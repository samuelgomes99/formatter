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
    Remove todos os caracteres que não são dígitos do número.
    """
    return re.sub(r'\D', '', numero)


def formatar_numero(numero: str) -> str:
    """
    Formata o número para o padrão E.164 (+55[DDD][Número]) aplicando as regras:
      - Se o DDD for menor que 30, o número (geralmente móvel) deve conter o dígito 9.
        Caso o número local não comece com '9', adiciona-o à esquerda.
      - Se o DDD for maior ou igual a 30, o número (fixo) não deve conter o dígito 9 extra.
        Assim, se o número local tiver 9 dígitos e iniciar com '9', remove-se esse primeiro dígito.

    A função também remove um eventual prefixo “0” e o código do país “55”, se presentes.

    Se o número, após a normalização, não tiver 10 ou 11 dígitos, o valor original é retornado.
    """
    original = numero
    # Remove todos os caracteres não numéricos
    digits = normalizar_telefone(numero)

    # Remove um eventual prefixo de trunk (0)
    if digits.startswith('0'):
        digits = digits[1:]

    # Remove o código do país, se estiver presente
    if digits.startswith('55'):
        digits = digits[2:]

    # Após esses ajustes, o número deve ter 10 ou 11 dígitos (2 para DDD + 8 ou 9 para o local)
    if len(digits) not in (10, 11):
        return original  # Se não tiver tamanho esperado, retorna o número original

    ddd = digits[:2]
    local = digits[2:]

    try:
        ddd_int = int(ddd)
    except ValueError:
        return original  # Em caso de problema com o DDD, retorna o original

    # Para DDD < 30 (região onde os celulares devem conter o dígito 9)
    if ddd_int < 30:
        # Se o número local não começar com '9', adiciona-o;
        # caso já comece com '9', considera que está correto.
        if not local.startswith('9'):
            local = '9' + local
    else:
        # Para DDD ≥ 30 (números fixos, que não levam o nono dígito)
        # Se o número local tiver 9 dígitos e iniciar com '9', remove o primeiro dígito.
        if len(local) == 9 and local.startswith('9'):
            local = local[1:]

    return f"+55{ddd}{local}"


def detectar_formato_arquivo(filename: str) -> str:
    """
    Detecta o formato do arquivo com base na extensão,
    retornando a extensão em letras minúsculas.
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
            mime_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                if formato == '.xlsx'
                else "application/vnd.ms-excel"
            )
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
