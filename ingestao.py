import pandas as pd
from sqlalchemy import text
from config import engine


def criar_indices():
    """Garante buscas instantâneas por ativo e data no Streamlit."""
    print("Criando índices de busca rápida no Supabase...")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_cotacoes_ticker_data 
            ON cotacoes (ticker, data_pregao DESC);
        """))
        conn.commit()
    print("✅ Índices criados com sucesso!")


def processar_e_salvar(caminho_txt):
    print(f"Lendo o arquivo: {caminho_txt}...")

    # Posições fixas da especificação COTAHIST da B3
    widths = [2, 8, 2, 12, 3, 12, 10, 3, 4, 13, 13, 13, 13, 13, 13, 13, 5, 18, 18, 13, 1, 8, 7, 13, 12]
    colnames = [
        'TIPREG', 'DATPRE', 'CODBDI', 'CODNEG', 'TPMERC', 'NOMRES', 'ESPECI',
        'PRAZOT', 'MODREF', 'PREABE', 'PREMAX', 'PREMIN', 'PREMED', 'PREFCAT',
        'PREOFC', 'PREOFV', 'TOTNEG', 'QUATOT', 'VOLTOT', 'PREERC', 'INDDAT',
        'DATVEN', 'FATCOT', 'PTOERC', 'CODISI'
    ]

    # 1. Leitura com encoding='latin-1' para evitar UnicodeDecodeError
    df = pd.read_fwf(
        caminho_txt,
        widths=widths,
        names=colnames,
        header=None,
        dtype=str,
        encoding='latin-1'
    )

    # Lê apenas cotações do lote padrão / mercado à vista (TIPREG == '01')
    df = df[df['TIPREG'] == '01'].copy()

    # 2. Formatação de datas e números
    df['DATPRE'] = pd.to_datetime(df['DATPRE'], format='%Y%m%d')

    # B3 envia preços e volumes com 2 casas decimais implícitas (dividir por 100)
    colunas_financeiras = ['PREABE', 'PREMAX', 'PREMIN', 'PREMED', 'PREFCAT', 'VOLTOT']
    for col in colunas_financeiras:
        df[col] = df[col].astype(float) / 100.0

    df['QUATOT'] = df['QUATOT'].astype(int)
    df['CODNEG'] = df['CODNEG'].str.strip()
    df['NOMRES'] = df['NOMRES'].str.strip()

    # 3. Seleção e Renomeação de campos para a tabela cotacoes
    df_banco = df[[
        'DATPRE', 'CODBDI', 'CODNEG', 'TPMERC', 'NOMRES', 'ESPECI',
        'PREABE', 'PREMAX', 'PREMIN', 'PREMED', 'PREFCAT', 'QUATOT', 'VOLTOT'
    ]].copy()

    df_banco.columns = [
        'data_pregao', 'cod_bdi', 'ticker', 'tipo_mercado', 'nome_empresa', 'especi_papel',
        'preco_abertura', 'preco_maximo', 'preco_minimo', 'preco_medio', 'preco_fechamento',
        'qtd_negociada', 'volume_financeiro'
    ]

    # 4. Envio eficiente em lotes de 5.000 para a tabela cotacoes
    print(f"🚀 Enviando {len(df_banco)} linhas para a tabela 'cotacoes' no Supabase...")
    try:
        df_banco.to_sql(
            name='cotacoes',
            con=engine,
            if_exists='append',
            index=False,
            chunksize=5000,
            method='multi'
        )
        print("✅ Ingestão finalizada com sucesso!")

        # Criação do índice para otimizar o Streamlit
        criar_indices()
        print("🎉 Carga e indexação finalizadas no Supabase com sucesso!")

    except Exception as e:
        print(f"❌ Erro na ingestão: {e}")


if __name__ == "__main__":
        processar_e_salvar("COTAHIST_M092026.TXT")