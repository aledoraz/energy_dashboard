import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt

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
    df_pivot = df.pivot_table(index='date', columns=['entity_code', 'series'], values='share_of_generation_pct', aggfunc='sum')

    # --- VISUALIZZAZIONE TABELLA ---
    st.subheader("📊 Dati Grezzi")
    st.write(df.head())

    # --- GRAFICO AREA STACKED ---
    color_map = {
        "Coal": "#4d4d4d", "Other fossil": "#a6a6a6", "Gas": "#b5651d",
        "Nuclear": "#ffdd44", "Solar": "#87CEEB", "Wind": "#aec7e8",
        "Hydro": "#1f77b4", "Bioenergy": "#2ca02c", "Other renewables": "#17becf"
    }
    order = ["Coal", "Other fossil", "Gas", "Nuclear", "Solar", "Wind", "Hydro", "Bioenergy", "Other renewables"]

    st.subheader("📈 Quota di Generazione Elettrica per Fonte")

    fig, axes = plt.subplots(5, 1, figsize=(12, 12), sharex=True)
    for idx, country in enumerate(['ITA', 'DEU', 'FRA', 'CHN', 'USA']):
        ax = axes[idx]
        available_categories = [cat for cat in order if cat in df_pivot[country].columns]
        df_ordered = df_pivot[country][available_categories]
        colors = [color_map[cat] for cat in available_categories]
        df_ordered.plot(kind='area', stacked=True, ax=ax, alpha=0.7, color=colors)
        ax.set_title(f'Quota di Generazione - {country}')
        ax.set_ylabel('%')
    plt.xlabel('Anno')
    plt.tight_layout()
    st.pyplot(fig)

else:
    st.warning("Nessun dato disponibile!")
