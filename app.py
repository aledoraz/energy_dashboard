import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import time
from datetime import datetime, timedelta
from io import BytesIO
import plotly.express as px

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

# --- FUNZIONE: Ricava l'ultima data disponibile dai dati Ember ---
def get_last_available_date():
    api_key = st.secrets["API_KEY"]
    base_url = "https://api.ember-energy.org"
    query_url = (
        f"{base_url}/v1/electricity-generation/monthly"
        f"?entity_code=ITA&series=Coal"
        f"&is_aggregate_series=false&include_all_dates_value_range=true&api_key={api_key}"
    )
    response = requests.get(query_url)
    if response.status_code == 200:
        data = response.json()
        if "data" in data and data["data"]:
            dates = [entry["date"] for entry in data["data"]]
            return max(pd.to_datetime(dates))
    # Se non disponibile, fallback al mese precedente
    today = datetime.today().replace(day=1)
    return today - timedelta(days=1)

# --- FUNZIONE PRINCIPALE DI DOWNLOAD DATI ---
def get_data():
    api_key = st.secrets["API_KEY"]
    end_date = get_last_available_date()
    end_str = end_date.strftime("%Y-%m")

    base_url = "https://api.ember-energy.org"
    query_url = (
        f"{base_url}/v1/electricity-generation/monthly"
        f"?entity_code=ARG,ARM,AUS,AUT,AZE,BGD,BLR,BEL,BOL,BIH,BRA,BGR,CAN,CHL,CHN,COL,CRI,HRV,CYP,CZE,DNK,DOM,ECU,EGY,SLV,EST,FIN,FRA,GEO,DEU,GRC,HUN,IND,IRN,IRL,ITA,JPN,KAZ,KEN,KWT,KGZ,LVA,LTU,LUX,MYS,MLT,MEX,MDA,MNG,MNE,MAR,NLD,NZL,NGA,MKD,NOR,OMN,PAK,PER,PHL,POL,PRT,PRI,QAT,ROU,RUS,SRB,SGP,SVK,SVN,ZAF,KOR,ESP,LKA,SWE,CHE,TWN,TJK,THA,TUN,TUR,UKR,GBR,USA,URY,VNM"
        f"&start_date=2000-01&end_date={end_str}"
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

# Lista ISO3 dei paesi europei presenti nei dati
europe_iso3 = [
    "ALB", "AUT", "BEL", "BIH", "BGR", "HRV", "CYP", "CZE", "DNK", "EST",
    "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL", "ITA", "LVA", "LTU",
    "LUX", "MLT", "MDA", "MNE", "NLD", "MKD", "NOR", "POL", "PRT", "ROU",
    "SRB", "SVK", "SVN", "ESP", "SWE", "CHE", "UKR", "GBR", "XKX"
]

if not df_raw.empty:
    df_work = df_raw.copy()

    # Aggregato WORLD
    world = df_work.groupby(["date", "series"], as_index=False)["generation_twh"].sum()
    world["entity_code"] = "WORLD"

    # Aggregato EUR
    eur = df_work[df_work["entity_code"].isin(europe_iso3)].groupby(["date", "series"], as_index=False)["generation_twh"].sum()
    eur["entity_code"] = "EUR"

    # Unione con i dati originali
    df_augmented = pd.concat([df_raw, world, eur], ignore_index=True)

    # Calcolo quota per EUR e WORLD
    df_augmented["date"] = pd.to_datetime(df_augmented["date"])
    totali = df_augmented.groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    totali = totali.rename(columns={"generation_twh": "total_twh"})
    df_augmented = df_augmented.merge(totali, on=["entity_code", "date"], how="left")
    df_augmented["share_of_generation_pct"] = (df_augmented["generation_twh"] / df_augmented["total_twh"]) * 100
    df_augmented["share_of_generation_pct"] = df_augmented["share_of_generation_pct"].round(2)
    df_augmented = df_augmented.drop(columns=["total_twh"])

    df_raw = df_augmented.copy()

    # --- AGGIUNTA: % VARIAZIONE VS GC PRECEDENTE E INIZIO ANNO ---
    df_raw["date"] = pd.to_datetime(df_raw["date"])
    df_raw["month_year"] = df_raw["date"].dt.strftime("%m-%Y")

    # Governing Council ECB (Day 2) date in formato MM-YYYY
    gc_months = ["01-2025", "04-2025", "06-2025", "07-2025", "09-2025", "10-2025", "12-2025"]
    gc_months_dt = [datetime.strptime(m, "%m-%Y") for m in gc_months]

    # Aggiunge colonna con ultima GC precedente
    def last_gc_month(row_date):
        prev = [gc for gc in gc_months_dt if gc < row_date]
        return max(prev).strftime("%m-%Y") if prev else None

    df_raw["Last GC"] = df_raw["date"].apply(last_gc_month)

    gc_ref = df_raw[["entity_code", "series", "month_year", "generation_twh"]].rename(
        columns={"month_year": "Last GC", "generation_twh": "GC Value"})

    df_raw = df_raw.merge(gc_ref, on=["entity_code", "series", "Last GC"], how="left")
    df_raw["Last GC"] = ((df_raw["generation_twh"] - df_raw["GC Value"]) / df_raw["GC Value"]) * 100
    df_raw["Last GC"] = df_raw["Last GC"].round(2)
    df_raw = df_raw.drop(columns=["GC Value"])

    # Calcolo variazione vs inizio anno (01-YYYY)
    df_raw["Year"] = df_raw["date"].dt.year
    df_raw["BOY"] = "01-" + df_raw["Year"].astype(str)
    boy_ref = df_raw[["entity_code", "series", "month_year", "generation_twh"]].rename(
        columns={"month_year": "BOY", "generation_twh": "BOY Value"})
    df_raw = df_raw.merge(boy_ref, on=["entity_code", "series", "BOY"], how="left")
    df_raw["BOY"] = ((df_raw["generation_twh"] - df_raw["BOY Value"]) / df_raw["BOY Value"]) * 100
    df_raw["BOY"] = df_raw["BOY"].round(2)
    df_raw = df_raw.drop(columns=["BOY Value"])

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
    # Creiamo una copia per il calcolo mensile YoY
    df_month = df.copy()
    df_last_year = df_month.copy()
    df_last_year["Date"] = df_last_year["Date"] + pd.DateOffset(years=1)
    df_month = df_month.merge(
        df_last_year[["Country", "Source", "Date", "Generation (TWh)"]],
        on=["Country", "Source", "Date","Last GC", "BOY"],
        suffixes=("", "_last_year"),
        how="left"
    )
    df_month["YoY Variation (%)"] = ((df_month["Generation (TWh)"] - df_month["Generation (TWh)_last_year"]) / df_month["Generation (TWh)_last_year"]) * 100
    df_month["YoY Variation (%)"] = df_month["YoY Variation (%)"].round(2)
    df_month.drop(columns=["Generation (TWh)_last_year"], inplace=True)
    # Selezioniamo le colonne utili e formattiamo la data in "MM-YYYY"
    df_monthly = df_month[["Country", "Date", "Source","Generation (TWh)", "Share (%)", "YoY Variation (%)","Last GC", "BOY"]].copy()
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
    # Calcoliamo la quota: se la fonte è Total, la quota è 100 altrimenti calcolata in base al totale annuale
    annual['Share (%)'] = annual.apply(
        lambda row: 100 if row['Source'] == 'Total' else round((row['Generation (TWh)'] / row['Annual Total']) * 100, 2),
        axis=1
    )
    # Calcoliamo la variazione YoY annuale
    annual = annual.sort_values(['Country', 'Source', 'Year'])
    annual['YoY Variation (%)'] = annual.groupby(['Country', 'Source'])['Generation (TWh)'].pct_change() * 100
    annual['YoY Variation (%)'] = annual['YoY Variation (%)'].round(2)
    # Creiamo una colonna Date con l'anno (per uniformare la visualizzazione)
    annual['Date'] = annual['Year'].astype(str)
    df_annual_final = annual[['Country', 'Date', 'Source', 'Generation (TWh)', 'Share (%)', 'YoY Variation (%)']]
    
    # --- INTERFACCIA UTENTE: TABELLA CON FILTRI ---
    st.subheader("Tabella Produzione Elettrica")
    # Selezione visualizzazione: Mensile o Annuale
    table_view = st.radio("Visualizzazione dati:", ("Mensile", "Annuale"))
    # Filtro per Country (tabella)
    table_country = st.selectbox("Seleziona un paese per la tabella:", sorted(df["Country"].unique()))

    # Filtro per Source (multiselezione)
    available_sources = sorted(df["Source"].unique())
    table_source = st.multiselect("Seleziona una fonte:", available_sources, default=available_sources)

    # Filtro per Anno (con multiselezione)
    if table_view == "Mensile":
        available_years = sorted(df_monthly["Date"].str[-4:].unique())
    else:
        available_years = sorted(df_annual_final["Date"].unique())
    
    selected_years = st.multiselect("Seleziona uno o più anni:", available_years, default=available_years)

    
    # Seleziona il dataset in base al tipo di visualizzazione
    if table_view == "Mensile":
        df_table = df_monthly.copy()
    else:
        df_table = df_annual_final.copy()
    
    # Applica i filtri per Country e Source
    df_table = df_table[(df_table["Country"] == table_country) & (df_table["Source"].isin(table_source))]
    
    df_table = df_table[df_table["Date"].str[-4:].isin(selected_years)]

    # Funzione per colorare la colonna YoY
    def color_yoy(val):
        if pd.isna(val):
            return ""
        color = "green" if val > 0 else "red" if val < 0 else "black"
        return f"color: {color}"
    
    styled_table = df_table.style.applymap(color_yoy, subset=["YoY Variation (%)", "Last GC", "BOY"]).format({
    "Generation (TWh)": "{:.2f}",
    "Share (%)": "{:.2f}",
    "YoY Variation (%)": "{:.2f}",
    "Last GC": "{:.2f}",
    "BOY": "{:.2f}"
    })

    
    st.dataframe(styled_table, use_container_width=True)
    
    # Pulsante per scaricare i dati filtrati della tabella
    st.download_button("Scarica Dati Tabella", df_table.to_csv(index=False), "dati_tabella.csv", "text/csv")
    
    # Pulsante per scaricare il DB completo preso con l'API
    st.download_button("Scarica DB Completo", df_raw.to_csv(index=False), "db_completo.csv", "text/csv")
    
        # --- INTERFACCIA UTENTE: GRAFICO ---
    st.subheader("Grafico Quota di Generazione Elettrica per Fonte")
    
    # Ordine fisso delle fonti (stacking)
    ordered_sources = ["Coal", "Gas", "Other fossil", "Nuclear", "Solar", "Wind", "Hydro", "Bioenergy", "Other renewables"]
    
    # Colori coerenti
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
    
    # Selezione paese
    graph_country = st.selectbox("Seleziona un paese per il grafico:", sorted(df["Country"].unique()), key="graph_country")
    
    # Selezione metrica: Share o YoY
    metric_choice = st.radio("Seleziona la metrica da visualizzare:", ["Share", "YoY"])
    
    # Filtro per fonte da includere nel grafico
    selected_sources = st.multiselect(
        "Seleziona le fonti da visualizzare nel grafico:",
        options=ordered_sources,
        default=ordered_sources
    )
    
    # Prepara dati
    df_graph = df_monthly[df_monthly["Country"] == graph_country].copy()
    df_graph["Date"] = pd.to_datetime(df_graph["Date"], format="%m-%Y", errors="coerce")
    
    # Applichiamo i filtri
    df_graph = df_graph[df_graph["Source"].isin(selected_sources)]
    
    # Imposta Source come categorico con ordine fisso (anche con subset)
    df_graph["Source"] = pd.Categorical(df_graph["Source"], categories=ordered_sources, ordered=True)
    
    # Selezione metrica
    if metric_choice == "Share":
        y_col = "Share (%)"
        y_title = "Quota (%)"
        y_range = [0, 100]
    else:
        y_col = "YoY Variation (%)"
        y_title = "Variazione YoY (%)"
        # y_range dinamico con margine
        y_min = df_graph[y_col].min()
        y_max = df_graph[y_col].max()
        y_margin = max(abs(y_min), abs(y_max)) * 0.1
        y_range = [y_min - y_margin, y_max + y_margin]
    
    # Plot interattivo
    import plotly.express as px
    
    if not df_graph.empty:
        fig = px.area(
            df_graph,
            x="Date",
            y=y_col,
            color="Source",
            category_orders={"Source": ordered_sources},
            color_discrete_map=color_map,
            title=f"{y_title} - {graph_country}",
            labels={y_col: y_title, "Date": "Anno"}
        )
    
        fig.update_layout(
            yaxis=dict(range=y_range),
            hovermode="x unified",
            legend_title="Fonte",
            xaxis_title="Anno",
            yaxis_title=y_title,
            margin=dict(t=50, b=50, l=40, r=10),
        )
    
        st.plotly_chart(fig, use_container_width=True)
    
        # Download PNG (solo se Kaleido è installato)
        import io
        buf = io.BytesIO()
        try:
            fig.write_image(buf, format="png")
            buf.seek(0)
            st.download_button(
                label="Scarica Grafico",
                data=buf,
                file_name=f"grafico_{graph_country}.png",
                mime="image/png"
            )
        except Exception as e:
            st.warning("⚠️ Kaleido non installato, impossibile scaricare il grafico come PNG.")
    else:
        st.warning("Nessun dato disponibile per il grafico!")

    
else:
    st.warning("Nessun dato disponibile!")
