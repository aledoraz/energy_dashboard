        
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
        url = (
            "https://api.ember-energy.org/v1/electricity-generation/monthly"
            "?entity_code=ITA&series=Coal"
            "&is_aggregate_series=false&include_all_dates_value_range=true"
            f"&api_key={api_key}"
        )
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if "data" in data and data["data"]:
                dates = [entry["date"] for entry in data["data"]]
                return max(pd.to_datetime(dates))
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
            f"?entity_code=ARG,ARM,AUS,AUT,AZE,BGD,BLR,BEL,BOL,BIH,BRA,BGR,CAN,CHL,CHN,COL,CRI,HRV,CYP,CZE,DNK,DOM,"
            f"ECU,EGY,SLV,EST,FIN,FRA,GEO,DEU,GRC,HUN,IND,IRN,IRL,ITA,JPN,KAZ,KEN,KWT,KGZ,LVA,LTU,LUX,MYS,MLT,"
            f"MEX,MDA,MNG,MNE,MAR,NLD,NZL,NGA,MKD,NOR,OMN,PAK,PER,PHL,POL,PRT,PRI,QAT,ROU,RUS,SRB,SGP,SVK,SVN,"
            f"ZAF,KOR,ESP,LKA,SWE,CHE,TWN,TJK,THA,TUN,TUR,UKR,GBR,USA,URY,VNM"
            f"&start_date=2000-01&end_date={end_str}"
            f"&series=Bioenergy,Coal,Gas,Hydro,Nuclear,Other fossil,Other renewables,Solar,Wind"
            f"&is_aggregate_series=false&include_all_dates_value_range=true&api_key={api_key}"
        )
    
        for _ in range(5):
            response = requests.get(query_url)
            if response.status_code == 200:
                data = response.json()
                if "data" in data and isinstance(data["data"], list) and data["data"]:
                    return pd.DataFrame(data["data"])
                else:
                    st.warning("Dati API ricevuti ma vuoti o in formato inatteso.")
                    return pd.DataFrame()
            elif response.status_code == 500:
                time.sleep(20)
        return pd.DataFrame()
    
    # --- SCARICAMENTO DATI ---
    df_raw = get_data()
    
    # Lista ISO3 dei paesi europei presenti nei dati
    europe_iso3 = [
        "ALB", "AUT", "BEL", "BIH", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL",
        "ITA", "LVA", "LTU", "LUX", "MLT", "MDA", "MNE", "NLD", "MKD", "NOR", "POL", "PRT", "ROU", "SRB", "SVK", "SVN", "ESP",
        "SWE", "CHE", "UKR", "GBR", "XKX"
    ]

    
    
    # --- PREPARAZIONE DATI ---
    df = df_raw[["entity_code", "date", "series", "generation_twh", "share_of_generation_pct", "% BOY"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] >= pd.to_datetime("2014-01")]
    df["generation_twh"] = df["generation_twh"].round(2)
    
    # Definizione fonti green/brown
    green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables", "Nuclear"]
    brown_sources = ["Coal", "Gas", "Other fossil"]
    
    # Aggregati Total, Green, Brown
    df_total = df.groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total["series"] = "Total"
    df_total["share_of_generation_pct"] = 100.0
    df_total = df_total.rename(columns={"generation_twh": "generation_twh"})
    
    df_green = df[df["series"].isin(green_sources)].groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_green["series"] = "Green"
    df_green = df_green.rename(columns={"generation_twh": "generation_twh"})
    
    df_brown = df[df["series"].isin(brown_sources)].groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_brown["series"] = "Brown"
    df_brown = df_brown.rename(columns={"generation_twh": "generation_twh"})
    
    # Calcolo quota e % BOY anche per aggregati
    for agg_df in [df_green, df_brown]:
        agg_df = agg_df.merge(df_total[["entity_code", "date", "generation_twh"]].rename(columns={"generation_twh": "total"}), 
                              on=["entity_code", "date"], how="left")
        agg_df["share_of_generation_pct"] = (agg_df["generation_twh"] / agg_df["total"]) * 100
        agg_df["share_of_generation_pct"] = agg_df["share_of_generation_pct"].round(2)
        agg_df.drop(columns=["total"], inplace=True)
    
    # Unione di tutte le fonti
    df = pd.concat([df, df_total, df_green, df_brown], ignore_index=True)
    df["share_of_generation_pct"] = df["share_of_generation_pct"].round(2)
    
    # Rinomina
    df = df.rename(columns={
        "entity_code": "Country",
        "date": "Date",
        "series": "Source",
        "generation_twh": "Generation (TWh)",
        "share_of_generation_pct": "Share (%)"
    })
    
    # Ordinamento
    df = df.sort_values(by=["Country", "Source", "Date"])
    df_original = df.copy()
    
    # --- CALCOLO YOY ---
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
    df_monthly = df_month.copy()
    df_monthly["Date"] = df_monthly["Date"].dt.strftime('%m-%Y')
    
    
    # --- AGGREGAZIONE ANNUALE ---
    df_annual = df_original.copy()
    df_annual['Year'] = df_annual["Date"].dt.year
    annual = df_annual.groupby(['Country', 'Source', 'Year'])['Generation (TWh)'].sum().reset_index()
    annual_total = annual[annual['Source'] == 'Total'][['Country', 'Year', 'Generation (TWh)']].rename(
        columns={'Generation (TWh)': 'Annual Total'})
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
    
    # --- TABELLA ---
    st.subheader("Tabella Produzione Elettrica")
    table_view = st.radio("Visualizzazione dati:", ("Mensile", "Annuale"))
    table_country = st.selectbox("Seleziona un paese per la tabella:", sorted(df["Country"].unique()))
    available_sources = sorted(df["Source"].unique())
    table_source = st.multiselect("Seleziona una fonte:", available_sources, default=available_sources)
    
    if table_view == "Mensile":
        available_years = sorted(df_monthly["Date"].str[-4:].unique())
    else:
        available_years = sorted(df_annual_final["Date"].unique())
    
    selected_years = st.multiselect("Seleziona uno o più anni:", available_years, default=available_years)
    
    df_table = df_monthly.copy() if table_view == "Mensile" else df_annual_final.copy()
    df_table = df_table[(df_table["Country"] == table_country) & (df_table["Source"].isin(table_source))]
    df_table = df_table[df_table["Date"].str[-4:].isin(selected_years)]
    
