import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import time
from datetime import datetime
from io import BytesIO

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

# Calcola la data finale come il mese precedente a oggi
today = datetime.today()
if today.month == 1:
    end_year = today.year - 1
    end_month = 12
else:
    end_year = today.year
    end_month = today.month - 1
end_date = f"{end_year}-{end_month:02d}"
start_date = "2010-01"

def get_data():
    api_key = st.secrets["API_KEY"]
    base_url = "https://api.ember-energy.org"
    # Nota: non viene più passato il parametro entity_code per ottenere tutti i paesi
    query_url = (
        f"{base_url}/v1/electricity-generation/monthly"
        f"?start_date={start_date}"
        f"&end_date={end_date}"
        f"&series=Bioenergy,Coal,Gas,Hydro,Nuclear,Other fossil,Other renewables,Solar,Wind"
        f"&is_aggregate_series=false&include_all_dates_value_range=true&api_key={api_key}"
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
    # --- PREPARAZIONE DATI INIZIALI (dati mensili grezzi) ---
    # Seleziona le colonne rilevanti e converti la data in datetime
    df = df_raw[["entity_code", "date", "series", "generation_twh", "share_of_generation_pct"]].copy()
    df['date'] = pd.to_datetime(df['date'])
    # Considera solo dati dal 2000-01 in poi
    df = df[df['date'] >= pd.to_datetime("2000-01")]
    df["generation_twh"] = df["generation_twh"].round(2)
    
    # Rinomina le colonne per uniformità
    df = df.rename(columns={
        "entity_code": "Country",
        "date": "Date",
        "series": "Source",
        "generation_twh": "Generation (TWh)",
        "share_of_generation_pct": "Share (%)"
    })
    
    # Salva i dati individuali (non ancora aggregati) per il calcolo dei gruppi
    df_ind = df.copy()
    
    # Definizione delle fonti per aggregazioni di "Green" e "Brown"
    green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables", "Nuclear"]
    brown_sources = ["Coal", "Gas", "Other fossil"]
    
    # --- AGGREGATI PER OGNI COUNTRY (individuali) ---
    # Calcola "Total" per ogni country e data
    df_total = df.groupby(["Country", "Date"])["Generation (TWh)"].sum().reset_index()
    df_total["Source"] = "Total"
    df_total["Share (%)"] = 100.0

    # Calcola "Green"
    df_green = df[df["Source"].isin(green_sources)].groupby(["Country", "Date"])["Generation (TWh)"].sum().reset_index()
    df_green["Source"] = "Green"
    df_green = pd.merge(df_green, df_total[["Country", "Date", "Generation (TWh)"]], on=["Country", "Date"], suffixes=("", "_total"))
    df_green["Share (%)"] = ((df_green["Generation (TWh)"] / df_green["Generation (TWh)_total"]) * 100).round(2)
    df_green.drop(columns=["Generation (TWh)_total"], inplace=True)
    
    # Calcola "Brown"
    df_brown = df[df["Source"].isin(brown_sources)].groupby(["Country", "Date"])["Generation (TWh)"].sum().reset_index()
    df_brown["Source"] = "Brown"
    df_brown = pd.merge(df_brown, df_total[["Country", "Date", "Generation (TWh)"]], on=["Country", "Date"], suffixes=("", "_total"))
    df_brown["Share (%)"] = ((df_brown["Generation (TWh)"] / df_brown["Generation (TWh)_total"]) * 100).round(2)
    df_brown.drop(columns=["Generation (TWh)_total"], inplace=True)
    
    # Combina i dati individuali con gli aggregati per ogni country
    df = pd.concat([df, df_total, df_green, df_brown], ignore_index=True)
    
    # --- AGGREGATI DI GRUPPO ---
    # Definizione dei gruppi (si utilizzano codici ISO)
    eu_countries = ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"]
    g20_countries = ["ARG", "AUS", "BRA", "CAN", "CHN", "FRA", "DEU", "IND", "IDN", "ITA", "JPN", "MEX", "RUS", "SAU", "ZAF", "KOR", "TUR", "GBR", "USA"]
    g7_countries = ["CAN", "FRA", "DEU", "ITA", "JPN", "GBR", "USA"]
    g9_countries = ["CAN", "FRA", "DEU", "ITA", "JPN", "GBR", "USA", "CHN", "IND"]  # Definito come G7 + CHN e IND
    # World: tutti i paesi presenti nei dati individuali
    world_countries = df_ind["Country"].unique().tolist()
    
    def compute_group_aggregate(df_individual, group_name, countries_list):
        # Filtra i dati per i paesi del gruppo
        df_group = df_individual[df_individual["Country"].isin(countries_list)].copy()
        if df_group.empty:
            return pd.DataFrame()
        # Raggruppa per Date e Source per ottenere i valori individuali (raw)
        group_indiv = df_group.groupby(["Date", "Source"], as_index=False)["Generation (TWh)"].sum()
        group_indiv["Country"] = group_name
        # Calcola l'aggregato "Total" per il gruppo (somma di tutte le fonti raw per ogni Date)
        group_total = df_group.groupby("Date", as_index=False)["Generation (TWh)"].sum()
        group_total["Source"] = "Total"
        group_total["Country"] = group_name
        # Calcola "Green" e "Brown" per il gruppo
        group_green = df_group[df_group["Source"].isin(green_sources)].groupby("Date", as_index=False)["Generation (TWh)"].sum()
        group_green["Source"] = "Green"
        group_green["Country"] = group_name
        group_brown = df_group[df_group["Source"].isin(brown_sources)].groupby("Date", as_index=False)["Generation (TWh)"].sum()
        group_brown["Source"] = "Brown"
        group_brown["Country"] = group_name
        # Combina i risultati
        group_df = pd.concat([group_total, group_green, group_brown, group_indiv], ignore_index=True)
        group_df = group_df.drop_duplicates(subset=["Country", "Date", "Source"])
        # Calcola la quota: per ogni Date, la quota = (Generation / Total) * 100
        group_df["Share (%)"] = None
        for d in group_df["Date"].unique():
            tot = group_df[(group_df["Date"]==d) & (group_df["Source"]=="Total")]["Generation (TWh)"]
            if not tot.empty:
                tot_val = tot.iloc[0]
                group_df.loc[group_df["Date"]==d, "Share (%)"] = (group_df[group_df["Date"]==d]["Generation (TWh)"] / tot_val * 100).round(2)
        return group_df

    df_eur = compute_group_aggregate(df_ind, "EUR", eu_countries)
    df_g20 = compute_group_aggregate(df_ind, "G20", g20_countries)
    df_g7 = compute_group_aggregate(df_ind, "G7", g7_countries)
    df_g9 = compute_group_aggregate(df_ind, "G9", g9_countries)
    df_world = compute_group_aggregate(df_ind, "World", world_countries)
    
    # Aggiungi i gruppi al dataset principale
    df = pd.concat([df, df_eur, df_g20, df_g7, df_g9, df_world], ignore_index=True)
    df["Share (%)"] = df["Share (%)"].astype(float).round(2)
    
    # Ordina i dati
    df = df.sort_values(by=["Country", "Source", "Date"])
    
    # --- CALCOLO VARIAZIONE YOY (MESSILE) ---
    df_month = df.copy()
    df_last_year = df_month.copy()
    df_last_year["Date"] = df_last_year["Date"] + pd.DateOffset(years=1)
    df_month = df_month.merge(
        df_last_year[["Country", "Source", "Date", "Generation (TWh)"]],
        on=["Country", "Source", "Date"],
        suffixes=("", "_last_year"),
        how="left"
    )
    df_month["YoY Variation (%)"] = ((df_month["Generation (TWh)"] - df_month["Generation (TWh)_last_year"]) / df_month["Generation (TWh)_last_year"]) * 100
    df_month["YoY Variation (%)"] = df_month["YoY Variation (%)"].round(2)
    df_month.drop(columns=["Generation (TWh)_last_year"], inplace=True)
    
    # Per visualizzazione mensile, formatta la data come "MM-YYYY"
    df_monthly = df_month.copy()
    df_monthly["Date"] = df_monthly["Date"].dt.strftime('%m-%Y')
    
    # --- AGGREGAZIONE DEI DATI A LIVELLO ANNUALE ---
    df_annual = df.copy()
    df_annual['Year'] = df_annual["Date"].dt.year
    annual = df_annual.groupby(['Country', 'Source', 'Year'])['Generation (TWh)'].sum().reset_index()
    annual_total = annual[annual['Source'] == 'Total'][['Country', 'Year', 'Generation (TWh)']].rename(
        columns={'Generation (TWh)': 'Annual Total'}
    )
    annual = annual.merge(annual_total, on=['Country', 'Year'], how='left')
    annual['Share (%)'] = annual.apply(
        lambda row: 100 if row['Source'] == 'Total' else round((row['Generation (TWh)'] / row['Annual Total']) * 100, 2),
        axis=1
    )
    annual = annual.sort_values(['Country', 'Source', 'Year'])
    annual['YoY Variation (%)'] = annual.groupby(['Country', 'Source'])['Generation (TWh)'].pct_change() * 100
    annual['YoY Variation (%)'] = annual['YoY Variation (%)'].round(2)
    annual['Date'] = annual['Year'].astype(str)
    df_annual_final = annual[['Country', 'Date', 'Source', 'Generation (TWh)', 'Share (%)', 'YoY Variation (%)']]
    
    # --- INTERFACCIA UTENTE: TABELLA CON FILTRI ---
    st.subheader("Tabella Produzione Elettrica")
    table_view = st.radio("Visualizzazione dati:", ("Mensile", "Annuale"))
    
    # Filtri con opzione "All" per Country, Source e Anno
    # Elimina i valori nulli e poi fai il sort
    all_countries = df["Country"].dropna().unique()
    all_countries = sorted(all_countries)

    countries_options = ["All"] + all_countries
    table_countries = st.multiselect("Seleziona paese/i per la tabella:", countries_options, default=["All"])
    
    all_sources = sorted(df["Source"].unique())
    sources_options = ["All"] + all_sources
    table_sources = st.multiselect("Seleziona fonte/e per la tabella:", sources_options, default=["All"])
    
    if table_view == "Mensile":
        df_table = df_monthly.copy()
        df_table["Year"] = df_table["Date"].str[-4:].astype(int)
    else:
        df_table = df_annual_final.copy()
        df_table["Year"] = df_table["Date"].astype(int)
    
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
    
    def color_yoy(val):
        if pd.isna(val):
            return ""
        color = "green" if val > 0 else "red" if val < 0 else "black"
        return f"color: {color}"
    
    styled_table = df_table.style.applymap(color_yoy, subset=["YoY Variation (%)"]).format({
        "Generation (TWh)": "{:.2f}",
        "Share (%)": "{:.2f}",
        "YoY Variation (%)": "{:.2f}"
    })
    
    st.dataframe(styled_table, use_container_width=True)
    st.download_button("📥 Scarica Dati Tabella", df_table.to_csv(index=False), "dati_tabella.csv", "text/csv")
    st.download_button("Scarica DB Completo", df_raw.to_csv(index=False), "db_completo.csv", "text/csv")
    
    # --- GRAFICO STATICO CON MATPLOTLIB ---
    st.subheader("Grafico Quota di Generazione Elettrica per Fonte")
    # Filtro per Country specifico per il grafico (scelta singola)
    graph_country = st.selectbox("Seleziona un paese per il grafico:", sorted(df["Country"].unique()))
    
    df_graph = df_monthly[df_monthly["Country"] == graph_country]
    # Escludi gli aggregati di gruppo per non appesantire il grafico
    df_graph = df_graph[~df_graph["Country"].isin(["EUR", "G20", "G7", "G9", "World"])]
    # Escludi anche le fonti aggregate "Total", "Green", "Brown"
    df_graph_plot = df_graph[~df_graph["Source"].isin(["Total", "Green", "Brown"])]
    df_plot = df_graph_plot.pivot(index='Date', columns='Source', values='Share (%)')
    
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
    
    fig, ax = plt.subplots(figsize=(10, 5))
    if not df_plot.empty:
        df_plot.plot(kind='area', stacked=True, alpha=0.7, ax=ax, color=[color_map[s] for s in df_plot.columns])
        ax.legend(loc='upper left')
        ax.set_title(f"Quota di Generazione - {graph_country}")
        ax.set_ylabel('%')
        ax.set_ylim(0, 100)
        ax.set_xlabel('Anno')
        plt.tight_layout()
        st.pyplot(fig)
    else:
        st.warning("Nessun dato disponibile per il grafico!")
else:
    st.warning("Nessun dato disponibile!")
