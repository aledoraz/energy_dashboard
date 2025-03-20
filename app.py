df = df.sort_values(by=["Country", "Source", "Date"])
df["Date"] = pd.to_datetime(df["Date"], format='%m-%Y')

# Creiamo una copia del dataset con l'anno spostato di +1 per il confronto
df_last_year = df.copy()
df_last_year["Date"] = df_last_year["Date"] + pd.DateOffset(years=1)
df = df.merge(df_last_year[["Country", "Source", "Date", "Generation (TWh)"]], 
              on=["Country", "Source", "Date"], 
              suffixes=("", "_last_year"), 
              how="left")
df["YoY Variation (%)"] = ((df["Generation (TWh)"] - df["Generation (TWh)_last_year"]) / df["Generation (TWh)_last_year"]) * 100
df["YoY Variation (%)"] = df["YoY Variation (%)"].round(2)
df.drop(columns=["Generation (TWh)_last_year"], inplace=True)
df_yoy = df[["Country", "Date", "Source", "Generation (TWh)", "Share (%)", "YoY Variation (%)"]]

# Converti la colonna Date in stringa ed estrai i primi 10 caratteri
df_yoy["Date"] = df_yoy["Date"].astype(str).str[:10]

# --- VISUALIZZAZIONE ---
col1, col2 = st.columns([2, 3])
with col1:
    st.subheader("📊 Produzione Elettricità YoY")
    paese_scelto = st.selectbox("Seleziona un paese:", df["Country"].unique())
    df_paese = df_yoy[df_yoy["Country"] == paese_scelto]
    st.write(df_paese.style.format({
        "Generation (TWh)": "{:.2f}", 
        "Share (%)": "{:.2f}", 
        "YoY Variation (%)": "{:.2f}"
    }))
    st.download_button("📥 Scarica Dati", df_paese.to_csv(index=False), "dati_variation.csv", "text/csv")
    
with col2:
    st.subheader("📈 Quota di Generazione Elettrica per Fonte")
    fig, ax = plt.subplots(figsize=(10, 5))
    df_plot = df_paese[~df_paese["Source"].isin(["Total", "Green", "Brown"])].pivot(index='Date', columns='Source', values='Share (%)')
    df_plot.plot(kind='area', stacked=True, alpha=0.7, ax=ax, color=[color_map[s] for s in df_plot.columns])
    ax.set_title(f"Quota di Generazione - {paese_scelto}")
    ax.set_ylabel('%')
    ax.set_ylim(0, 100)
    plt.xlabel('Anno')
    plt.tight_layout()
    st.pyplot(fig)