def color_yoy(val):
        if pd.isna(val):
            return ""
        color = "green" if val > 0 else "red" if val < 0 else "black"
        return f"color: {color}"
    
    columns_to_color = [col for col in ["YoY Variation (%)", "% BOY"] if col in df_table.columns]
    styled_table = df_table.style.applymap(color_yoy, subset=columns_to_color).format({
        "Generation (TWh)": "{:.2f}",
        "Share (%)": "{:.2f}",
        "YoY Variation (%)": "{:.2f}",
        "% BOY": "{:.2f}"
    })
    
    st.dataframe(styled_table, use_container_width=True)
    
    st.download_button("Scarica Dati Tabella", df_table.to_csv(index=False), "dati_tabella.csv", "text/csv")
    st.download_button("Scarica DB Completo", df_raw.to_csv(index=False), "db_completo.csv", "text/csv")
    
    
    # --- GRAFICO ---
    st.subheader("Grafico Quota di Generazione Elettrica per Fonte")
    
    ordered_sources = ["Coal", "Gas", "Other fossil", "Nuclear", "Solar", "Wind", "Hydro", "Bioenergy", "Other renewables"]
    color_map = {
        "Coal": "#4d4d4d", "Other fossil": "#a6a6a6", "Gas": "#b5651d", "Nuclear": "#ffdd44",
        "Solar": "#87CEEB", "Wind": "#aec7e8", "Hydro": "#1f77b4", "Bioenergy": "#2ca02c", "Other renewables": "#17becf"
    }
    
    graph_country = st.selectbox("Seleziona un paese per il grafico:", sorted(df["Country"].unique()), key="graph_country")
    metric_choice = st.radio("Seleziona la metrica da visualizzare:", ["Share", "YoY"])
    selected_sources = st.multiselect("Seleziona le fonti da visualizzare nel grafico:", options=ordered_sources, default=ordered_sources)
    
    df_graph = df_monthly[df_monthly["Country"] == graph_country].copy()
    df_graph["Date"] = pd.to_datetime(df_graph["Date"], format="%m-%Y", errors="coerce")
    df_graph = df_graph[df_graph["Source"].isin(selected_sources)]
    df_graph["Source"] = pd.Categorical(df_graph["Source"], categories=ordered_sources, ordered=True)
    
    if metric_choice == "Share":
        y_col = "Share (%)"
        y_title = "Quota (%)"
        y_range = [0, 100]
    else:
        y_col = "YoY Variation (%)"
        y_title = "Variazione YoY (%)"
        y_min, y_max = df_graph[y_col].min(), df_graph[y_col].max()
        y_margin = max(abs(y_min), abs(y_max)) * 0.1
        y_range = [y_min - y_margin, y_max + y_margin]
    
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
        except Exception:
            st.warning("⚠️ Kaleido non installato, impossibile scaricare il grafico come PNG.")
    else:
        st.warning("Nessun dato disponibile per il grafico!")
