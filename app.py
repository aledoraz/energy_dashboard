import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from io import BytesIO
import plotly.express as px

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

# --- PARAMETRI GLOBALI ---
API_KEY = st.secrets["API_KEY"]
EU_ISO3 = [
    "AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU",
    "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT",
    "ROU", "SVK", "SVN", "ESP", "SWE"
]
G20_ISO3 = [
    "ARG", "AUS", "BRA", "CAN", "CHN", "FRA", "DEU", "IND", "IDN", "ITA", "JPN",
    "KOR", "MEX", "RUS", "SAU", "ZAF", "TUR", "GBR", "USA", "EU"
]
ALL_ISO3 = sorted(set(EU_ISO3 + G20_ISO3) - {"EU"})
COUNTRIES = ",".join(ALL_ISO3)
GREEN_SOURCES = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables", "Nuclear"]
BROWN_SOURCES = ["Coal", "Gas", "Other fossil"]

# --- FUNZIONE: SCARICA DATI ---
def download_ember_data(frequency):
    base_url = "https://api.ember-energy.org/v1/electricity-generation"
    series = "Bioenergy,Coal,Gas,Hydro,Nuclear,Other fossil,Other renewables,Solar,Wind"
    url = (
        f"{base_url}/{frequency}?"
        f"entity_code={COUNTRIES}"
        f"&start_date=2000-01&end_date=2025-12"
        f"&series={series}"
        f"&is_aggregate_series=false&include_all_dates_value_range=true"
        f"&api_key={API_KEY}"
    )
    for _ in range(5):
        response = requests.get(url)
        if response.status_code == 200:
            json_data = response.json()
            if "data" in json_data:
                df = pd.DataFrame(json_data["data"])
                df["frequency"] = frequency
                return df
        time.sleep(10)
    return pd.DataFrame()

# --- SCARICAMENTO E UNIONE ---
df_monthly = download_ember_data("monthly")
df_annual = download_ember_data("annual")
df_raw = pd.concat([df_monthly, df_annual], ignore_index=True)

if df_raw.empty:
    st.error("Nessun dato disponibile.")
    st.stop()

# --- PREPARAZIONE BASE ---
df_raw["date"] = pd.to_datetime(df_raw["date"])
df_raw = df_raw[df_raw["date"] >= pd.to_datetime("2014-01")]
if "entity_name" not in df_raw.columns:
    df_raw["entity_name"] = df_raw["entity_code"]
else:
    df_raw["entity_name"] = df_raw["entity_name"].fillna(df_raw["entity_code"])

# --- AGGREGATI EUR & WORLD ---
def add_aggregates(df):
    for freq in df["frequency"].unique():
        subset = df[df["frequency"] == freq]
        eur = subset[subset["entity_code"].isin(EU_ISO3)].groupby(["date", "series"], as_index=False)["generation_twh"].sum()
        eur["entity_code"] = "EUR"
        eur["entity_name"] = "Europe"
        eur["frequency"] = freq

        world = subset.groupby(["date", "series"], as_index=False)["generation_twh"].sum()
        world["entity_code"] = "WORLD"
        world["entity_name"] = "World"
        world["frequency"] = freq

        df = pd.concat([df, eur, world], ignore_index=True)
    return df

df_raw = add_aggregates(df_raw)

# --- CALCOLO SHARE ---
total_gen = df_raw.groupby(["entity_code", "date", "frequency"])["generation_twh"].sum().reset_index()
total_gen.rename(columns={"generation_twh": "total"}, inplace=True)
df_raw = df_raw.merge(total_gen, on=["entity_code", "date", "frequency"], how="left")
df_raw["share_of_generation_pct"] = (df_raw["generation_twh"] / df_raw["total"] * 100).round(2)
df_raw.drop(columns="total", inplace=True)

# --- COLONNA BOY ---
df_raw["month_key"] = df_raw["date"].dt.strftime("%m-%Y")
df_raw["boy_key"] = "01-" + df_raw["date"].dt.year.astype(str)
ref = df_raw[["entity_code", "series", "boy_key", "generation_twh", "frequency"]].rename(
    columns={"generation_twh": "boy_value", "boy_key": "month_key"}
)
df_raw = df_raw.merge(ref, on=["entity_code", "series", "month_key", "frequency"], how="left")
df_raw["% BOY"] = df_raw.apply(
    lambda r: 0 if r["boy_value"] == 0 else round((r["generation_twh"] - r["boy_value"]) / r["boy_value"] * 100, 2),
    axis=1
)
df_raw.drop(columns=["boy_value", "month_key"], inplace=True)

# --- RINOMINA ---
df = df_raw.rename(columns={
    "entity_code": "Country",
    "entity_name": "Country Name",
    "date": "Date",
    "series": "Source",
    "generation_twh": "Generation (TWh)",
    "share_of_generation_pct": "Share (%)"
})

