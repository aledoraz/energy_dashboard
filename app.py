import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
from io import BytesIO

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

# --- FUNZIONE PER SCARICARE I DATI ---
def get_data():
    api_key = st.secrets["API_KEY"]  # Usa la chiave API da secrets
    base_url = "https://api.ember-energy.org"

    query_url = (
        f"{base_url}/v1/electricity-generation/monthly"
        + f"?entity_code=ITA,DEU,FRA,CHN,USA"
        + f"&start_date=2014-01&end_date=2025-01"
        + f"&series=Bioenergy,Coal,Gas,Hydro,Nuclear,Other fossil,Other renewables,Solar,Wind"
        + f"&is_aggregate_series=false&include_all_dates_value_range=true&api_key={api_key}"
    )

    response = requests.get(query_url)
    if response.status_code == 200:
        return pd.DataFrame(response.json()["data"])
    else:
        st.error(f"Errore API: {response.status_code}")
        return pd.DataFrame()

# --- SCARICAMENTO DATI ---
df = get_data()

if not df.empty:
    st.success("Dati scaricati con successo!")

    # --- FILTRARE E PREPARARE I DATI ---
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['date'].dt.year > 2014]
    
    # Creiamo le nuove categorie
    green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables"]
    brown_sources = ["Coal", "Gas", "Nuclear", "Other fossil"]
    
    df["total"] = df.groupby(["entity_code", "date"])["generation_gwh"].transform("sum")
    df["total_green"] = df[df["series"].isin(green_sources)].groupby(["entity_code", "date"])["generation_gwh"].transform("sum")
    df["total_brown"] = df[df["series"].isin(brown_sources)].groupby(["entity_code", "date"])["generation_gwh"].transform("sum")
    
    # --- TABELLA INTERATTIVA CON FILTRI ---
    st.subheader("📊 Dati Grezzi (Filtrabili)")
    filtro_paese = st.multiselect("Seleziona Paesi:", options=df["entity_code"].unique(), default=df["entity_code"].unique())
    filtro_fonte = st.multiselect("Seleziona Fonte Energetica:", options=df["series"].unique(), default=df["series"].unique())

    df_filtrato = df[df["entity_code"].isin(filtro_paese) & df["series"].isin(filtro_fonte)]
    st.write(df_filtrato.head(10))

    # --- OPZIONE DI DOWNLOAD DEL DATASET ---
    st.download_button("📥 Scarica Dati Filtrati", df_filtrato.to_csv(index=False), "dati_filtrati.csv", "text/csv")
    st.download_button("📥 Scarica Tutti i Dati", df.to_csv(index=False), "dati_completi.csv", "text/csv")

    # --- GRAFICO INTERATTIVO ---
    st.subheader("📈 Quota di Generazione Elettrica per Fonte (Selezione Paese)")
    paese_scelto = st.selectbox("Seleziona un paese:", df["entity_code"].unique())

    df_pivot = df.pivot_table(index='date', columns=['entity_code', 'series'], values='share_of_generation_pct', aggfunc='sum')
    df_grafico = df_pivot[paese_scelto].dropna()
    
    color_map = {
        "Coal": "#4d4d4d", "Other fossil": "#a6a6a6", "Gas": "#b5651d",
        "Nuclear": "#ffdd44", "Solar": "#87CEEB", "Wind": "#aec7e8",
        "Hydro": "#1f77b4", "Bioenergy": "#2ca02c", "Other renewables": "#17becf"
    }
    
    fig, ax = plt.subplots(figsize=(10, 5))
    df_grafico.plot(kind='area', stacked=True, alpha=0.7, color=[color_map.get(c, "#333333") for c in df_grafico.columns], ax=ax)
    ax.set_title(f"Quota di Generazione - {paese_scelto}")
    ax.set_ylabel('%')
    plt.xlabel('Anno')
    plt.tight_layout()
    st.pyplot(fig)
    
    # --- OPZIONE DI DOWNLOAD DEL GRAFICO ---
    buffer = BytesIO()
    fig.savefig(buffer, format="png")
    buffer.seek(0)
    st.download_button("📥 Scarica Grafico", buffer, file_name="grafico_generazione.png", mime="image/png")

    # --- NUOVA TABELLA: PRODUZIONE ULTIMO MESE/SEMESTRE ---
    st.subheader("📊 Produzione Elettrica per Fonte - Ultimo Mese & Ultimo Semestre")
    ultimo_mese = df["date"].max()
    ultimo_semestre = ultimo_mese - pd.DateOffset(months=5)
    
    df_ultimo_mese = df[df["date"] == ultimo_mese]
    df_ultimo_semestre = df[df["date"] >= ultimo_semestre].groupby(["entity_code", "series"])["generation_gwh"].sum().reset_index()
    
    df_yoy_mese = df[df["date"] == (ultimo_mese - pd.DateOffset(years=1))]
    df_yoy_semestre = df[df["date"] >= (ultimo_semestre - pd.DateOffset(years=1))].groupby(["entity_code", "series"])["generation_gwh"].sum().reset_index()
    
    df_variation_mese = df_ultimo_mese.merge(df_yoy_mese, on=["entity_code", "series"], suffixes=("_new", "_old"))
    df_variation_mese["YoY %"] = ((df_variation_mese["generation_gwh_new"] - df_variation_mese["generation_gwh_old"]) / df_variation_mese["generation_gwh_old"]) * 100
    
    st.write(df_variation_mese.style.applymap(lambda x: "color: red" if x < 0 else "color: green", subset=["YoY %"]))
    st.download_button("📥 Scarica Dati Filtrati", df_variation_mese.to_csv(index=False), "dati_variation.csv", "text/csv")

else:
    st.warning("Nessun dato disponibile!")
