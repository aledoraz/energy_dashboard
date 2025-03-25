import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
from io import BytesIO
import plotly.express as px

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Dashboard Generazione Elettrica", layout="wide")

# --- API KEY ---
API_KEY = st.secrets["API_KEY"]

# --- SCARICA DATI ---
def get_ember_data(frequency):
    base_url = "https://api.ember-energy.org"
    url = (
        f"{base_url}/v1/electricity-generation/{frequency}"
        f"?entity_code=ARG,ARM,AUS,AUT,AZE,BGD,BLR,BEL,BOL,BIH,BRA,BGR,CAN,CHL,CHN,COL,CRI,HRV,CYP,CZE,DNK,DOM,"
        f"ECU,EGY,SLV,EST,FIN,FRA,GEO,DEU,GRC,HUN,IND,IRN,IRL,ITA,JPN,KAZ,KEN,KWT,KGZ,LVA,LTU,LUX,MYS,MLT,"
        f"MEX,MDA,MNG,MNE,MAR,NLD,NZL,NGA,MKD,NOR,OMN,PAK,PER,PHL,POL,PRT,PRI,QAT,ROU,RUS,SRB,SGP,SVK,SVN,"
        f"ZAF,KOR,ESP,LKA,SWE,CHE,TWN,TJK,THA,TUN,TUR,UKR,GBR,USA,URY,VNM"
        f"&start_date=2000-01&end_date=2025-12"
        f"&series=Bioenergy,Coal,Gas,Hydro,Nuclear,Other fossil,Other renewables,Solar,Wind"
        f"&is_aggregate_series=false&include_all_dates_value_range=true&api_key={API_KEY}"
    )

    for _ in range(5):
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            df = pd.DataFrame(data["data"])
            df["frequency"] = frequency
            return df
        time.sleep(5)
    return pd.DataFrame()

# --- SCARICA MENSILI E ANNUALI ---
df_monthly = get_ember_data("monthly")
df_annual = get_ember_data("annual")
df_raw = pd.concat([df_monthly, df_annual], ignore_index=True)

# --- CHECK DATI ---
if df_raw.empty:
    st.warning("❌ Nessun dato disponibile.")
    st.stop()

# --- BASE ---
df_raw["date"] = pd.to_datetime(df_raw["date"])
df_raw = df_raw[df_raw["date"] >= pd.to_datetime("2014-01")]

# --- AGGREGAZIONI EUR e WORLD ---
europe_iso3 = [
    "ALB", "AUT", "BEL", "BIH", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL",
    "ITA", "LVA", "LTU", "LUX", "MLT", "MDA", "MNE", "NLD", "MKD", "NOR", "POL", "PRT", "ROU", "SRB", "SVK", "SVN", "ESP",
    "SWE", "CHE", "UKR", "GBR", "XKX"
]

df_list = [df_raw]
for freq in df_raw["frequency"].unique():
    df_sub = df_raw[df_raw["frequency"] == freq]
    eur = df_sub[df_sub["entity_code"].isin(europe_iso3)].groupby(["date", "series"], as_index=False)["generation_twh"].sum()
    eur["entity_code"] = "EUR"
    eur["frequency"] = freq
    df_list.append(eur)

    wld = df_sub.groupby(["date", "series"], as_index=False)["generation_twh"].sum()
    wld["entity_code"] = "WORLD"
    wld["frequency"] = freq
    df_list.append(wld)

df_raw = pd.concat(df_list, ignore_index=True)

# --- CALCOLO SHARE ---
total = df_raw.groupby(["entity_code", "date", "frequency"])["generation_twh"].sum().reset_index().rename(columns={"generation_twh": "total"})
df_raw = df_raw.merge(total, on=["entity_code", "date", "frequency"], how="left")
df_raw["share_of_generation_pct"] = (df_raw["generation_twh"] / df_raw["total"] * 100).round(2)
df_raw.drop(columns="total", inplace=True)

# --- COLONNA BOY ---
df_raw["month_year"] = df_raw["date"].dt.strftime("%m-%Y")
df_raw["boy_key"] = "01-" + df_raw["date"].dt.year.astype(str)
ref = df_raw[["entity_code", "series", "month_year", "generation_twh", "frequency"]].rename(
    columns={"month_year": "boy_key", "generation_twh": "boy_value"}
)
df_raw = df_raw.merge(ref, on=["entity_code", "series", "boy_key", "frequency"], how="left")
df_raw["% BOY"] = df_raw.apply(
    lambda r: 0 if r["boy_value"] == 0 else round((r["generation_twh"] - r["boy_value"]) / r["boy_value"] * 100, 2),
    axis=1
)
df_raw.drop(columns=["boy_value", "boy_key"], inplace=True)

# --- RINOMINA ---
df = df_raw.rename(columns={
    "entity_code": "Country",
    "date": "Date",
    "series": "Source",
    "generation_twh": "Generation (TWh)",
    "share_of_generation_pct": "Share (%)"
})

