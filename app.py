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

CAMINHO_LOGO = "logo.png"

st.set_page_config(
    page_title="Dashboard B3 - Liquidez & Índices",
    page_icon=CAMINHO_LOGO,
    layout="wide",
)

# Cabeçalho com Logo
col_logo, col_titulo = st.columns([1, 6])
with col_logo:
    try:
        st.image(CAMINHO_LOGO, width=90)
    except Exception:
        pass
with col_titulo:
    st.title("📊 Análise de Volume, Liquidez, Preços e Fluxo vs Índices")

st.markdown("---")


# --- FUNÇÕES DE DADOS E CACHE ---
@st.cache_data(ttl=3600)
def carregar_indice_yfinance(symbol, di, df_data):
    """Carrega histórico via yfinance e calcula variação percentual diária."""
    try:
        # Busca 5 dias antes de 'di' para calcular a variação % do primeiro dia do filtro
        inicio_busca = pd.to_datetime(di) - pd.Timedelta(days=5)
        df_idx = yf.download(
            symbol,
            start=inicio_busca,
            end=pd.to_datetime(df_data) + pd.Timedelta(days=1),
            progress=False,
        )
        if not df_idx.empty:
            if isinstance(df_idx.columns, pd.MultiIndex):
                df_idx.columns = df_idx.columns.get_level_values(0)
            df_idx = df_idx.reset_index()
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
            df_idx = df_idx.sort_values("data_pregao")
            df_idx["var_pct"] = df_idx["fechamento"].pct_change() * 100.0

            # Filtra de volta para o intervalo exato selecionado pelo usuário
            df_idx = df_idx[df_idx["data_pregao"] >= pd.to_datetime(di)]
            return df_idx[["data_pregao", "fechamento", "volume", "var_pct"]]
    except Exception as e:
        logger.warning(f"Erro ao carregar índice {symbol}: {e}")
    return pd.DataFrame()


