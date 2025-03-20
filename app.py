import dash
from dash import dcc, html, dash_table, Input, Output
import pandas as pd
import requests
import time
import plotly.express as px
from datetime import datetime

# Crea l'app Dash
app = dash.Dash(__name__)
server = app.server  # Per eventuale deploy

# === Funzione per recuperare i dati dall'API ===
def get_data():
    # Sostituisci 'YOUR_API_KEY' con la tua API key oppure utilizza un sistema di configurazione
    api_key = "YOUR_API_KEY"
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
                return pd.DataFrame()
        elif response.status_code == 500:
            time.sleep(20)
        else:
            return pd.DataFrame()
    return pd.DataFrame()

# === Scarica e processa i dati ===
df = get_data()

if not df.empty:
    # Seleziona e formatta le colonne utili
    df = df[["entity_code", "date", "series", "generation_twh", "share_of_generation_pct"]]
    # Converte la data e la formatta come "MM-YYYY"
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%m-%Y')
    df = df[df['date'] >= '01-2014']
    df["generation_twh"] = df["generation_twh"].round(2)

    green_sources = ["Bioenergy", "Hydro", "Solar", "Wind", "Other renewables", "Nuclear"]
    brown_sources = ["Coal", "Gas", "Other fossil"]

    # Calcola aggregati "Total"
    df_total = df.groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total["series"] = "Total"
    df_total["share_of_generation_pct"] = 100.0

    # Aggregato "Green"
    df_total_green = df[df["series"].isin(green_sources)].groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total_green["series"] = "Green"
    df_total_green["share_of_generation_pct"] = (df_total_green["generation_twh"] / df_total["generation_twh"]).round(2) * 100

    # Aggregato "Brown"
    df_total_brown = df[df["series"].isin(brown_sources)].groupby(["entity_code", "date"])["generation_twh"].sum().reset_index()
    df_total_brown["series"] = "Brown"
    df_total_brown["share_of_generation_pct"] = (df_total_brown["generation_twh"] / df_total["generation_twh"]).round(2) * 100

    # Combina i dati originali con gli aggregati
    df = pd.concat([df, df_total, df_total_green, df_total_brown], ignore_index=True)
    df["share_of_generation_pct"] = df["share_of_generation_pct"].round(2)

    # Rinomina le colonne per uniformità
    df = df.rename(columns={
        "entity_code": "Country",
        "date": "Date",
        "series": "Source",
        "generation_twh": "Generation (TWh)",
        "share_of_generation_pct": "Share (%)"
    })

    df = df.sort_values(by=["Country", "Source", "Date"])
    df["Date"] = pd.to_datetime(df["Date"], format='%m-%Y')

    # Calcola la variazione YoY
    df_last_year = df.copy()
    df_last_year["Date"] = df_last_year["Date"] + pd.DateOffset(years=1)
    df = df.merge(df_last_year[["Country", "Source", "Date", "Generation (TWh)"]],
                  on=["Country", "Source", "Date"],
                  suffixes=("", "_last_year"),
                  how="left")
    df["YoY Variation (%)"] = ((df["Generation (TWh)"] - df["Generation (TWh)_last_year"]) /
                               df["Generation (TWh)_last_year"]) * 100
    df["YoY Variation (%)"] = df["YoY Variation (%)"].round(2)
    df.drop(columns=["Generation (TWh)_last_year"], inplace=True)
    # Seleziona le colonne da visualizzare
    df_yoy = df[["Country", "Date", "Source", "Generation (TWh)", "Share (%)", "YoY Variation (%)"]]
    # Crea una colonna testuale per la data (per visualizzazione nella tabella)
    df_yoy["Date_str"] = df_yoy["Date"].dt.strftime('%m-%Y')
else:
    df_yoy = pd.DataFrame()

# Definisci una mappa colori (usata nel grafico)
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

# === Layout della Dashboard con Dash ===
app.layout = html.Div([
    html.H1("Dashboard Generazione Elettrica"),
    html.Div([
        html.Div([
            html.H3("📊 Produzione Elettricità YoY"),
            # Dropdown per selezionare il paese
            dcc.Dropdown(
                id="country-dropdown",
                options=[{"label": c, "value": c} for c in sorted(df_yoy["Country"].unique())],
                value=sorted(df_yoy["Country"].unique())[0]
            ),
            # Tabella dei dati
            dash_table.DataTable(
                id="table-data",
                columns=[{"name": col, "id": col} for col in ["Country", "Date_str", "Source", "Generation (TWh)", "Share (%)", "YoY Variation (%)"]],
                data=df_yoy.to_dict("records"),
                page_size=10,
                style_cell={'textAlign': 'center'}
            ),
            html.Br(),
            html.Button("📥 Scarica Dati", id="download-btn"),
            dcc.Download(id="download-dataframe-csv")
        ], style={"width": "45%", "display": "inline-block", "verticalAlign": "top", "padding": "10px"}),
        html.Div([
            html.H3("📈 Quota di Generazione Elettrica per Fonte"),
            dcc.Graph(id="area-chart")
        ], style={"width": "50%", "display": "inline-block", "padding": "10px"})
    ])
])

# === Callback per aggiornare la tabella e il grafico in base al paese selezionato ===
@app.callback(
    [Output("table-data", "data"),
     Output("area-chart", "figure")],
    [Input("country-dropdown", "value")]
)
def update_dashboard(selected_country):
    # Filtra i dati per il paese selezionato
    filtered_df = df_yoy[df_yoy["Country"] == selected_country]
    table_data = filtered_df.to_dict("records")
    
    # Prepara i dati per il grafico: esclude le fonti aggregate "Total", "Green", "Brown"
    filtered_plot = filtered_df[~filtered_df["Source"].isin(["Total", "Green", "Brown"])]
    if not filtered_plot.empty:
        # Per il grafico usiamo Plotly Express; l'asse x sarà la data
        pivot_df = filtered_plot.pivot(index="Date", columns="Source", values="Share (%)")
        pivot_df = pivot_df.reset_index()
        # Crea il grafico area
        fig = px.area(pivot_df, x="Date", y=pivot_df.columns[1:], title=f"Quota di Generazione - {selected_country}")
        fig.update_layout(legend=dict(x=0, y=1), yaxis_range=[0, 100],
                          xaxis_title="Anno", yaxis_title="%")
    else:
        fig = {}
    return table_data, fig

# === Callback per il download dei dati CSV ===
@app.callback(
    Output("download-dataframe-csv", "data"),
    [Input("download-btn", "n_clicks")],
    prevent_initial_call=True
)
def download_csv(n_clicks):
    return dcc.send_data_frame(df_yoy.to_csv, "dati_variation.csv", index=False)

# Avvia il server Dash
if __name__ == '__main__':
    app.run_server(debug=True)