# --- AGGREGA SERIE ---
def aggregate_series(df, label, sources):
    group = df[df["Source"].isin(sources)].groupby(["Country", "Date", "frequency"], as_index=False)["Generation (TWh)"].sum()
    group["Source"] = label

    total = df[df["Source"] != label].groupby(["Country", "Date", "frequency"])["Generation (TWh)"].sum().reset_index()
    total.rename(columns={"Generation (TWh)": "total"}, inplace=True)
    group = group.merge(total, on=["Country", "Date", "frequency"], how="left")
    group["Share (%)"] = (group["Generation (TWh)"] / group["total"] * 100).round(2)

    # BOY
    group["month_year"] = group["Date"].dt.strftime("%m-%Y")
    group["boy_key"] = "01-" + group["Date"].dt.year.astype(str)
    ref = group[["Country", "Source", "month_year", "Generation (TWh)", "frequency"]].rename(columns={
        "month_year": "boy_key", "Generation (TWh)": "boy_value"
    })
    group = group.merge(ref, on=["Country", "Source", "boy_key", "frequency"], how="left")
    group["% BOY"] = group.apply(
        lambda r: 0 if r["boy_value"] == 0 else round((r["Generation (TWh)"] - r["boy_value"]) / r["boy_value"] * 100, 2),
        axis=1
    )
    group.drop(columns=["boy_value", "boy_key"], inplace=True)
    return group

df_total = df.groupby(["Country", "Date", "frequency"], as_index=False)["Generation (TWh)"].sum()
df_total["Source"] = "Total"
df_total["Share (%)"] = 100.0
df_total = aggregate_series(df_total, "Total", [])

green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables", "Nuclear"]
brown_sources = ["Coal", "Gas", "Other fossil"]
df_green = aggregate_series(df, "Green", green_sources)
df_brown = aggregate_series(df, "Brown", brown_sources)

df_all = pd.concat([df, df_total, df_green, df_brown], ignore_index=True)
df_all["Date_str"] = df_all["Date"].dt.strftime("%m-%Y")

# --- YOY ---
df_last = df_all.copy()
df_last["Date"] = df_last["Date"] + pd.DateOffset(years=1)
df_yoy = df_all.merge(
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

country = st.selectbox("Seleziona un paese:", sorted(filtered["Country"].unique()))
sources = st.multiselect("Seleziona una fonte:", sorted(filtered["Source"].unique()), default=sorted(filtered["Source"].unique()))
years = st.multiselect("Anni:", sorted(filtered["Date"].dt.year.unique().astype(str)), default=sorted(filtered["Date"].dt.year.unique().astype(str)))

df_table = filtered[
    (filtered["Country"] == country) &
    (filtered["Source"].isin(sources)) &
    (filtered["Date"].dt.year.astype(str).isin(years))
].copy()
df_table["Date"] = df_table["Date"].dt.strftime("%m-%Y") if selected_freq == "monthly" else df_table["Date"].dt.year.astype(str)

def color(val):
    if pd.isna(val): return ""
    return "color: green" if val > 0 else "color: red" if val < 0 else "color: black"

styled = df_table[["Country", "Date", "Source", "Generation (TWh)", "Share (%)", "YoY Variation (%)", "% BOY"]].style \
    .applymap(color, subset=["YoY Variation (%)", "% BOY"]) \
    .format("{:.2f}", subset=["Generation (TWh)", "Share (%)", "YoY Variation (%)", "% BOY"])

st.dataframe(styled, use_container_width=True)
st.download_button("Scarica Dati Tabella", df_table.to_csv(index=False), "dati_tabella.csv", "text/csv")
st.download_button("Scarica DB Completo", df_yoy.to_csv(index=False), "db_completo.csv", "text/csv")

# --- GRAFICO ---
st.subheader("Grafico Quota di Generazione Elettrica per Fonte")

ordered_sources = ["Coal", "Gas", "Other fossil", "Nuclear", "Solar", "Wind", "Hydro", "Bioenergy", "Other renewables", "Green", "Brown", "Total"]
color_map = {
    "Coal": "#4d4d4d",
    "Other fossil": "#a6a6a6",
    "Gas": "#b5651d",
    "Nuclear": "#ffdd44",
    "Solar": "#87CEEB",
    "Wind": "#aec7e8",
    "Hydro": "#1f77b4",
    "Bioenergy": "#2ca02c",
    "Other renewables": "#17becf",
    "Green": "#2ecc71",
    "Brown": "#e67e22",
    "Total": "#333333"
}

graph_country = st.selectbox("Seleziona un paese per il grafico:", sorted(df_yoy["Country"].unique()), key="graph_country")
metric_choice = st.radio("Seleziona la metrica da visualizzare:", ["Share", "YoY"])
selected_sources = st.multiselect("Seleziona le fonti da visualizzare nel grafico:", ordered_sources, default=ordered_sources)

df_graph = df_yoy[(df_yoy["Country"] == graph_country) & (df_yoy["frequency"] == "monthly")]
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
        st.download_button("Scarica Grafico", buf, file_name=f"grafico_{graph_country}.png", mime="image/png")
    except Exception:
        st.warning("⚠️ Kaleido non installato, impossibile scaricare il grafico come PNG.")
else:
    st.warning("Nessun dato disponibile per il grafico!")
