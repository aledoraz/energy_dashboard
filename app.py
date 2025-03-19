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
    
    for attempt in range(3):  # 3 tentativi di richiesta
        response = requests.get(query_url)
        if response.status_code == 200:
            data = response.json()
            if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                return pd.DataFrame(data["data"])
            else:
                st.warning("Dati API ricevuti ma vuoti o in formato inatteso.")
                return pd.DataFrame()
        elif response.status_code == 500:
            st.warning(f"Tentativo {attempt+1}/3: Il server API ha restituito errore 500. Riprovo tra 5 secondi...")
            time.sleep(5)  # Attendere 5 secondi prima di ritentare
        else:
            st.error(f"Errore API: {response.status_code}")
            return pd.DataFrame()
    
    st.error("Errore persistente API 500: il server non risponde. Riprova più tardi.")
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
else:
    st.warning("Nessun dato disponibile!")
