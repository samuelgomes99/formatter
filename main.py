from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import re
from io import StringIO, BytesIO
from fastapi.responses import StreamingResponse

app = FastAPI()

# Configuração do CORS para permitir todas as origens
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def normalizar_telefone(numero: str) -> str:
    """
    Remove todos os caracteres que não são números de um telefone.
    """
    return re.sub(r'\D', '', numero)

def formatar_numero(numero: str) -> str:
    """
    Formata o número de telefone para o padrão:
    +55[DDD][Número com ou sem nono dígito, dependendo do DDD].
    """
    # Remove caracteres não numéricos
    numero_normalizado = normalizar_telefone(numero)

    # Verifica se o número já possui código do país
    if numero_normalizado.startswith('55'):
        numero_normalizado = numero_normalizado[2:]  # Remove o '55'

    # Verifica se o número tem pelo menos 10 dígitos (2 DDD + 8 número)
    if len(numero_normalizado) < 10:
        return numero  # Retorna o número original se for inválido

    # Extrai DDD e o restante do número
    ddd = numero_normalizado[:2]
    restante = numero_normalizado[2:]

    # Aplica a regra do nono dígito
    if int(ddd) >= 30:  # DDD maior ou igual a 30
        if restante.startswith('9'):
            restante = restante[1:]  # Remove o '9' inicial
    else:  # DDD menor que 30
        if not restante.startswith('9'):
            restante = '9' + restante  # Adiciona o '9' inicial

    # Retorna o número no formato final
    return f"+55{ddd}{restante}"

@app.post("/formatar-telefones")
async def formatar_telefones(
    file: UploadFile = File(...),
    coluna_telefone: str = Form(...)
):
    # Verifica se o arquivo é um CSV
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="O arquivo deve ser um CSV.")

    try:
        # Lê o conteúdo do arquivo
        contents = await file.read()
        df = pd.read_csv(StringIO(contents.decode('utf-8')))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler o arquivo CSV: {str(e)}")

    # Remove espaços dos nomes das colunas
    df.columns = df.columns.str.strip()

    # Verifica se a coluna de telefone existe
    if coluna_telefone not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"A coluna '{coluna_telefone}' não foi encontrada no arquivo CSV. "
                   f"Colunas disponíveis: {df.columns.tolist()}"
        )

    try:
        # Aplica a formatação aos telefones
        df[coluna_telefone] = df[coluna_telefone].astype(str).apply(formatar_numero)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao formatar os telefones: {str(e)}")

    try:
        # Gera o CSV com os números formatados
        output = StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return StreamingResponse(
            BytesIO(output.getvalue().encode('utf-8')),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=telefones_formatados_{file.filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar o arquivo CSV: {str(e)}")

@app.get("/")
async def root():
    return {"message": "API de formatação de telefones. Use o endpoint /formatar-telefones."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
