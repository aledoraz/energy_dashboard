import streamlit as st
import pandas as pd
import requests
pip install plotly
import plotly.express as px
import time

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

def get_data():
    api_key = st.secrets["API_KEY"]
    base_url = "https://api.ember-energy.org"
    query_url = (
        f"{base_url}/v1/electricity-generation/monthly"
        f"?entity_code=ITA,DEU,FRA,CHN,USA,AUS,CAN,JPN"
        f"&start_date=2014-01&end_date=2025-01"
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
    df = df_raw[["entity_code", "date", "series", "generation_twh", "share_of_generation_pct"]].copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['date'] >= pd.to_datetime("2014-01")]
    df["generation_twh"] = df["generation_twh"].round(2)
    
    # Definiamo le fonti per aggregazioni
    green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables", "Nuclear"]
    brown_sources = ["Coal", "Gas", "Other fossil"]
    
    # Calcolo delle serie aggregate mensili
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
    
    # Rinominiamo le colonne
    df = df.rename(columns={
        "entity_code": "Country",
        "date": "Date",
        "series": "Source",
        "generation_twh": "Generation (TWh)",
        "share_of_generation_pct": "Share (%)"
    })
    
    # Ordinamento e conversione della data in datetime
    df = df.sort_values(by=["Country", "Source", "Date"])
    # Salviamo una copia base per aggregazioni annuali
    df_original = df.copy()
    
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
    # Formattiamo la data in "MM-YYYY"
    df_monthly = df_month[["Country", "Date", "Source", "Generation (TWh)", "Share (%)", "YoY Variation (%)"]].copy()
    df_monthly["Date"] = df_monthly["Date"].dt.strftime('%m-%Y')
    
    # --- AGGREGAZIONE DEI DATI A LIVELLO ANNUALE ---
    df_annual = df_original.copy()
    df_annual['Year'] = df_annual["Date"].dt.year
    # Sommiamo la generazione per ogni anno, paese e fonte
    annual = df_annual.groupby(['Country', 'Source', 'Year'])['Generation (TWh)'].sum().reset_index()
    # Recuperiamo il totale annuale per ciascun paese
    annual_total = annual[annual['Source'] == 'Total'][['Country', 'Year', 'Generation (TWh)']].rename(
        columns={'Generation (TWh)': 'Annual Total'}
    )
    annual = annual.merge(annual_total, on=['Country', 'Year'], how='left')
    # Calcoliamo la quota
    annual['Share (%)'] = annual.apply(
        lambda row: 100 if row['Source'] == 'Total' else round((row['Generation (TWh)'] / row['Annual Total']) * 100, 2),
        axis=1
    )
    # Calcoliamo la variazione YoY annuale
    annual = annual.sort_values(['Country', 'Source', 'Year'])
    annual['YoY Variation (%)'] = annual.groupby(['Country', 'Source'])['Generation (TWh)'].pct_change() * 100
    annual['YoY Variation (%)'] = annual['YoY Variation (%)'].round(2)
    # Creiamo una colonna Date con l'anno (come stringa)
    annual['Date'] = annual['Year'].astype(str)
    df_annual_final = annual[['Country', 'Date', 'Source', 'Generation (TWh)', 'Share (%)', 'YoY Variation (%)']]
    
    # --- INTERFACCIA UTENTE: TABELLA CON FILTRI ---
    st.subheader("Tabella Produzione Elettrica")
    # Selezione visualizzazione: Mensile o Annuale
    table_view = st.radio("Visualizzazione dati:", ("Mensile", "Annuale"))
    
    # Creiamo i filtri multiselezione con opzione "All"
    countries = sorted(df["Country"].unique())
    countries_options = ["All"] + countries
    table_countries = st.multiselect("Seleziona paese/i per la tabella:", countries_options, default=["All"])
    
    sources = sorted(df["Source"].unique())
    sources_options = ["All"] + sources
    table_sources = st.multiselect("Seleziona fonte/e per la tabella:", sources_options, default=["All"])
    
    # Seleziona il dataset in base al tipo di visualizzazione
    if table_view == "Mensile":
        df_table = df_monthly.copy()
        # Aggiungiamo la colonna "Year" estraendo l'anno dalla data in formato "MM-YYYY"
        df_table["Year"] = df_table["Date"].str[-4:].astype(int)
    else:
        df_table = df_annual_final.copy()
        df_table["Year"] = df_table["Date"].astype(int)
    
    years = sorted(df_table["Year"].unique())
    years_options = ["All"] + years
    table_years = st.multiselect("Seleziona anno/i per la tabella:", years_options, default=["All"])
    
    # Se "All" è presente, sostituiamo con tutti i valori disponibili
    filter_countries = countries if "All" in table_countries else table_countries
    filter_sources = sources if "All" in table_sources else table_sources
    filter_years = years if "All" in table_years else table_years
    
    # Applica i filtri per Country, Source e Anno
    df_table = df_table[
        (df_table["Country"].isin(filter_countries)) &
        (df_table["Source"].isin(filter_sources)) &
        (df_table["Year"].isin(filter_years))
    ]
    
    # Funzione per colorare la colonna YoY
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
    
    # Pulsante per scaricare i dati filtrati della tabella
    st.download_button("📥 Scarica Dati Tabella", df_table.to_csv(index=False), "dati_tabella.csv", "text/csv")
    
    # Pulsante per scaricare il DB completo preso con l'API
    st.download_button("Scarica DB Completo", df_raw.to_csv(index=False), "db_completo.csv", "text/csv")
    
    # --- INTERFACCIA UTENTE: GRAFICO INTERATTIVO CON PLOTLY ---
    st.subheader("Grafico Quota di Generazione Elettrica per Fonte (Interattivo)")
    
    # Filtro per Country specifico per il grafico (opzione "All" inclusa)
    graph_country_options = ["All"] + countries
    graph_country_sel = st.multiselect("Seleziona paese/i per il grafico:", graph_country_options, default=["All"], key="graph_country")
    filter_graph_countries = countries if "All" in graph_country_sel else graph_country_sel
    
    # Utilizziamo i dati mensili per il grafico e filtriamo per i paesi scelti
    df_graph = df_monthly[df_monthly["Country"].isin(filter_graph_countries)]
    # Escludiamo le fonti aggregate
    df_graph = df_graph[~df_graph["Source"].isin(["Total", "Green", "Brown"])]
    # Convertiamo la colonna Date in datetime per Plotly
    df_graph["Date"] = pd.to_datetime(df_graph["Date"], format='%m-%Y')
    
    # Se è selezionato un solo paese, mostriamo un unico grafico; altrimenti, utilizziamo i facet
    if len(filter_graph_countries) == 1:
        fig = px.area(
            df_graph,
            x="Date",
            y="Share (%)",
            color="Source",
            title=f"Quota di Generazione - {filter_graph_countries[0]}",
            template="plotly_white",
            labels={"Share (%)": "%", "Date": "Anno"}
        )
    else:
        fig = px.area(
            df_graph,
            x="Date",
            y="Share (%)",
            color="Source",
            facet_col="Country",
            title="Quota di Generazione Elettrica per Fonte",
            template="plotly_white",
            labels={"Share (%)": "%", "Date": "Anno"}
        )
    
    # Imposta la legenda in alto a sinistra
    fig.update_layout(legend=dict(x=0, y=1))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Nessun dato disponibile!")
