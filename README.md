# Strategy DNA Tester

A SaaS and consulting tool that merges a Prop Firm Performance Auditor with an MQL5 Strategy Stress-Tester.

## Phase 1 MVP Components

1. **Python Analytics Engine (`src/engine.py`)**: Computes the Integrity Score (Profit Factor Retention, Drawdown Expansion Penalty, Trade Expectancy Match) and DNA Z-Score Check.
2. **Streamlit Dashboard (`src/app.py`)**: A lightweight UI to upload backtest and live trade results, visually plotting the robustness or curve-fitting score.
3. **MQL5 Data Extractor (`src/DataExtractor.mq5`)**: Extracts historical trade executions (Entry, Exit, PnL, duration) and indicator contexts (ATR, Volatility) out of MetaTrader 5 into a `csv` format.

## Setup Instructions

### Python / Streamlit

1. Install Python 3.9+
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the Streamlit Dashboard:
   ```bash
   streamlit run src/app.py
   ```

### MQL5 Data Extractor

1. Place `src/DataExtractor.mq5` into your MetaTrader 5 `MQL5/Scripts/` folder.
2. Compile the script using MetaEditor.
3. Run it once on a Backtest chart (generates `backtest_results.csv`) and once on a Live Trade History chart (generates `live_results.csv`).
4. Find the generated CSVs in your MT5 `MQL5/Files/` directory.

## Future Phases
- BI & Regime Analysis Engine
- Prop-Firm Monte Carlo Simulations Module
- Full Dockerization for SaaS Deployment