import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import time
from io import BytesIO

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

import time

st.title("Caricamento in corso...")

# Placeholder per il testo e progress bar
status_text = st.empty()
progress_bar = st.progress(0)

for i in range(100):
    # Aggiorna il testo e la progress bar
    status_text.text(f"Caricamento in corso... {i + 1}%")
    progress_bar.progress(i + 1)
    time.sleep(0.05)

status_text.text("Caricamento completato!")
def get_data():
    api_key = st.secrets["API_KEY"]
    base_url = "https://api.ember-energy.org"
    query_url = (
        f"{base_url}/v1/electricity-generation/monthly"
        + f"?entity_code=ITA,DEU,FRA,CHN,USA,AUS,CAN,JPN"
        + f"&start_date=2014-01&end_date=2025-01"
        + f"&series=Bioenergy,Coal,Gas,Hydro,Nuclear,Other fossil,Other renewables,Solar,Wind"
        + f"&is_aggregate_series=false&include_all_dates_value_range=true&api_key={api_key}"
    )
    
    for attempt in range(5):
        response = requests.get(query_url)
        if response.status_code == 200:
            data = response.json()
            if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                return pd.DataFrame(data["data"])
            else:
                st.warning("Dati API ricevuti ma vuoti o in formato inatteso.")
                return pd.DataFrame()
        elif response.status_code == 500:
            time.sleep(20)
        else:
            return pd.DataFrame()
    
    return pd.DataFrame()

# --- SCARICAMENTO DATI ---
df = get_data()

if not df.empty:
    # --- PREPARAZIONE DEI DATI ---
    df = df[["entity_code", "date", "series", "generation_twh", "share_of_generation_pct"]]
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%m-%Y')
    df = df[df['date'] >= '01-2014']
    df["generation_twh"] = df["generation_twh"].round(2)
    
    green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables", "Nuclear"]
    brown_sources = ["Coal", "Gas", "Other fossil"]
    
    df_total = df.groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total["series"] = "Total"
    df_total["share_of_generation_pct"] = 100.0
    
    df_total_green = df[df["series"].isin(green_sources)].groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total_green["series"] = "Green"
    df_total_green["share_of_generation_pct"] = (df_total_green["generation_twh"] / df_total["generation_twh"]).round(2) * 100
    
    df_total_brown = df[df["series"].isin(brown_sources)].groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total_brown["series"] = "Brown"
    df_total_brown["share_of_generation_pct"] = (df_total_brown["generation_twh"] / df_total["generation_twh"]).round(2) * 100
    
    df = pd.concat([df, df_total, df_total_green, df_total_brown], ignore_index=True)
    df["share_of_generation_pct"] = df["share_of_generation_pct"].round(2)
    
    df = df.rename(columns={
        "entity_code": "Country",
        "date": "Date",
        "series": "Source",
        "generation_twh": "Generation (TWh)",
        "share_of_generation_pct": "Share (%)"
    })


    df = df.sort_values(by=["Country", "Source", "Date"])
    df["Date"] = pd.to_datetime(df["Date"], format='%m-%Y')
    
    # Creiamo una copia del dataset con l'anno spostato di +1 per il confronto
    df_last_year = df.copy()
    df_last_year["Date"] = df_last_year["Date"] + pd.DateOffset(years=1)
    df = df.merge(df_last_year[["Country", "Source", "Date", "Generation (TWh)"]], 
                  on=["Country", "Source", "Date"], 
                  suffixes=("", "_last_year"), 
                  how="left")
    df["YoY Variation (%)"] = ((df["Generation (TWh)"] - df["Generation (TWh)_last_year"]) / df["Generation (TWh)_last_year"]) * 100
    df["YoY Variation (%)"] = df["YoY Variation (%)"].round(2)
    df.drop(columns=["Generation (TWh)_last_year"], inplace=True)
    df_yoy = df[["Country", "Date", "Source", "Generation (TWh)", "Share (%)", "YoY Variation (%)"]]
    
    # Converti la colonna Date in stringa ed estrai i primi 10 caratteri
    df_yoy["Date"] = df_yoy["Date"].astype(str).str[:10]
    
    # --- VISUALIZZAZIONE ---
    color_map = {
            "Coal": "#4d4d4d",
            "Other fossil": "#a6a6a6",
            "Gas": "#b5651d",
            "Nuclear": "#ffdd44",
            "Solar": "#87CEEB",
            "Wind": "#aec7e8",
            "Hydro": "#1f77b4",
            "Bioenergy": "#2ca02c",
            "Other renewables": "#17becf"
        }
        
    col1, col2 = st.columns([2, 3])
        
    with col1:
            st.subheader("📊 Produzione Elettricità YoY")
            paese_scelto = st.selectbox("Seleziona un paese:", df["Country"].unique())
            df_paese = df_yoy[df_yoy["Country"] == paese_scelto]
            st.write(df_paese.style.format({"Generation (TWh)": "{:.2f}", "Share (%)": "{:.2f}", "YoY Variation (%)": "{:.2f}"}))
            st.download_button("📥 Scarica Dati", df_paese.to_csv(index=False), "dati_variation.csv", "text/csv")
        
    with col2:
            st.subheader("📈 Quota di Generazione Elettrica per Fonte")
            fig, ax = plt.subplots(figsize=(10, 5))
            df_plot = df_paese[~df_paese["Source"].isin(["Total", "Green", "Brown"])].pivot(index='Date', columns='Source', values='Share (%)')
            df_plot.plot(kind='area', stacked=True, alpha=0.7, ax=ax, color=[color_map[s] for s in df_plot.columns])
            ax.set_title(f"Quota di Generazione - {paese_scelto}")
            ax.set_ylabel('%')
            ax.set_ylim(0, 100)
            plt.xlabel('Anno')
            plt.tight_layout()
            st.pyplot(fig)
else:
    st.warning("Nessun dato disponibile!")
