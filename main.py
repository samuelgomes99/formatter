from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import re
from io import StringIO, BytesIO
from fastapi.responses import StreamingResponse
import os

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
    Remove todos os caracteres que não são dígitos do número de telefone.
    """
    return re.sub(r'\D', '', numero)


def formatar_numero(numero: str) -> str:
    """
    Formata o número de telefone para o padrão E.164: +55[DDD][Número]

    Regras:
      - Se o DDD for maior ou igual a 30, o número local não deve conter o dígito 9.
        Assim, se o número local tiver 9 dígitos e iniciar com '9', remove-se apenas o primeiro dígito.
      - Se o DDD for menor que 30, o número local deve conter o dígito 9.
        Se estiver com 8 dígitos (e não iniciar com '9'), adiciona-se o dígito '9' no início.
    """
    numero_limpo = normalizar_telefone(numero)

    # Remove o código do país '55' se presente
    if numero_limpo.startswith('55'):
        numero_limpo = numero_limpo[2:]

    # Após remover o código do país, esperamos 10 ou 11 dígitos (2 para DDD + 8 ou 9 para o número local)
    if len(numero_limpo) not in (10, 11):
        return numero  # Retorna o número original se o tamanho não for válido

    ddd = numero_limpo[:2]
    parte_local = numero_limpo[2:]

    if int(ddd) >= 30:
        # Para DDD ≥ 30, o número local deve ter 8 dígitos.
        # Se estiver com 9 dígitos e iniciar com '9', remove APENAS o primeiro dígito.
        if len(parte_local) == 9 and parte_local.startswith('9'):
            parte_local = parte_local[1:]
    else:
        # Para DDD < 30, o número local deve ter 9 dígitos.
        # Se estiver com 8 dígitos e não iniciar com '9', adiciona o dígito '9'.
        if len(parte_local) == 8 and not parte_local.startswith('9'):
            parte_local = '9' + parte_local

    return f"+55{ddd}{parte_local}"


def detectar_formato_arquivo(filename: str) -> str:
    """
    Detecta o formato do arquivo com base na extensão.
    Retorna a extensão em letras minúsculas.
    """
    _, ext = os.path.splitext(filename)
    return ext.lower()


@app.post("/formatar-telefones")
async def formatar_telefones(
        file: UploadFile = File(...),
        coluna_telefone: str = Form(...)
):
    # Suporte a múltiplos formatos de arquivo
    formatos_suportados = ['.csv', '.xlsx', '.xls', '.tsv']
    formato = detectar_formato_arquivo(file.filename)

    if formato not in formatos_suportados:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de arquivo não suportado. Formatos suportados: {', '.join(formatos_suportados)}"
        )

    try:
        contents = await file.read()
        if formato == '.csv':
            df = pd.read_csv(StringIO(contents.decode('utf-8')))
        elif formato in ['.xlsx', '.xls']:
            df = pd.read_excel(BytesIO(contents))
        elif formato == '.tsv':
            df = pd.read_csv(StringIO(contents.decode('utf-8')), sep='\t')
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de arquivo não suportado: {formato}"
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler o arquivo: {str(e)}")

    # Remove espaços dos nomes das colunas
    df.columns = df.columns.str.strip()

    # Verifica se a coluna de telefone existe (ignorando maiúsculas/minúsculas)
    colunas_lower = [col.lower() for col in df.columns]
    coluna_telefone_lower = coluna_telefone.lower()
    if coluna_telefone_lower not in colunas_lower:
        raise HTTPException(
            status_code=400,
            detail=f"A coluna '{coluna_telefone}' não foi encontrada no arquivo. "
                   f"Colunas disponíveis: {df.columns.tolist()}"
        )

    # Obtém o nome exato da coluna (respeitando a capitalização)
    indice_coluna = colunas_lower.index(coluna_telefone_lower)
    coluna_telefone_real = df.columns[indice_coluna]

    try:
        # Aplica a formatação aos telefones
        df[coluna_telefone_real] = df[coluna_telefone_real].astype(str).apply(formatar_numero)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao formatar os telefones: {str(e)}")

    try:
        # Gera o arquivo no mesmo formato de entrada
        output = BytesIO()
        if formato == '.csv':
            df.to_csv(output, index=False)
            mime_type = "text/csv"
            extension = ".csv"
        elif formato in ['.xlsx', '.xls']:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
            mime_type = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                         if formato == '.xlsx'
                         else "application/vnd.ms-excel")
            extension = ".xlsx" if formato == '.xlsx' else ".xls"
        elif formato == '.tsv':
            df.to_csv(output, index=False, sep='\t')
            mime_type = "text/tab-separated-values"
            extension = ".tsv"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Formato de arquivo não suportado para saída: {formato}"
            )
        output.seek(0)
        return StreamingResponse(
            output,
            media_type=mime_type,
            headers={
                "Content-Disposition": f"attachment; filename=telefones_formatados_{os.path.splitext(file.filename)[0]}{extension}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar o arquivo formatado: {str(e)}")


@app.get("/")
async def root():
    return {"message": "API de formatação de telefones. Use o endpoint /formatar-telefones."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8081)
