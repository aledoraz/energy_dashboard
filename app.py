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
    df["generation_twh"] = df["generation_twh"].round(2)
    
    # --- FILTRARE E PREPARARE I DATI ---
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%m-%Y')
    df = df[df['date'] >= '2014-01']
    
    # Creiamo le nuove categorie
    green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables", "Nuclear"]
    brown_sources = ["Coal", "Gas", "Other fossil"]
    
    df_total = df.groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total["series"] = "Total"
    df_total_green = df[df["series"].isin(green_sources)].groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total_green["series"] = "Green"
    df_total_brown = df[df["series"].isin(brown_sources)].groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total_brown["series"] = "Brown"
    df = pd.concat([df, df_total, df_total_green, df_total_brown], ignore_index=True)
    
    df["share_of_generation_pct"] = df["share_of_generation_pct"].round(2)
    
    # --- LAYOUT DELLA DASHBOARD ---
    col1, col2 = st.columns([2, 3])
    
    with col1:
        st.subheader("📊 Produzione Elettricità YoY")
        paese_scelto = st.selectbox("Seleziona un paese:", df["entity_code"].unique())
        df_paese = df[df["entity_code"] == paese_scelto]
        
        ultimo_mese = df_paese["date"].max()
        df_ultimo_mese = df_paese[df_paese["date"] == ultimo_mese]
        df_yoy_mese = df_paese[df_paese["date"] == (pd.to_datetime(ultimo_mese, format='%m-%Y') - pd.DateOffset(years=1)).strftime('%m-%Y')]
        
        df_variation_mese = df_ultimo_mese.merge(df_yoy_mese, on=["entity_code", "series"], suffixes=("_new", "_old"))
        df_variation_mese["YoY Variation"] = ((df_variation_mese["generation_twh_new"] - df_variation_mese["generation_twh_old"]) / df_variation_mese["generation_twh_old"]) * 100
        df_variation_mese = df_variation_mese.rename(columns={
            "entity_code": "Country",
            "date": "Date",
            "series": "Source",
            "generation_twh_new": "Generation (TWh)",
            "share_of_generation_pct_new": "Share (%)"
        })
        df_variation_mese = df_variation_mese[["Country", "Date", "Source", "Generation (TWh)", "Share (%)", "YoY Variation"]]
        
        st.write(df_variation_mese.style.applymap(lambda x: "color: red" if x < 0 else "color: green", subset=["YoY Variation"]))
        st.download_button("📥 Scarica Dati Filtrati", df_variation_mese.to_csv(index=False), "dati_variation.csv", "text/csv")
        st.download_button("📥 Scarica Dataset Completo", df.to_csv(index=False), "dati_completi.csv", "text/csv")
    
    with col2:
        st.subheader("📈 Quota di Generazione Elettrica per Fonte")
        df_pivot = df_paese.pivot_table(index='date', columns='series', values='generation_twh', aggfunc='sum')
        df_pivot = df_pivot.drop(columns=["Total", "Green", "Brown"], errors='ignore')
        fig, ax = plt.subplots(figsize=(10, 5))
        df_pivot.plot(kind='area', stacked=True, alpha=0.7, ax=ax)
        ax.set_title(f"Quota di Generazione - {paese_scelto}")
        ax.set_ylabel('%')
        plt.xlabel('Anno')
        plt.tight_layout()
        st.pyplot(fig)
        buffer = BytesIO()
        fig.savefig(buffer, format="png")
        buffer.seek(0)
        st.download_button("📥 Scarica Grafico", buffer, file_name=f"grafico_generazione_{paese_scelto}.png", mime="image/png")
else:
    st.warning("Nessun dato disponibile!")