@st.cache_data(ttl=1800)
def buscar_noticias_ibovespa(data_alvo, limit=5):
    """Busca notícias exclusivas sobre o IBOVESPA na data do evento."""
    try:
        query = "Ibovespa bolsa B3"
        query_encoded = urllib.parse.quote(query)

        data_ini_str = (data_alvo - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        data_fim_str = (data_alvo + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        rss_url = (
            f"https://news.google.com/rss/search?q={query_encoded}"
            f"+after:{data_ini_str}+before:{data_fim_str}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        )

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
        logger.error(f"Erro ao buscar notícias IBOVESPA: {e}")
        return []


# --- GERENCIAMENTO DE LINHAS DINÂMICAS (SESSION STATE) ---
if "linhas_dinamicas" not in st.session_state:
    st.session_state.linhas_dinamicas = []

# --- BARRA LATERAL (INPUTS) ---
st.sidebar.header("⚙️ Parâmetros da Análise")

ticker_selecionado = (
    st.sidebar.text_input("Digite o Ticker do Ativo:", value="PETR4")
    .upper()
    .strip()
)

st.sidebar.subheader("Intervalo Temporal")
di = st.sidebar.date_input("Data Inicial (di):", pd.to_datetime("2026-09-01"))
df_data = st.sidebar.date_input("Data Final (df):", pd.to_datetime("2026-10-30"))

st.sidebar.subheader("📈 Índices e Moedas (Yahoo Finance)")
opcoes_indices = {
    "IBOVESPA (^BVSP)": "^BVSP",
    "Dólar (USD/BRL)": "USDBRL=X",
    "S&P 500 (^GSPC)": "^GSPC",
    "IFIX (^IFIX)": "^IFIX",
}
indices_selecionados = st.sidebar.multiselect(
    "Selecione para Comparação:",
    options=list(opcoes_indices.keys()),
    default=["IBOVESPA (^BVSP)"],
)

# Gatilho de variação do IBOVESPA (padrão 10%, ajustável se desejar testar outros valores)
gatilho_ibov = st.sidebar.number_input(
    "Alerta de Variação IBOVESPA (%):",
    min_value=0.5,
    max_value=50.0,
    value=10.0,
    step=0.5,
    help="Exibe um marcador no gráfico e libera as notícias do IBOVESPA nos dias em que a variação absoluta atingir este percentual.",
)

# --- CONTROLE DE LINHAS DINÂMICAS NA SIDEBAR ---
st.sidebar.markdown("---")
st.sidebar.subheader("📍 Marcadores Dinâmicos nos Gráficos")

with st.sidebar.form("form_nova_linha", clear_on_submit=True):
    nova_data = st.date_input("Data do Evento:", value=di)
    novo_texto = st.text_input(
        "Descrição (ex: Copom, Balanço):", placeholder="Nome do evento"
    )
    nova_cor = st.color_picker("Cor da Linha:", value="#FF4B4B")
    btn_add = st.form_submit_button("➕ Adicionar Linha")

    if btn_add and novo_texto.strip():
        st.session_state.linhas_dinamicas.append(
            {
                "data": pd.to_datetime(nova_data),
                "texto": novo_texto.strip(),
                "cor": nova_cor,
            }
        )

if st.session_state.linhas_dinamicas:
    st.sidebar.caption("Linhas ativas:")
    for i, item in enumerate(st.session_state.linhas_dinamicas):
        col_txt, col_del = st.sidebar.columns([4, 1])
        col_txt.write(f"• {item['data'].strftime('%d/%m/%Y')}: **{item['texto']}**")
        if col_del.button("🗑️", key=f"del_linha_{i}"):
            st.session_state.linhas_dinamicas.pop(i)
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🌐 Filtro de Investidores")
categorias_disponiveis = [
    "Estrangeiro",
    "Institucional",
    "Pessoa física",
    "Inst. Financeira",
    "Outros",
]
categorias_selecionadas = st.sidebar.multiselect(
    "Selecione as categorias:",
    options=categorias_disponiveis,
    default=categorias_disponiveis,
)

# --- PROCESSAMENTO E GRÁFICOS ---
if ticker_selecionado and di and df_data:
    try:
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

        # Carrega índices selecionados + garante IBOVESPA para monitoramento de 10%
        dict_indices = {}
        for nome_exibicao in indices_selecionados:
            symbol = opcoes_indices[nome_exibicao]
            nome_chave = nome_exibicao.split(" (")[0]
            df_carregado = carregar_indice_yfinance(symbol, di, df_data)
            if not df_carregado.empty:
                dict_indices[nome_chave] = df_carregado

        df_ibov_monitor = dict_indices.get(
            "IBOVESPA", carregar_indice_yfinance("^BVSP", di, df_data)
        )

        # Identifica dias com variação >= gatilho_ibov (ex: 10%)
        eventos_ibov_extremos = pd.DataFrame()
        if not df_ibov_monitor.empty and "var_pct" in df_ibov_monitor.columns:
            eventos_ibov_extremos = df_ibov_monitor[
                df_ibov_monitor["var_pct"].abs() >= gatilho_ibov
            ].copy()

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

            # --- FUNÇÕES AUXILIARES DOS GRÁFICOS ---
            def adicionar_linhas_dinamicas(fig, df_ref, col_data_name):
                if not st.session_state.linhas_dinamicas:
                    return
                min_dt = df_ref[col_data_name].min()
                max_dt = df_ref[col_data_name].max()

                for linha in st.session_state.linhas_dinamicas:
                    dt_evento = linha["data"]
                    if min_dt <= dt_evento <= max_dt:
                        fig.add_vline(
                            x=dt_evento.timestamp() * 1000,
                            line_width=2,
                            line_dash="dash",
                            line_color=linha["cor"],
                            annotation_text=linha["texto"],
                            annotation_position="top left",
                            annotation_font_color=linha["cor"],
                        )

            def adicionar_traces_indices(fig, col_target="fechamento"):
                cores_indices = {
                    "IBOVESPA": "#9467bd",
                    "Dólar": "#2ca02c",
                    "IFIX": "#8c564b",
                    "S&P 500": "#e377c2",
                }
                estilos_indices = {
                    "IBOVESPA": "dash",
                    "Dólar": "solid",
                    "IFIX": "dot",
                    "S&P 500": "dashdot",
                }
                tem_secundario = False

                for idx_nome, df_idx in dict_indices.items():
                    if not df_idx.empty:
                        df_clean = df_idx.dropna(subset=["fechamento", "volume"])
                        y_val = (
                            df_clean["volume"]
                            if col_target == "volume"
                            else df_clean["fechamento"]
                        )

                        fig.add_trace(
                            go.Scatter(
                                x=df_clean["data_pregao"],
                                y=y_val,
                                mode="lines",
                                name=f"{idx_nome}",
                                yaxis="y2",
                                connectgaps=True,
                                line=dict(
                                    color=cores_indices.get(idx_nome, "#7f7f7f"),
                                    width=1.8,
                                    dash=estilos_indices.get(idx_nome, "dash"),
                                ),
                            )
                        )
                        tem_secundario = True

                        # Adiciona SÍMBOLO DE ALERTA nos dias de variação >= gatilho_ibov no IBOVESPA
                        if (
                            idx_nome == "IBOVESPA"
                            and col_target == "fechamento"
                            and not eventos_ibov_extremos.empty
                        ):
                            hover_texts = []
                            for _, row_ev in eventos_ibov_extremos.iterrows():
                                dt_str = row_ev["data_pregao"].strftime("%d/%m/%Y")
                                g_min = row_ev["data_pregao"].strftime("%m/%d/%Y")
                                g_max = (
                                    row_ev["data_pregao"] + pd.Timedelta(days=1)
                                ).strftime("%m/%d/%Y")
                                link_news = f"https://www.google.com/search?q=Ibovespa&tbm=nws&tbs=cdr:1,cd_min:{g_min},cd_max:{g_max}"
                                hover_texts.append(
                                    f"<b>⚠️ ALERTA IBOVESPA ({dt_str})</b><br>"
                                    f"Variação: <b>{row_ev['var_pct']:+.2f}%</b><br>"
                                    f"<a href='{link_news}' target='_blank' style='color:#ffeb3b;'>🔗 Clique aqui para abrir notícias do dia</a>"
                                )

                            fig.add_trace(
                                go.Scatter(
                                    x=eventos_ibov_extremos["data_pregao"],
                                    y=eventos_ibov_extremos["fechamento"],
                                    mode="markers",
                                    name=f"Alerta IBOV (≥{gatilho_ibov}%)",
                                    yaxis="y2",
                                    marker=dict(
                                        symbol="star",
                                        size=15,
                                        color="#ff0000",
                                        line=dict(width=1.5, color="#ffffff"),
                                    ),
                                    text=hover_texts,
                                    hoverinfo="text",
                                )
                            )

                return tem_secundario

            # --- GRÁFICO 1: VOLUME ---
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
            adicionar_linhas_dinamicas(fig_vol, df_acao, "data_pregao")
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
                hovermode="closest",
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

            # --- GRÁFICO 2: FLUXO DE INVESTIDORES ---
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
                adicionar_linhas_dinamicas(fig_fluxo, df_fluxo, "data_pregao")
                fig_fluxo.update_layout(
                    xaxis_title="Data",
                    yaxis=dict(title="Saldo Líquido (R$)"),
                    yaxis2=(
                        dict(
                            title="Pontos / Cotação",
                            overlaying="y",
                            side="right",
                        )
                        if tem_y2_fluxo
                        else None
                    ),
                    margin=dict(l=20, r=20, t=30, b=20),
                    hovermode="closest",
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

            # --- GRÁFICO 3: PREÇO MÉDIO ---
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
            adicionar_linhas_dinamicas(fig_preco, df_acao, "data_pregao")
            fig_preco.update_layout(
                xaxis_title="Data",
                yaxis=dict(title=f"Preço Médio {ticker_selecionado} (R$)"),
                yaxis2=(
                    dict(
                        title="Pontos / Cotação", overlaying="y", side="right"
                    )
                    if tem_y2_preco
                    else None
                ),
                margin=dict(l=20, r=20, t=30, b=20),
                hovermode="closest",
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
            # --- EXPANDER FECHADO: NOTÍCIAS DO IBOVESPA LOGO ABAIXO DO PREÇO MÉDIO ---
            with st.expander(
                    f"📰 Alertas e Notícias do IBOVESPA (Variação ≥ {gatilho_ibov}%)",
                    expanded=False,
            ):
                if not eventos_ibov_extremos.empty:
                    abas_datas = [
                        f"⭐ {row['data_pregao'].strftime('%d/%m/%Y')} ({row['var_pct']:+.2f}%)"
                        for _, row in eventos_ibov_extremos.iterrows()
                    ]
                    tabs = st.tabs(abas_datas)

                    for tab, (_, row_ev) in zip(
                            tabs, eventos_ibov_extremos.iterrows()
                    ):
                        with tab:
                            dt_ev = row_ev["data_pregao"]
                            dt_str = dt_ev.strftime("%d/%m/%Y")
                            st.info(
                                f"O **IBOVESPA** registrou variação de **{row_ev['var_pct']:+.2f}%** "
                                f"e fechou aos **{row_ev['fechamento']:,.0f} pontos** em **{dt_str}**."
                            )

                            noticias = buscar_noticias_ibovespa(dt_ev)
                            if noticias:
                                for n in noticias:
                                    st.markdown(
                                        f"#### 🔗 [{n['titulo']}]({n['link']})"
                                    )
                                    if n["publicado"]:
                                        st.caption(
                                            f"🕒 Publicado em: {n['publicado']}"
                                        )
                            else:
                                g_min = dt_ev.strftime("%m/%d/%Y")
                                g_max = (
                                        dt_ev + pd.Timedelta(days=1)
                                ).strftime("%m/%d/%Y")
                                url_gnews = f"https://www.google.com/search?q=Ibovespa&tbm=nws&tbs=cdr:1,cd_min:{g_min},cd_max:{g_max}"
                                st.markdown(
                                    f"#### 🔗 [Abrir manchetes do IBOVESPA no Google News para {dt_str}]({url_gnews})"
                                )
                else:
                    st.info(
                        f"Nenhuma variação diária do **IBOVESPA** atingiu **±{gatilho_ibov}%** no intervalo selecionado. "
                        f"(Dica: reduza o valor de 'Alerta de Variação IBOVESPA (%)' na barra lateral para visualizar dias com oscilações menores)."
                    )


            # --- GRÁFICO 4: ABERTURA VS FECHAMENTO ---
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
            adicionar_linhas_dinamicas(fig_abe_ult, df_acao, "data_pregao")
            fig_abe_ult.update_layout(
                xaxis_title="Data",
                yaxis=dict(title="Preço (R$)"),
                yaxis2=(
                    dict(
                        title="Pontos / Cotação", overlaying="y", side="right"
                    )
                    if tem_y2_abe_ult
                    else None
                ),
                margin=dict(l=20, r=20, t=30, b=20),
                hovermode="closest",
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

            # --- DETALHAMENTO DIÁRIO ---
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
            else:
                st.warning(
                    f"Não houve pregão registrado para **{ticker_selecionado}** no dia {data_detalhe.strftime('%d/%m/%Y')}."
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