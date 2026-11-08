import os
import pandas as pd
from sqlalchemy import create_engine, text

# Puxa os dados das variáveis de ambiente se rodar fora do Streamlit
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")

if DB_USER and DB_PASSWORD and DB_HOST:
    db_url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(db_url)
else:
    # Se rodar via streamlit CLI
    from config import engine