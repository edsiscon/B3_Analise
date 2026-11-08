import urllib.parse
from sqlalchemy import create_engine
import streamlit as st


def get_database_engine():
    try:
        user = st.secrets["postgres"]["user"]
        password = st.secrets["postgres"]["password"]
        host = st.secrets["postgres"]["host"]
        port = str(st.secrets["postgres"]["port"])
        dbname = st.secrets["postgres"]["dbname"]

        # Trata caracteres especiais na senha
        password_encoded = urllib.parse.quote_plus(password)

        db_url = f"postgresql+psycopg2://{user}:{password_encoded}@{host}:{port}/{dbname}"

        return create_engine(
            db_url, pool_pre_ping=True, connect_args={"connect_timeout": 10}
        )
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        raise e


engine = get_database_engine()