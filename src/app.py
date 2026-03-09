import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from engine import calculate_integrity_score, analyze_regimes, calculate_session_metrics, run_prop_firm_monte_carlo

st.set_page_config(page_title="Strategy DNA Tester", layout="wide")
st.title("The Strategy DNA Tester")
st.markdown("""
A robust SaaS tool blending a Prop Firm Performance Auditor with an MQL5 Strategy Stress-Tester.
""")

col1, col2 = st.columns(2)
with col1:
    backtest_file = st.file_uploader("Upload Backtest CSV (Optional)", type=["csv"])
with col2:
    live_file = st.file_uploader("Upload Live CSV (Optional)", type=["csv"])

# Determine if we have any data to analyze
has_backtest = backtest_file is not None
has_live = live_file is not None

if has_backtest or has_live:
    df_bt = pd.read_csv(backtest_file) if has_backtest else None
    df_live = pd.read_csv(live_file) if has_live else None

    # Validation check
    valid_bt = df_bt is not None and 'PnL' in df_bt.columns
    valid_live = df_live is not None and 'PnL' in df_live.columns

    if (has_backtest and not valid_bt) or (has_live and not valid_live):
        st.error("Error: Uploaded CSVs must contain a 'PnL' column. Please use the MQL5 DataExtractor script.")
    else:
        tab1, tab2, tab3 = st.tabs(["Integrity Score", "BI & Regime Analysis", "Prop-Firm Monte Carlo"])

        # Determine the primary dataframe for Regime and Monte Carlo analysis
        # If both are uploaded, let the user choose which one to analyze for Tabs 2 & 3.
        # Otherwise, default to the one that is uploaded.
        if has_backtest and has_live:
            st.sidebar.markdown("### Analysis Data Source")
            analysis_source = st.sidebar.radio(
                "Select which dataset to use for Regime Analysis and Monte Carlo:",
                ("Live Data", "Backtest Data")
            )
            df_analysis = df_live.copy() if analysis_source == "Live Data" else df_bt.copy()
            st.sidebar.info(f"Currently analyzing: **{analysis_source}**")
        else:
            df_analysis = df_live.copy() if has_live else df_bt.copy()
            source_name = "Live Data" if has_live else "Backtest Data"
            st.sidebar.info(f"Currently analyzing: **{source_name}**")

        # --- TAB 1: INTEGRITY SCORE ---
        with tab1:
            if not (has_backtest and has_live):
                st.info("ℹ️ **Integrity Score Requires Both Files.** Please upload both a Backtest CSV and a Live CSV to calculate the statistical degradation and curve-fitting score.")
            else:
                results = calculate_integrity_score(df_bt, df_live)

                st.subheader("Integrity Score")
                score = results['IntegrityScore']

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
                st.plotly_chart(fig, use_container_width=True)

                st.subheader("Score Components")
                c1, c2, c3 = st.columns(3)
                c1.metric(label="Profit Factor Retention", value=f"{results['Components']['R_PF']*100:.1f}%")
                c2.metric(label="Drawdown Penalty", value=f"{results['Components']['P_DD']*100:.1f}%")
                c3.metric(label="Expectancy Match", value=f"{results['Components']['M_E']*100:.1f}%")

                st.subheader("Advanced DNA Z-Score Check")
                z_col1, z_col2 = st.columns(2)
                z_col1.metric(label="Z-Score", value=f"{results['ZScore']:.2f}")
                z_col2.metric(label="DNA Status", value=results['DNA_Status'])

                if results['ZScore'] < -2.0:
                    st.warning("The live strategy is performing significantly worse than the backtest. The backtest is likely curve-fitted.")
                elif -1.96 <= results['ZScore'] <= 1.96:
                    st.success("The live results match the backtest DNA (95% confidence).")
                else:
                    st.info("The live strategy is overperforming expectations in an anomalous way. The backtest edge may not map 1:1.")

        # --- TAB 2: BI & REGIME ANALYSIS ---
        with tab2:
            st.header("Regime Analysis")
            st.markdown("Breakdown of trading performance based on volatility regimes and execution session.")

            st.subheader("Market Regime Analysis (Terciles)")
            regime_indicator = st.selectbox("Select Volatility Indicator:", ["ATR", "StdDev"])

            if regime_indicator in df_analysis.columns:
                df_regimes = analyze_regimes(df_analysis, regime_indicator)
                if not df_regimes.empty:
                    st.dataframe(df_regimes, use_container_width=True)
                else:
                    st.warning("Not enough data to calculate regimes.")
            else:
                st.warning(f"Indicator '{regime_indicator}' missing from CSV.")

            st.subheader("Session Analysis Heatmap")
            if 'EntryHour' in df_analysis.columns:
                df_sessions = calculate_session_metrics(df_analysis)
                if not df_sessions.empty:
                    # Heatmap for Win Rate
                    fig_wr = px.imshow(
                        df_sessions[['Win Rate (%)']].T,
                        labels=dict(x="Hour of Day", y="", color="Win Rate (%)"),
                        x=df_sessions['EntryHour'],
                        color_continuous_scale="RdYlGn",
                        aspect="auto",
                        title="Win Rate by Trade Entry Hour"
                    )
                    st.plotly_chart(fig_wr, use_container_width=True)

                    # Heatmap for Profit Factor
                    fig_pf = px.imshow(
                        df_sessions[['Profit Factor']].T,
                        labels=dict(x="Hour of Day", y="", color="Profit Factor"),
                        x=df_sessions['EntryHour'],
                        color_continuous_scale="RdYlGn",
                        aspect="auto",
                        title="Profit Factor by Trade Entry Hour"
                    )
                    st.plotly_chart(fig_pf, use_container_width=True)
                else:
                    st.warning("No session data available.")
            else:
                st.warning("'EntryHour' missing from CSV.")

            st.subheader("Asset / Symbol Performance")
            if 'Symbol' in df_analysis.columns:
                sym_perf = df_analysis.groupby('Symbol')['PnL'].sum().reset_index()
                fig_sym = px.bar(sym_perf, x='Symbol', y='PnL', title="Net PnL by Symbol", color='PnL', color_continuous_scale="RdYlGn")
                st.plotly_chart(fig_sym, use_container_width=True)
            else:
                st.warning("'Symbol' missing from CSV.")

        # --- TAB 3: PROP-FIRM MONTE CARLO ---
        with tab3:
            st.header("Prop-Firm Monte Carlo Simulator")
            st.markdown("Stress-test the trade history against standard Prop Firm rules using bootstrapping.")

            col_mc1, col_mc2 = st.columns([1, 2])
            with col_mc1:
                st.subheader("Firm Rules")
                starting_balance = st.number_input("Starting Balance ($)", value=100000, step=10000)
                target_pct = st.slider("Profit Target (%)", 1.0, 20.0, 10.0, 0.5) / 100.0
                daily_dd_pct = st.slider("Max Daily Drawdown (%)", 1.0, 10.0, 5.0, 0.5) / 100.0
                total_dd_pct = st.slider("Max Total Drawdown (%)", 1.0, 20.0, 10.0, 0.5) / 100.0
                sims = st.selectbox("Simulations (Paths)", [1000, 5000, 10000], index=0)

                run_btn = st.button("Run Simulation", type="primary")

            with col_mc2:
                if run_btn:
                    with st.spinner("Running Monte Carlo bootstrapping..."):
                        mc_results = run_prop_firm_monte_carlo(
                            df_analysis, starting_balance, daily_dd_pct, total_dd_pct, target_pct, sims
                        )

                        if 'error' in mc_results:
                            st.error(mc_results['error'])
                        else:
                            st.success(f"Simulated {sims} paths across {mc_results['TradesPerDay']} avg trades/day.")

                            c1, c2, c3 = st.columns(3)
                            c1.metric("Probability of Passing", f"{mc_results['ProbPass']:.2f}%")
                            c2.metric("Probability of Ruin", f"{mc_results['ProbRuin']:.2f}%")
                            c3.metric("Survived (No Target)", f"{mc_results['ProbSurviveNoTarget']:.2f}%")

                            st.markdown("### Failure Breakdown")
                            st.write(f"- Failed by hitting **Daily Drawdown**: {mc_results['ProbFailDaily']:.2f}%")
                            st.write(f"- Failed by hitting **Total Drawdown**: {mc_results['ProbFailTotal']:.2f}%")

                            st.markdown("### Sample Equity Curves")
                            fig_mc = go.Figure()
                            # Plot a few paths
                            for idx, path in enumerate(mc_results['SamplePaths']):
                                # Only plot up to 50 paths to keep browser responsive
                                if idx >= 50: break
                                fig_mc.add_trace(go.Scatter(y=path, mode='lines', line=dict(width=1, color='rgba(0,100,250,0.2)'), showlegend=False))

                            # Add target and total DD lines
                            fig_mc.add_hline(y=starting_balance * (1 + target_pct), line_dash="dash", line_color="green", annotation_text="Profit Target")
                            fig_mc.add_hline(y=starting_balance * (1 - total_dd_pct), line_dash="dash", line_color="red", annotation_text="Max Total DD")
                            fig_mc.update_layout(title="Sample Monte Carlo Equity Paths", xaxis_title="Trades", yaxis_title="Account Balance ($)")
                            st.plotly_chart(fig_mc, use_container_width=True)
