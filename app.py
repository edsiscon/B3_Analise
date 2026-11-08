import datetime
import logging
import urllib.parse
import feedparser
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from config import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
        
caminho_logo = "logouff_vertical_azul-1.png"
st.set_page_config(
    page_title="Dashboard B3 - Eleições 2026, Liquidez & Índices",
    page_icon=caminho_logo,
    layout="wide",
)

st.title(
    "📊 Análise de Volume, Liquidez, Preços e Fluxo vs Índices (Eleições 2026)"
)


@st.cache_data(ttl=3600)
def carregar_indice_yfinance(symbol, di, df_data):
    """Carrega os dados históricos de um índice de mercado via yfinance."""
    try:
        df_idx = yf.download(
            symbol, start=di, end=df_data + pd.Timedelta(days=1), progress=False
        )
        if not df_idx.empty:
            if isinstance(df_idx.columns, pd.MultiIndex):
                df_idx.columns = df_idx.columns.get_level_values(0)
            df_idx = df_idx.reset_index()

            # Evita o Pandas4Warning (sem inplace=True)
            df_idx = df_idx.rename(
                columns={
                    "Date": "data_pregao",
                    "Close": "fechamento",
                    "Volume": "volume",
                }
            )
            df_idx["data_pregao"] = pd.to_datetime(
                df_idx["data_pregao"]
            ).dt.tz_localize(None)
            return df_idx[["data_pregao", "fechamento", "volume"]]
    except Exception as e:
        logger.warning(
            f"Não foi possível carregar o índice {symbol} via Yahoo Finance: {e}"
        )
    return pd.DataFrame()


@st.cache_data(ttl=1800)
def buscar_noticias_rss_google(ticker, data_inicio, data_fim, limit=5):
    """Busca notícias reais via RSS do Google usando apenas o nome do Ticker."""
    try:
        query = f"{ticker}"
        query_encoded = urllib.parse.quote(query)

        data_ini_str = data_inicio.strftime("%Y-%m-%d")
        data_fim_str = (data_fim + pd.Timedelta(days=2)).strftime("%Y-%m-%d")

        rss_url = f"https://news.google.com/rss/search?q={query_encoded}+after:{data_ini_str}+before:{data_fim_str}&hl=pt-BR&gl=BR&ceid=BR:pt-419"

        feed = feedparser.parse(rss_url)
        noticias = []

        for entry in feed.entries[:limit]:
            noticias.append(
                {
                    "titulo": entry.title,
                    "link": entry.link,
                    "publicado": getattr(entry, "published", ""),
                }
            )

        return noticias
    except Exception as e:
        logger.error(f"Erro ao buscar notícias RSS: {e}")
        return []


# --- BARRA LATERAL (INPUTS) ---
st.sidebar.header("⚙️ Parâmetros da Análise")

# Ticker via input de texto simples (sem ler do banco)
ticker_selecionado = st.sidebar.text_input(
    "Digite o Ticker do Ativo:", value="PETR4"
).upper().strip()

st.sidebar.subheader("Intervalo Temporal")
di = st.sidebar.date_input("Data Inicial (di):", pd.to_datetime("2026-09-01"))
df_data = st.sidebar.date_input("Data Final (df):", pd.to_datetime("2026-10-30"))

st.sidebar.subheader("📈 Índices de Mercado (Yahoo Finance)")
indices_selecionados = st.sidebar.multiselect(
    "Selecione os Índices para Comparação:",
    options=["IBOVESPA (^BVSP)"],
    default=["IBOVESPA (^BVSP)"],
)

st.sidebar.subheader("🌐 Filtro de Investidores (Gráfico de Fluxo)")
categorias_disponiveis = [
    "Estrangeiro",
    "Institucional",
    "Pessoa física",
    "Inst. Financeira",
    "Outros",
]
categorias_selecionadas = st.sidebar.multiselect(
    "Selecione as categorias para exibir:",
    options=categorias_disponiveis,
    default=categorias_disponiveis,
)

