import streamlit as st
import pandas as pd
import requests
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

# Lista ISO3 dei paesi europei
europe_iso3 = [
    "ALB", "AUT", "BEL", "BIH", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL",
    "ITA", "LVA", "LTU", "LUX", "MLT", "MDA", "MNE", "NLD", "MKD", "NOR", "POL", "PRT", "ROU", "SRB", "SVK", "SVN", "ESP",
    "SWE", "CHE", "UKR", "GBR", "XKX"
]

# Aggregazioni EUR e WORLD
if not df_raw.empty:
    df_raw["date"] = pd.to_datetime(df_raw["date"])
    df_eur = df_raw[df_raw["entity_code"].isin(europe_iso3)].groupby(["date", "series"], as_index=False)["generation_twh"].sum()
    df_eur["entity_code"] = "EUR"

    df_world = df_raw.groupby(["date", "series"], as_index=False)["generation_twh"].sum()
    df_world["entity_code"] = "WORLD"

    df_raw = pd.concat([df_raw, df_eur, df_world], ignore_index=True)

    # Ricalcolo quota
    total_gen = df_raw.groupby(["entity_code", "date"])["generation_twh"].sum().reset_index().rename(
        columns={"generation_twh": "total"})
    df_raw = df_raw.merge(total_gen, on=["entity_code", "date"], how="left")
    df_raw["share_of_generation_pct"] = (df_raw["generation_twh"] / df_raw["total"]) * 100
    df_raw["share_of_generation_pct"] = df_raw["share_of_generation_pct"].round(2)
    df_raw.drop(columns="total", inplace=True)

    # Aggiunta colonna BOY = valore di gennaio per ogni anno
    df_raw["month_year"] = df_raw["date"].dt.strftime("%m-%Y")
    df_raw["boy_key"] = "01-" + df_raw["date"].dt.year.astype(str)
    ref = df_raw[["entity_code", "series", "month_year", "generation_twh"]].copy()
    ref = ref.rename(columns={"month_year": "boy_key", "generation_twh": "boy_value"})
    df_raw = df_raw.merge(ref, on=["entity_code", "series", "boy_key"], how="left")
    df_raw["% BOY"] = ((df_raw["generation_twh"] - df_raw["boy_value"]) / df_raw["boy_value"]) * 100
    df_raw["% BOY"] = df_raw.apply(
    lambda row: 0.0 if row["boy_value"] == 0 else ((row["generation_twh"] - row["boy_value"]) / row["boy_value"]) * 100,
    axis=1
    )
    df_raw["% BOY"] = df_raw["% BOY"].round(2)

    df_raw.drop(columns=["boy_value", "boy_key"], inplace=True)

    # Ridenominazione
    df = df_raw.rename(columns={
        "entity_code": "Country",
        "date": "Date",
        "series": "Source",
        "generation_twh": "Generation (TWh)",
        "share_of_generation_pct": "Share (%)"
    })

    # Aggiunta Green, Brown, Total
    green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables", "Nuclear"]
    brown_sources = ["Coal", "Gas", "Other fossil"]

    def aggregate_and_append(label, source_list):
        agg = df[df["Source"].isin(source_list)].groupby(["Country", "Date"], as_index=False)[
            ["Generation (TWh)"]].sum()
        agg["Source"] = label
        total = df[df["Source"] == "Total"][["Country", "Date", "Generation (TWh)"]].rename(columns={"Generation (TWh)": "total"})
        agg = agg.merge(total, on=["Country", "Date"], how="left")
        agg["Share (%)"] = (agg["Generation (TWh)"] / agg["total"] * 100).round(2)
        agg.drop(columns="total", inplace=True)

        # Colonna % BOY anche per aggregati
        agg["month_year"] = agg["Date"].dt.strftime("%m-%Y")
        agg["boy_key"] = "01-" + agg["Date"].dt.year.astype(str)
        ref = agg[["Country", "Source", "month_year", "Generation (TWh)"]].rename(columns={
            "month_year": "boy_key", "Generation (TWh)": "boy_value"})
        agg = agg.merge(ref, on=["Country", "Source", "boy_key"], how="left")
        agg["% BOY"] = ((agg["Generation (TWh)"] - agg["boy_value"]) / agg["boy_value"]).round(2) * 100
        agg.drop(columns=["boy_value", "boy_key"], inplace=True)
        return agg

    df_total = df.groupby(["Country", "Date"], as_index=False)[["Generation (TWh)"]].sum()
    df_total["Source"] = "Total"
    df_total["Share (%)"] = 100.0

    # Colonna % BOY per Total
    df_total["month_year"] = df_total["Date"].dt.strftime("%m-%Y")
    df_total["boy_key"] = "01-" + df_total["Date"].dt.year.astype(str)
    ref_total = df_total[["Country", "month_year", "Generation (TWh)"]].rename(columns={"month_year": "boy_key", "Generation (TWh)": "boy_value"})
    df_total = df_total.merge(ref_total, on=["Country", "boy_key"], how="left")
    df_total["% BOY"] = ((df_total["Generation (TWh)"] - df_total["boy_value"]) / df_total["boy_value"] * 100).round(2)
    df_total.drop(columns=["boy_value", "boy_key"], inplace=True)

    df_green = aggregate_and_append("Green", green_sources)
    df_brown = aggregate_and_append("Brown", brown_sources)

    df_all = pd.concat([df, df_total, df_green, df_brown], ignore_index=True)
    df_all = df_all[df_all["Date"] >= pd.to_datetime("2014-01")]
    df_all = df_all.sort_values(["Country", "Source", "Date"])
    df_all["Date_str"] = df_all["Date"].dt.strftime("%m-%Y")

    # --- VARIAZIONE YOY ---
    df_yoy = df_all.copy()
    df_last_year = df_yoy.copy()
    df_last_year["Date"] = df_last_year["Date"] + pd.DateOffset(years=1)
    df_yoy = df_yoy.merge(
        df_last_year[["Country", "Source", "Date", "Generation (TWh)"]],
        on=["Country", "Source", "Date"],
        suffixes=("", "_last_year"),
        how="left"
    )
    df_yoy["YoY Variation (%)"] = ((df_yoy["Generation (TWh)"] - df_yoy["Generation (TWh)_last_year"]) / df_yoy["Generation (TWh)_last_year"]) * 100
    df_yoy["YoY Variation (%)"] = df_yoy.apply(
    lambda row: 0.0 if row["Generation (TWh)_last_year"] == 0 else ((row["Generation (TWh)"] - row["Generation (TWh)_last_year"]) / row["Generation (TWh)_last_year"]) * 100,
    axis=1)
    df_yoy["YoY Variation (%)"] = df_yoy["YoY Variation (%)"].round(2)

    df_yoy.drop(columns=["Generation (TWh)_last_year"], inplace=True)
    df_monthly = df_yoy.copy()

    # --- TABELLA ---
    st.subheader("Tabella Produzione Elettrica")
    view = st.radio("Visualizzazione dati:", ("Mensile",), index=0)
    country = st.selectbox("Seleziona un paese:", sorted(df_monthly["Country"].unique()))
    sources = st.multiselect("Seleziona una fonte:", sorted(df_monthly["Source"].unique()), default=sorted(df_monthly["Source"].unique()))
    years = st.multiselect("Anni:", sorted(df_monthly["Date"].dt.year.unique().astype(str)), default=sorted(df_monthly["Date"].dt.year.unique().astype(str)))

    df_show = df_monthly[
        (df_monthly["Country"] == country) &
        (df_monthly["Source"].isin(sources)) &
        (df_monthly["Date"].dt.year.astype(str).isin(years))
    ].copy()
    df_show["Date"] = df_show["Date"].dt.strftime("%m-%Y")

    def color(val):
        if pd.isna(val): return ""
        return "color: green" if val > 0 else "color: red" if val < 0 else "color: black"

    styled = df_show[["Country", "Date", "Source", "Generation (TWh)", "Share (%)", "YoY Variation (%)", "% BOY"]].style \
        .applymap(color, subset=["YoY Variation (%)", "% BOY"]) \
        .format({col: "{:.2f}" for col in ["Generation (TWh)", "Share (%)", "YoY Variation (%)", "% BOY"]})

    st.dataframe(styled, use_container_width=True)
    st.download_button("Scarica Dati Tabella", df_show.to_csv(index=False), "dati_tabella.csv", "text/csv")
    st.download_button("Scarica DB Completo", df_raw.to_csv(index=False), "db_completo.csv", "text/csv")
