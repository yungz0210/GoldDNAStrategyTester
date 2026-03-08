import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from engine import calculate_integrity_score

st.set_page_config(page_title="Strategy DNA Tester", layout="wide")

st.title("The Strategy DNA Tester - Integrity Score")
st.markdown("""
Upload your MT5 Backtest and Live Trade CSVs to analyze strategy robustness and detect curve fitting.
""")

col1, col2 = st.columns(2)
with col1:
    backtest_file = st.file_uploader("Upload Backtest CSV", type=["csv"])
with col2:
    live_file = st.file_uploader("Upload Live CSV", type=["csv"])

if backtest_file and live_file:
    df_bt = pd.read_csv(backtest_file)
    df_live = pd.read_csv(live_file)

    # Require 'PnL' column for MVP calculations
    if 'PnL' not in df_bt.columns or 'PnL' not in df_live.columns:
        st.error("Error: CSVs must contain a 'PnL' column.")
    else:
        results = calculate_integrity_score(df_bt, df_live)

        # Display Integrity Score
        st.subheader("Integrity Score")
        score = results['IntegrityScore']

        # Gauge Chart
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = score,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Strategy Integrity Score"},
            gauge = {
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 50], 'color': "red"},
                    {'range': [50, 80], 'color': "yellow"},
                    {'range': [80, 100], 'color': "green"}
                ],
                'threshold': {
                    'line': {'color': "white", 'width': 4},
                    'thickness': 0.75,
                    'value': 80
                }
            }
        ))

        st.plotly_chart(fig)

        # Components breakdown
        st.subheader("Score Components")
        c1, c2, c3 = st.columns(3)
        c1.metric(label="Profit Factor Retention", value=f"{results['Components']['R_PF']*100:.1f}%")
        c2.metric(label="Drawdown Penalty", value=f"{results['Components']['P_DD']*100:.1f}%")
        c3.metric(label="Expectancy Match", value=f"{results['Components']['M_E']*100:.1f}%")

        # Z-Score
        st.subheader("Advanced DNA Z-Score Check")
        z_col1, z_col2 = st.columns(2)
        z_col1.metric(label="Z-Score", value=f"{results['ZScore']:.2f}")
        z_col2.metric(label="DNA Status", value=results['DNA_Status'])

        st.markdown(f"**Interpretation:** {results['DNA_Status']}")
        if results['ZScore'] < -2.0:
            st.warning("The live strategy is performing significantly worse than the backtest. The backtest is likely curve-fitted.")
        elif -1.96 <= results['ZScore'] <= 1.96:
            st.success("The live results match the backtest DNA (95% confidence).")
        else:
            st.info("The live strategy is overperforming expectations in an anomalous way. The backtest edge may not map 1:1, or sample size is small.")
