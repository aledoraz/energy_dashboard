import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import time
from io import BytesIO

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

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
    st.success("Dati scaricati con successo!")

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
    
    df = df[["entity_code", "date", "series", "generation_twh", "share_of_generation_pct"]]
    df.rename(columns={
        "entity_code": "Country",
        "date": "Date",
        "series": "Source",
        "generation_twh": "Generation (TWh)",
        "share_of_generation_pct": "Share (%)"
    }, inplace=True)
    
    # --- CALCOLO VARIAZIONE YOY ---
    df_yoy = df.copy()
    df_yoy_prev = df_yoy.copy()
    df_yoy_prev["Date"] = pd.to_datetime(df_yoy_prev["Date"], format='%m-%Y') - pd.DateOffset(years=1)
    df_yoy_prev["Date"] = df_yoy_prev["Date"].dt.strftime('%m-%Y')
    df_yoy_prev = df_yoy_prev[["Country", "Date", "Source", "Generation (TWh)"]]
    
    df_yoy = df_yoy.merge(df_yoy_prev, on=["Country", "Source", "Date"], suffixes=("", "_prev"), how="left")
    df_yoy["YoY Variation"] = ((df_yoy["Generation (TWh)"] - df_yoy["Generation (TWh)_prev"]) / df_yoy["Generation (TWh)_prev"]) * 100
    df_yoy.loc[df_yoy["Generation (TWh)_prev"].isna(), "YoY Variation"] = None
    df_yoy = df_yoy[["Country", "Date", "Source", "Generation (TWh)", "Share (%)", "YoY Variation"]]
    
    col1, col2 = st.columns([2, 3])
    
    with col1:
        st.subheader("📊 Produzione Elettricità YoY")
        paese_scelto = st.selectbox("Seleziona un paese:", df["Country"].unique())
        df_paese = df_yoy[df_yoy["Country"] == paese_scelto]
        st.write(df_paese.style.format({"Generation (TWh)": "{:.2f}", "Share (%)": "{:.2f}", "YoY Variation": "{:.2f}"}))
        st.download_button("📥 Scarica Dati", df_paese.to_csv(index=False), "dati_variation.csv", "text/csv")
    
    with col2:
        st.subheader("📈 Quota di Generazione Elettrica per Fonte")
        fig, ax = plt.subplots(figsize=(10, 5))
        df_plot = df_paese[~df_paese["Source"].isin(["Total", "Green", "Brown"])].pivot(index='Date', columns='Source', values='Share (%)')
        df_plot.plot(kind='area', stacked=True, alpha=0.7, ax=ax)
        ax.set_title(f"Quota di Generazione - {paese_scelto}")
        ax.set_ylabel('%')
        ax.set_ylim(0, 100)
        plt.xlabel('Anno')
        plt.tight_layout()
        st.pyplot(fig)
else:
    st.warning("Nessun dato disponibile!")