if ticker_selecionado and di and df_data:
    try:
        # CONSULTA DIRETA E LEVE: Apenas o Ticker e Período exatos
        query_ativo = """
            SELECT * FROM public.cotacoes
            WHERE ticker = %(ticker)s
              AND data_pregao BETWEEN %(di)s AND %(df)s
            ORDER BY data_pregao ASC;
        """
        params = {
            "ticker": ticker_selecionado,
            "di": f"{di.strftime('%Y-%m-%d')} 00:00:00",
            "df": f"{df_data.strftime('%Y-%m-%d')} 23:59:59",
        }
        df_acao = pd.read_sql(query_ativo, con=engine, params=params)

        # Índices via yfinance
        dict_indices = {}
        if "IBOVESPA (^BVSP)" in indices_selecionados:
            dict_indices["IBOVESPA"] = carregar_indice_yfinance(
                "^BVSP", di, df_data
            )
        if "IFIX (^IFIX)" in indices_selecionados:
            dict_indices["IFIX"] = carregar_indice_yfinance(
                "^IFIX", di, df_data
            )
        if "S&P 500 (^GSPC)" in indices_selecionados:
            dict_indices["S&P 500"] = carregar_indice_yfinance(
                "^GSPC", di, df_data
            )

        # Fluxo de Investidores
        query_fluxo = """
            SELECT * FROM fluxo_investidores
            WHERE data_pregao BETWEEN %(di)s AND %(df)s
            ORDER BY data_pregao ASC;
        """
        try:
            df_fluxo = pd.read_sql(query_fluxo, con=engine, params=params)
            if not df_fluxo.empty:
                df_fluxo["data_pregao"] = pd.to_datetime(df_fluxo["data_pregao"])
        except Exception:
            df_fluxo = pd.DataFrame()

        if not df_acao.empty:
            df_acao["data_pregao"] = pd.to_datetime(df_acao["data_pregao"])

            # Tratamentos de Volume e Preços
            s_vol = df_acao["volume_financeiro"].astype(float)
            df_acao["vol_calculado"] = (
                s_vol / 100.0 if s_vol.max() > 1_000_000_000 else s_vol
            )

            s_med = df_acao["preco_medio"].astype(float)
            df_acao["preco_medio_corrigido"] = (
                s_med / 100.0 if s_med.max() > 10000 else s_med
            )

            s_abe = df_acao["preco_abertura"].astype(float)
            df_acao["preco_abertura_corrigido"] = (
                s_abe / 100.0 if s_abe.max() > 10000 else s_abe
            )

            s_ult = df_acao["preco_fechamento"].astype(float)
            df_acao["preco_fechamento_corrigido"] = (
                s_ult / 100.0 if s_ult.max() > 10000 else s_ult
            )

            # Métricas principais
            vol_total = df_acao["vol_calculado"].sum()
            vol_medio = df_acao["vol_calculado"].mean()
            vol_maximo = df_acao["vol_calculado"].max()
            qtd_total = df_acao["qtd_negociada"].sum()

            st.subheader(
                f"Liquidez: **{ticker_selecionado}** ({di.strftime('%d/%m/%Y')} a {df_data.strftime('%d/%m/%Y')})"
            )

            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Volume Acumulado",
                f"R$ {vol_total:,.2f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", "."),
            )
            c2.metric(
                "Volume Médio Diário",
                f"R$ {vol_medio:,.2f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", "."),
            )
            c3.metric(
                "Pico de Volume",
                f"R$ {vol_maximo:,.2f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", "."),
            )
            c4.metric("Total de Títulos", f"{qtd_total:,.0f}".replace(",", "."))

            st.markdown("---")

            # Datas dos Turnos Eleitorais
            dt_turno1 = pd.to_datetime("2026-10-05")
            dt_turno2 = pd.to_datetime("2026-10-26")

            def adicionar_linhas_eleicao(fig, df_ref, col_data_name):
                min_dt = df_ref[col_data_name].min()
                max_dt = df_ref[col_data_name].max()

                if min_dt <= dt_turno1 <= max_dt:
                    fig.add_vline(
                        x=dt_turno1.timestamp() * 1000,
                        line_width=2,
                        line_dash="dash",
                        line_color="#0066cc",
                        annotation_text="1º Turno (05/10/2026)",
                        annotation_position="top left",
                        annotation_font_color="#0066cc",
                    )

                if min_dt <= dt_turno2 <= max_dt:
                    fig.add_vline(
                        x=dt_turno2.timestamp() * 1000,
                        line_width=2,
                        line_dash="dash",
                        line_color="#d62728",
                        annotation_text="2º Turno (26/10/2026)",
                        annotation_position="top right",
                        annotation_font_color="#d62728",
                    )

            def adicionar_traces_indices(fig, col_target="fechamento"):
                cores_indices = {
                    "IBOVESPA": "#9467bd",
                    "IFIX": "#8c564b",
                    "S&P 500": "#e377c2",
                }
                estilos_indices = {
                    "IBOVESPA": "dash",
                    "IFIX": "dot",
                    "S&P 500": "dashdot",
                }
                tem_secundario = False

                for idx_nome, df_idx in dict_indices.items():
                    if not df_idx.empty:
                        y_val = (
                            df_idx["volume"]
                            if col_target == "volume"
                            else df_idx["fechamento"]
                        )
                        fig.add_trace(
                            go.Scatter(
                                x=df_idx["data_pregao"],
                                y=y_val,
                                mode="lines",
                                name=f"{idx_nome}",
                                yaxis="y2",
                                line=dict(
                                    color=cores_indices.get(
                                        idx_nome, "#7f7f7f"
                                    ),
                                    width=1.5,
                                    dash=estilos_indices.get(
                                        idx_nome, "dash"
                                    ),
                                ),
                            )
                        )
                        tem_secundario = True
                return tem_secundario

            # --- GRÁFICO 1: EVOLUÇÃO DO VOLUME ---
            st.markdown(
                f"### 📈 Volume Financeiro: {ticker_selecionado} vs Índices"
            )
            fig_vol = go.Figure()
            fig_vol.add_trace(
                go.Scatter(
                    x=df_acao["data_pregao"],
                    y=df_acao["vol_calculado"],
                    mode="lines",
                    name=f"Volume {ticker_selecionado}",
                    line=dict(color="#1f77b4", width=2),
                )
            )
            tem_y2_vol = adicionar_traces_indices(fig_vol, col_target="volume")
            adicionar_linhas_eleicao(fig_vol, df_acao, "data_pregao")
            fig_vol.update_layout(
                xaxis_title="Data",
                yaxis=dict(title=f"Volume {ticker_selecionado} (R$)"),
                yaxis2=(
                    dict(
                        title="Volume Índices", overlaying="y", side="right"
                    )
                    if tem_y2_vol
                    else None
                ),
                margin=dict(l=20, r=20, t=30, b=20),
                hovermode="x unified",
                template="plotly_white",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
            )
            st.plotly_chart(fig_vol, use_container_width=True)

            # --- GRÁFICO 2: FLUXO DE INVESTIDORES vs ÍNDICES ---
            st.markdown(
                "### 🌐 Fluxo Líquido por Categoria de Investidor vs Índices"
            )
            if not df_fluxo.empty:
                fig_fluxo = go.Figure()
                mapeamento_categorias = {
                    "Estrangeiro": ("estrangeiro", "#0066cc"),
                    "Institucional": ("institucional", "#ff7f0e"),
                    "Pessoa física": ("pessoa_fisica", "#2ca02c"),
                    "Inst. Financeira": ("inst_financeira", "#d62728"),
                    "Outros": ("outros", "#7f7f7f"),
                }
                for label in categorias_selecionadas:
                    col_db, cor = mapeamento_categorias[label]
                    if col_db in df_fluxo.columns:
                        fig_fluxo.add_trace(
                            go.Scatter(
                                x=df_fluxo["data_pregao"],
                                y=df_fluxo[col_db],
                                mode="lines",
                                name=label,
                                line=dict(color=cor, width=2),
                            )
                        )
                tem_y2_fluxo = adicionar_traces_indices(
                    fig_fluxo, col_target="fechamento"
                )
                adicionar_linhas_eleicao(fig_fluxo, df_fluxo, "data_pregao")
                fig_fluxo.update_layout(
                    xaxis_title="Data",
                    yaxis=dict(title="Saldo Líquido (R$)"),
                    yaxis2=(
                        dict(
                            title="Pontos Índices", overlaying="y", side="right"
                        )
                        if tem_y2_fluxo
                        else None
                    ),
                    margin=dict(l=20, r=20, t=30, b=20),
                    hovermode="x unified",
                    template="plotly_white",
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1,
                    ),
                )
                st.plotly_chart(fig_fluxo, use_container_width=True)
            else:
                st.info(
                    "Nenhum dado de fluxo de investidores encontrado para o período selecionado."
                )

            # --- GRÁFICO 3: PREÇO MÉDIO vs ÍNDICES ---
            st.markdown(f"### 🏷️ Preço Médio: {ticker_selecionado} vs Índices")
            fig_preco = go.Figure()
            fig_preco.add_trace(
                go.Scatter(
                    x=df_acao["data_pregao"],
                    y=df_acao["preco_medio_corrigido"],
                    mode="lines",
                    name=f"Preço Médio {ticker_selecionado}",
                    line=dict(color="#2ca02c", width=2),
                )
            )
            tem_y2_preco = adicionar_traces_indices(
                fig_preco, col_target="fechamento"
            )
            adicionar_linhas_eleicao(fig_preco, df_acao, "data_pregao")
            fig_preco.update_layout(
                xaxis_title="Data",
                yaxis=dict(title=f"Preço Médio {ticker_selecionado} (R$)"),
                yaxis2=(
                    dict(
                        title="Pontos Índices", overlaying="y", side="right"
                    )
                    if tem_y2_preco
                    else None
                ),
                margin=dict(l=20, r=20, t=30, b=20),
                hovermode="x unified",
                template="plotly_white",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
            )
            st.plotly_chart(fig_preco, use_container_width=True)

            # --- GRÁFICO 4: PREÇO DE ABERTURA VS FECHAMENTO ---
            st.markdown(
                f"### 🔔 Preço de Abertura vs Fechamento: {ticker_selecionado}"
            )
            fig_abe_ult = go.Figure()
            fig_abe_ult.add_trace(
                go.Scatter(
                    x=df_acao["data_pregao"],
                    y=df_acao["preco_abertura_corrigido"],
                    mode="lines",
                    name=f"Abertura {ticker_selecionado}",
                    line=dict(color="#17becf", width=2),
                )
            )
            fig_abe_ult.add_trace(
                go.Scatter(
                    x=df_acao["data_pregao"],
                    y=df_acao["preco_fechamento_corrigido"],
                    mode="lines",
                    name=f"Fechamento {ticker_selecionado}",
                    line=dict(color="#bcbd22", width=2),
                )
            )
            tem_y2_abe_ult = adicionar_traces_indices(
                fig_abe_ult, col_target="fechamento"
            )
            adicionar_linhas_eleicao(fig_abe_ult, df_acao, "data_pregao")
            fig_abe_ult.update_layout(
                xaxis_title="Data",
                yaxis=dict(title="Preço (R$)"),
                yaxis2=(
                    dict(
                        title="Pontos Índices", overlaying="y", side="right"
                    )
                    if tem_y2_abe_ult
                    else None
                ),
                margin=dict(l=20, r=20, t=30, b=20),
                hovermode="x unified",
                template="plotly_white",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
            )
            st.plotly_chart(fig_abe_ult, use_container_width=True)

            # --- DETALHAMENTO DIÁRIO (TEXTO / MÉTRICAS) ---
            st.markdown(
                f"### 📌 Detalhamento Diário do Pregão: **{ticker_selecionado}**"
            )

            min_dt_val = df_acao["data_pregao"].min().date()
            max_dt_val = df_acao["data_pregao"].max().date()

            data_detalhe = st.date_input(
                "Selecione uma data para consultar cotações exatas:",
                value=di if di >= min_dt_val else min_dt_val,
                min_value=min_dt_val,
                max_value=max_dt_val,
                key="date_picker_detalhe",
            )

            row_dia = df_acao[df_acao["data_pregao"].dt.date == data_detalhe]

            if not row_dia.empty:
                r = row_dia.iloc[0]

                v_abe = r["preco_abertura_corrigido"]
                v_ult = r["preco_fechamento_corrigido"]

                s_max = float(r["preco_maximo"])
                v_max = s_max / 100.0 if s_max > 10000 else s_max

                s_min = float(r["preco_minimo"])
                v_min = s_min / 100.0 if s_min > 10000 else s_min

                col_a, col_f, col_max_c, col_min_c = st.columns(4)
                col_a.metric("🔔 Abertura", f"R$ {v_abe:.2f}")
                col_f.metric(
                    "🏁 Fechamento",
                    f"R$ {v_ult:.2f}",
                    delta=f"{((v_ult - v_abe) / v_abe) * 100:+.2f}% vs Abertura",
                )
                col_max_c.metric("📈 Máxima do Dia", f"R$ {v_max:.2f}")
                col_min_c.metric("📉 Mínima do Dia", f"R$ {v_min:.2f}")

                st.info(
                    f"🗓️ **Resumo do Pregão ({data_detalhe.strftime('%d/%m/%Y')}):** "
                    f"O papel **{ticker_selecionado}** abriu cotado a **R$ {v_abe:.2f}**, atingiu a máxima de **R$ {v_max:.2f}** "
                    f"e a mínima de **R$ {v_min:.2f}**, encerrando o dia a **R$ {v_ult:.2f}**."
                )
            else:
                st.warning(
                    f"Não houve pregão registrado para **{ticker_selecionado}** no dia {data_detalhe.strftime('%d/%m/%Y')} (final de semana ou feriado)."
                )

            st.markdown("---")

            # --- SEÇÃO DE NOTÍCIAS (ESTILO RESULTADOS DO GOOGLE) ---
            with st.expander(
                f"🔍 **Notícias Google: Manchetes de {ticker_selecionado} nos Dias de Pico**",
                expanded=True,
            ):
                st.markdown(
                    f"Resultados de busca para **{ticker_selecionado}** nos **5 dias de maior volume financeiro**:"
                )

                top_5_dias = df_acao.sort_values(
                    by="vol_calculado", ascending=False
                ).head(5)

                for idx, row in top_5_dias.reset_index(drop=True).iterrows():
                    data_dt = row["data_pregao"]
                    data_str = data_dt.strftime("%d/%m/%Y")
                    vol_fmt = (
                        f"R$ {row['vol_calculado']:,.2f}".replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )
                    preco_fmt = f"R$ {row['preco_medio_corrigido']:.2f}"

                    st.markdown(
                        f"### {idx + 1}. Pregão de {data_str} | Volume: `{vol_fmt}` | Preço Médio: `{preco_fmt}`"
                    )

                    noticias_dia = buscar_noticias_rss_google(
                        ticker_selecionado, data_dt, data_dt
                    )

                    if noticias_dia:
                        for item in noticias_dia:
                            st.markdown(
                                f"#### 🔗 [{item['titulo']}]({item['link']})"
                            )
                            if item["publicado"]:
                                st.caption(
                                    f"🕒 Publicado em: {item['publicado']}"
                                )
                    else:
                        g_min = data_dt.strftime("%m/%d/%Y")
                        g_max = (data_dt + pd.Timedelta(days=1)).strftime(
                            "%m/%d/%Y"
                        )
                        url_gnews = f"https://www.google.com/search?q={ticker_selecionado}&tbm=nws&tbs=cdr:1,cd_min:{g_min},cd_max:{g_max}"

                        st.markdown(
                            f"#### 🔗 [Ver todos os resultados no Google News para {ticker_selecionado} em {data_str}]({url_gnews})"
                        )

                    st.markdown("---")

            with st.expander("Ver dados brutos"):
                st.dataframe(df_acao, use_container_width=True)
        else:
            st.warning(
                f"Nenhum dado encontrado para **{ticker_selecionado}** no período selecionado."
            )

    except Exception as e:
        logger.error(f"Erro ao consultar o banco: {e}")
        st.error(
            "⚠️ Ocorreu um erro ao buscar as informações. Verifique a conexão com o banco de dados."
        )
