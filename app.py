import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import time
from io import BytesIO

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

# --- FUNZIONE PER SCARICARE I DATI CON RETRY ---
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
    
    for attempt in range(5):  # 5 tentativi di richiesta
        response = requests.get(query_url)
        if response.status_code == 200:
            data = response.json()
            if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                return pd.DataFrame(data["data"])
            else:
                st.warning("Dati API ricevuti ma vuoti o in formato inatteso.")
                return pd.DataFrame()
        elif response.status_code == 500:
            st.warning(f"Tentativo {attempt+1}/5: Il server API ha restituito errore 500. Riprovo tra 20 secondi...")
            time.sleep(20)  # Attendere 20 secondi prima di ritentare
        else:
            st.error(f"Errore API: {response.status_code}")
            return pd.DataFrame()
    
    st.error("Errore persistente API 500: il server non risponde. Riprova più tardi.")
    return pd.DataFrame()

# --- SCARICAMENTO DATI ---
df = get_data()

if not df.empty:
    st.success("Dati scaricati con successo!")

    # --- VERIFICA COLONNE PRIMA DI PROCEDERE ---
    if "generation_twh" not in df.columns:
        st.error("Errore: La colonna 'generation_twh' non è presente nei dati ricevuti. Verifica la struttura dell'API.")
        st.stop()
    
    # Convertiamo TWh in GWh (1 TWh = 1000 GWh)
    df["generation_gwh"] = df["generation_twh"] * 1000
    
    # --- FILTRARE E PREPARARE I DATI ---
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['date'].dt.year > 2014]
    
    # Creiamo le nuove categorie
    green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables"]
    brown_sources = ["Coal", "Gas", "Nuclear", "Other fossil"]
    
    df["total"] = df.groupby(["entity_code", "date"])["generation_gwh"].transform("sum")
    df["total_green"] = df[df["series"].isin(green_sources)].groupby(["entity_code", "date"])["generation_gwh"].transform("sum")
    df["total_brown"] = df[df["series"].isin(brown_sources)].groupby(["entity_code", "date"])["generation_gwh"].transform("sum")
    
    # --- TABELLA YOY ---
    st.subheader("📊 Produzione Elettricità YoY")
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
    
    # --- GRAFICO INTERATTIVO ---
    st.subheader("📈 Quota di Generazione Elettrica per Fonte")
    paese_scelto = st.selectbox("Seleziona un paese:", df["entity_code"].unique())
    df_pivot = df.pivot_table(index='date', columns=['entity_code', 'series'], values='generation_gwh', aggfunc='sum')
    df_grafico = df_pivot[paese_scelto].dropna()
    fig, ax = plt.subplots(figsize=(10, 5))
    df_grafico.plot(kind='area', stacked=True, alpha=0.7, ax=ax)
    ax.set_title(f"Quota di Generazione - {paese_scelto}")
    ax.set_ylabel('%')
    plt.xlabel('Anno')
    plt.tight_layout()
    st.pyplot(fig)
    buffer = BytesIO()
    fig.savefig(buffer, format="png")
    buffer.seek(0)
    st.download_button("📥 Scarica Grafico", buffer, file_name="grafico_generazione.png", mime="image/png")
else:
    st.warning("Nessun dato disponibile!")
