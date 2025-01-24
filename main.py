from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import re
from io import StringIO, BytesIO
from fastapi.responses import StreamingResponse

app = FastAPI()

# Configuração do CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Altere para as origens permitidas em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def formatar_telefone(numero):
    # Expressão regular para capturar o código do país e o número completo
    padrao = re.compile(r'(\+\d{1,3})?(\d{2})(\d{8,})')
    match = padrao.match(str(numero))  # Converte para string para evitar erros

    if not match:
        return numero  # Retorna o número original se não corresponder ao padrão esperado

    codigo_pais, ddd, resto = match.groups()
    codigo_pais = codigo_pais if codigo_pais else '+55'  # Assume +55 se não houver código do país

    ddd = int(ddd)

    # Aplica as regras de formatação
    if ddd > 30:
        # Remove o dígito 9 após o DDD, se existir
        if resto and resto[0] == '9':
            resto = resto[1:]
    else:
        # Adiciona o dígito 9 após o DDD, se não existir
        if resto and resto[0] != '9':
            resto = '9' + resto

    # Retorna o número formatado
    return f"{codigo_pais}{ddd}{resto}"

@app.post("/formatar-telefones")
async def formatar_telefones(
    file: UploadFile = File(...),
    coluna_telefone: str = Form(...)
):
    # Verifica se o arquivo é um CSV
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="O arquivo deve ser um CSV.")

    try:
        # Lê o arquivo CSV
        contents = await file.read()
        df = pd.read_csv(StringIO(contents.decode('utf-8')))
    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao ler o arquivo CSV.")

    # Verifica se a coluna de telefone existe
    if coluna_telefone not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"A coluna '{coluna_telefone}' não foi encontrada no arquivo CSV."
        )

    # Aplica a formatação
    df[coluna_telefone] = df[coluna_telefone].apply(formatar_telefone)

    try:
        # Salva o resultado em um novo CSV
        output = StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        byte_io = BytesIO(output.getvalue().encode('utf-8'))

        # Prepara a resposta como um arquivo para download
        return StreamingResponse(
            byte_io,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=telefones_formatados_{file.filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro ao processar o arquivo CSV.")

@app.get("/")
async def root():
    return {"message": "API de formatação de telefones. Use o endpoint /formatar-telefones."}
