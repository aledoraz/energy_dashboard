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
    
    # Ordinare i dati per data
    df = df.sort_values(by=["Country", "Date"])

    # --- INTERFACCIA UTENTE: TABELLA ---
    st.subheader("Tabella Produzione Elettrica")

    table_view = st.radio("Visualizzazione dati:", ("Mensile", "Annuale"))

    all_countries = sorted(df["Country"].dropna().unique())
    countries_options = ["All"] + all_countries
    table_countries = st.multiselect("Seleziona paese/i per la tabella:", countries_options, default=["All"])

    all_sources = sorted(df["Source"].unique())
    sources_options = ["All"] + all_sources
    table_sources = st.multiselect("Seleziona fonte/e per la tabella:", sources_options, default=["All"])

    if table_view == "Mensile":
        df_table = df.copy()
        df_table["Year"] = df_table["Date"].dt.year
    else:
        df_table = df.copy()
        df_table["Year"] = df_table["Date"].dt.year

    years_available = sorted(df_table["Year"].unique())
    years_options = ["All"] + years_available
    table_years = st.multiselect("Seleziona anno/i per la tabella:", years_options, default=["All"])

    filter_countries = all_countries if "All" in table_countries else table_countries
    filter_sources = all_sources if "All" in table_sources else table_sources
    filter_years = years_available if "All" in table_years else table_years

    df_table = df_table[
        (df_table["Country"].isin(filter_countries)) &
        (df_table["Source"].isin(filter_sources)) &
        (df_table["Year"].isin(filter_years))
    ]

    st.dataframe(df_table, use_container_width=True)
    st.download_button("📥 Scarica Dati Tabella", df_table.to_csv(index=False), "dati_tabella.csv", "text/csv")
    st.download_button("Scarica DB Completo", df_raw.to_csv(index=False), "db_completo.csv", "text/csv")

    # --- GRAFICO STATICO CON MATPLOTLIB ---
    st.subheader("Grafico Quota di Generazione Elettrica per Fonte")
    available_countries = sorted([str(c) for c in df["Country"].dropna().unique()] + ["EUR", "G20", "G7", "G9", "World"])

    graph_country = st.selectbox("Seleziona un paese o un gruppo per il grafico:", available_countries)

    df_graph = df[df["Country"] == graph_country]

    if df_graph.empty:
        st.warning(f"Nessun dato disponibile per {graph_country}.")
    else:
        # Ordinare i dati per data nel grafico
        df_graph = df_graph.sort_values(by=["Date"])

        df_graph_plot = df_graph[~df_graph["Source"].isin(["Total", "Green", "Brown"])]
        df_plot = df_graph_plot.pivot(index='Date', columns='Source', values='Share (%)')

        color_map = {
            "Coal": "#4d4d4d", "Other fossil": "#a6a6a6", "Gas": "#b5651d",
            "Nuclear": "#ffdd44", "Solar": "#87CEEB", "Wind": "#aec7e8",
            "Hydro": "#1f77b4", "Bioenergy": "#2ca02c", "Other renewables": "#17becf"
        }

        fig, ax = plt.subplots(figsize=(10, 5))
        df_plot.plot(kind='area', stacked=True, alpha=0.7, ax=ax, color=[color_map.get(s, "#cccccc") for s in df_plot.columns])
        ax.legend(loc='upper left')
        ax.set_title(f"Quota di Generazione - {graph_country}")
        ax.set_ylabel('%')
        ax.set_ylim(0, 100)
        ax.set_xlabel('Anno')
        plt.xticks(rotation=45)  # Ruota le date per migliorare la leggibilità
        plt.tight_layout()

        # --- VISUALIZZAZIONE GRAFICO ---
        st.pyplot(fig)

        # --- PULSANTE DOWNLOAD GRAFICO ---
        img_buffer = BytesIO()
        fig.savefig(img_buffer, format="png", dpi=300, bbox_inches="tight")
        img_buffer.seek(0)

        st.download_button(
            label="📥 Scarica il grafico",
            data=img_buffer,
            file_name=f"grafico_{graph_country}.png",
            mime="image/png"
        )
else:
    st.warning("Nessun dato disponibile!")
