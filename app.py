import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import time
from datetime import datetime
from io import BytesIO

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

def get_data():
    api_key = st.secrets["API_KEY"]
    base_url = "https://api.ember-energy.org"
    query_url = (
        f"{base_url}/v1/electricity-generation/monthly"
        + f"?start_date=2014-01&end_date=2025-01"
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
df_raw = get_data()

if not df_raw.empty:
    # --- PREPARAZIONE DATI ---
    df = df_raw[["entity_code", "date", "series", "generation_twh", "share_of_generation_pct"]].copy()
    df['Date'] = pd.to_datetime(df['date'])  # Conversione esplicita delle date
    df = df.rename(columns={"entity_code": "Country", "series": "Source",
                            "generation_twh": "Generation (TWh)", "share_of_generation_pct": "Share (%)"})
    
    # Creazione aggregati
    groups = {
        "EUR": ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"],
        "G20": ["ARG", "AUS", "BRA", "CAN", "CHN", "FRA", "DEU", "IND", "IDN", "ITA", "JPN", "MEX", "RUS", "SAU", "ZAF", "KOR", "TUR", "GBR", "USA"],
        "G7": ["CAN", "FRA", "DEU", "ITA", "JPN", "GBR", "USA"],
        "G9": ["CAN", "FRA", "DEU", "ITA", "JPN", "GBR", "USA", "CHN", "IND"],
        "World": df["Country"].unique().tolist()
    }
    
    for group, countries in groups.items():
        df_group = df[df["Country"].isin(countries)].groupby(["Date", "Source"], as_index=False)["Generation (TWh)"].sum()
        df_group["Country"] = group
        df = pd.concat([df, df_group], ignore_index=True)
    
    # Ordinare i dati per data
    df = df.sort_values(by=["Country", "Date"])
    
    # Calcolo Y-o-Y Variation
    df["Y-o-Y Variation (%)"] = df.groupby(["Country", "Source"])["Generation (TWh)"].pct_change(periods=12) * 100
    df["Y-o-Y Variation (%)"] = df["Y-o-Y Variation (%)"].round(2)
    
    # --- INTERFACCIA UTENTE: TABELLA ---
    st.subheader("Tabella Produzione Elettrica")

    table_view = st.radio("Visualizzazione dati:", ("Mensile", "Annuale"))

    all_countries = sorted(df["Country"].dropna().unique())
    countries_options = ["All"] + all_countries
    table_countries = st.multiselect("Seleziona paese/i per la tabella:", countries_options, default=["All"])

    all_sources = sorted(df["Source"].unique())
    sources_options = ["All"] + all_sources
    table_sources = st.multiselect("Seleziona fonte/e per la tabella:", sources_options, default=["All"])

    df_table = df[["Country", "Date", "Source", "Generation (TWh)", "Share (%)", "Y-o-Y Variation (%)"]].copy()

    st.dataframe(df_table, use_container_width=True)
    st.download_button("📥 Scarica Dati Tabella", df_table.to_csv(index=False), "dati_tabella.csv", "text/csv")

    # --- GRAFICO ---
    st.subheader("Grafico Quota di Generazione Elettrica per Fonte")
    graph_country = st.selectbox("Seleziona un paese o un gruppo per il grafico:", all_countries)
    df_graph = df[df["Country"] == graph_country]
    if df_graph.empty:
        st.warning(f"Nessun dato disponibile per {graph_country}.")
    else:
        df_graph = df_graph.pivot(index='Date', columns='Source', values='Share (%)')
        fig, ax = plt.subplots(figsize=(10, 5))
        df_graph.plot(kind='area', stacked=True, alpha=0.7, ax=ax)
        ax.set_title(f"Quota di Generazione - {graph_country}")
        st.pyplot(fig)
        
        img_buffer = BytesIO()
        fig.savefig(img_buffer, format="png", dpi=300, bbox_inches="tight")
        img_buffer.seek(0)

        st.download_button("📥 Scarica il grafico", img_buffer, file_name=f"grafico_{graph_country}.png", mime="image/png")