# --- AGGREGATI Total, Green, Brown ---
def aggregate_series(df, label, sources):
    group = df[df["Source"].isin(sources)].groupby(["Country", "Country Name", "Date", "frequency"], as_index=False)[
        "Generation (TWh)"].sum()
    group["Source"] = label

    total = df[df["Source"] != label].groupby(["Country", "Date", "frequency"])["Generation (TWh)"].sum().reset_index()
    total.rename(columns={"Generation (TWh)": "total"}, inplace=True)
    group = group.merge(total, on=["Country", "Date", "frequency"], how="left")
    group["Share (%)"] = (group["Generation (TWh)"] / group["total"] * 100).round(2)

    group["boy_key"] = "01-" + group["Date"].dt.year.astype(str)
    group["month_key"] = group["Date"].dt.strftime("%m-%Y")
    ref = group[["Country", "Source", "boy_key", "Generation (TWh)", "frequency"]].rename(
        columns={"Generation (TWh)": "boy_value", "boy_key": "month_key"}
    )
    group = group.merge(ref, on=["Country", "Source", "month_key", "frequency"], how="left")
    group["% BOY"] = group.apply(
        lambda r: 0 if r["boy_value"] == 0 else round((r["Generation (TWh)"] - r["boy_value"]) / r["boy_value"] * 100, 2),
        axis=1
    )
    group.drop(columns=["boy_value", "month_key"], inplace=True)
    return group

df_total = df.groupby(["Country", "Country Name", "Date", "frequency"], as_index=False)[["Generation (TWh)"]].sum()
df_total["Source"] = "Total"
df_total["Share (%)"] = 100.0
df_total = aggregate_series(df_total, "Total", [])

df_green = aggregate_series(df, "Green", GREEN_SOURCES)
df_brown = aggregate_series(df, "Brown", BROWN_SOURCES)

df_all = pd.concat([df, df_total, df_green, df_brown], ignore_index=True)
df_all = df_all.sort_values(["Country", "Source", "Date"])
df_all["Date_str"] = df_all["Date"].dt.strftime("%m-%Y")

# --- CALCOLO YOY ---
df_yoy = df_all.copy()
df_last = df_yoy.copy()
df_last["Date"] = df_last["Date"] + pd.DateOffset(years=1)
df_yoy = df_yoy.merge(
    df_last[["Country", "Source", "Date", "Generation (TWh)", "frequency"]],
    on=["Country", "Source", "Date", "frequency"],
    suffixes=("", "_last"),
    how="left"
)
df_yoy["YoY Variation (%)"] = df_yoy.apply(
    lambda r: 0 if r["Generation (TWh)_last"] == 0 else round((r["Generation (TWh)"] - r["Generation (TWh)_last"]) / r["Generation (TWh)_last"] * 100, 2),
    axis=1
)
df_yoy.drop(columns=["Generation (TWh)_last"], inplace=True)

# --- TABELLA ---
st.subheader("Tabella Produzione Elettrica")
selected_freq = st.radio("Frequenza:", ["monthly", "annual"])
filtered = df_yoy[df_yoy["frequency"] == selected_freq]

country = st.selectbox("Seleziona un paese:", sorted(filtered["Country Name"].unique()))
sources = st.multiselect("Seleziona una fonte:", sorted(filtered["Source"].unique()), default=sorted(filtered["Source"].unique()))
years = st.multiselect("Anni:", sorted(filtered["Date"].dt.year.unique().astype(str)), default=sorted(filtered["Date"].dt.year.unique().astype(str)))

df_table = filtered[
    (filtered["Country Name"] == country) &
    (filtered["Source"].isin(sources)) &
    (filtered["Date"].dt.year.astype(str).isin(years))
].copy()
df_table["Date"] = df_table["Date"].dt.strftime("%m-%Y") if selected_freq == "monthly" else df_table["Date"].dt.year.astype(str)

def color(val):
    if pd.isna(val): return ""
    return "color: green" if val > 0 else "color: red" if val < 0 else "color: black"

styled = df_table[["Country Name", "Date", "Source", "Generation (TWh)", "Share (%)", "YoY Variation (%)", "% BOY"]].style \
    .applymap(color, subset=["YoY Variation (%)", "% BOY"]) \
    .format("{:.2f}", subset=["Generation (TWh)", "Share (%)", "YoY Variation (%)", "% BOY"])

st.dataframe(styled, use_container_width=True)
st.download_button("Scarica Dati Tabella", df_table.to_csv(index=False), "dati_tabella.csv", "text/csv")
st.download_button("Scarica DB Completo", df_yoy.to_csv(index=False), "db_completo.csv", "text/csv")

# --- GRAFICO ---
st.subheader("Grafico Quota di Generazione Elettrica per Fonte")

ordered_sources = ["Coal", "Gas", "Other fossil", "Nuclear", "Solar", "Wind", "Hydro", "Bioenergy", "Other renewables"]
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

graph_country = st.selectbox("Seleziona un paese per il grafico:", sorted(df["Country"].unique()), key="graph_country")
metric_choice = st.radio("Seleziona la metrica da visualizzare:", ["Share", "YoY"])
selected_sources = st.multiselect("Seleziona le fonti da visualizzare nel grafico:", options=ordered_sources, default=ordered_sources)

df_graph = df_yoy[(df_yoy["Country"] == graph_country) & (df_yoy["frequency"] == "monthly")].copy()
df_graph = df_graph[df_graph["Source"].isin(selected_sources)]
df_graph["Source"] = pd.Categorical(df_graph["Source"], categories=ordered_sources, ordered=True)

if metric_choice == "Share":
    y_col = "Share (%)"
    y_title = "Quota (%)"
    y_range = [0, 100]
else:
    y_col = "YoY Variation (%)"
    y_title = "Variazione YoY (%)"
    y_min = df_graph[y_col].min()
    y_max = df_graph[y_col].max()
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

    buf = BytesIO()
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
