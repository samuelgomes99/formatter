from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import re
from io import StringIO

app = FastAPI()

# Configuração do CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def formatar_telefone(numero):
    # Remove caracteres não numéricos
    numero_limpo = re.sub(r'\D', '', str(numero))

    # Regex aprimorado para capturar diferentes formatos
    padrao = re.compile(
        r'^(\+?(\d{1,3})?)?'  # Código do país (opcional)
        r'(\d{2})'  # DDD
        r'(\d{8,})$'  # Resto do número (mínimo 8 dígitos)
    )

    match = padrao.match(numero_limpo)

    if not match:
        return numero  # Mantém original se não corresponder ao padrão

    codigo_pais, _, ddd, resto = match.groups()
    codigo_pais = codigo_pais if codigo_pais else '+55'
    ddd = int(ddd)

    # Aplica regras de formatação
    if ddd > 30:
        if resto.startswith('9'):
            resto = resto[1:]
    else:
        if not resto.startswith('9'):
            resto = '9' + resto

    return f"{codigo_pais}{ddd}{resto}"


@app.post("/formatar-telefones")
async def formatar_telefones(
        file: UploadFile = File(...),
        coluna_telefone: str = Form(...)
):
    try:
        # Validação do arquivo
        if not file.filename.lower().endswith('.csv'):
            raise HTTPException(
                status_code=400,
                detail="O arquivo deve ser um CSV válido."
            )

        # Processamento do CSV
        contents = await file.read()
        df = pd.read_csv(StringIO(contents.decode('utf-8')))

        # Normalização das colunas
        df.columns = df.columns.str.strip().str.lower()
        coluna = coluna_telefone.strip().lower()

        # Validação da coluna
        if coluna not in df.columns:
            disponiveis = ', '.join(df.columns)
            raise HTTPException(
                status_code=400,
                detail=f"Coluna '{coluna_telefone}' não encontrada. Colunas disponíveis: {disponiveis}"
            )

        # Formatação dos telefones
        df[coluna] = df[coluna].apply(formatar_telefone)

        # Geração do resultado
        output = StringIO()
        df.to_csv(output, index=False, encoding='utf-8')
        output.seek(0)

        return {"file": output.getvalue()}

    except pd.errors.ParserError:
        raise HTTPException(
            status_code=400,
            detail="Erro na leitura do CSV. Verifique o formato do arquivo."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno no servidor: {str(e)}"
        )


@app.get("/")
async def root():
    return {"message": "API de formatação de telefones. Use o endpoint POST /formatar-telefones"}