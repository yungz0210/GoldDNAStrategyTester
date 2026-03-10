# Strategy DNA Tester

A SaaS and consulting tool that merges a Prop Firm Performance Auditor with an MQL5 Strategy Stress-Tester.

## Core Components

1. **Python Analytics Engine (`src/engine.py`)**: Computes the Integrity Score, runs BI Regime Analysis (grouping trades by ATR/StdDev volatility levels), and performs Prop-Firm Monte Carlo simulations via bootstrapping.
2. **Streamlit Dashboard (`src/app.py`)**: A lightweight UI to upload backtest and live trade results, visually plotting the robustness or curve-fitting score, heatmaps, and Monte Carlo equity curves.
3. **MQL5 Strategy DNA Include (`src/StrategyDNA.mqh`)**: A plug-and-play header file for MT5 Expert Advisors that extracts historical trade executions and indicator contexts (ATR, Volatility) directly from the Strategy Tester.
4. **MQL5 Data Extractor (`src/DataExtractor.mq5`)**: Extracts Live trading history directly from a live MT5 chart.

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

### Generating CSV Files via MetaTrader 5

To analyze your data, you must generate the CSV files using our custom MQL5 tools. Standard MT5 HTML/Excel reports will not work because they lack the necessary per-tick indicator context (ATR, StdDev, MAE/MFE).

#### 1. How to get the Backtest Data (`StrategyDNA.mqh`)
Because MetaTrader 5 does not allow you to drag scripts onto a Strategy Tester Visual chart, you must include the data extractor directly in your Expert Advisor's code.
1. Copy `src/StrategyDNA.mqh` into your MT5 `MQL5/Include/` folder.
2. Open your Expert Advisor in MetaEditor and add `#include <StrategyDNA.mqh>` at the top.
3. Inside your `OnDeinit` function, call the export function:
   ```cpp
   void OnDeinit(const int reason)
     {
      // ... your existing code ...

      // Export Strategy DNA data for Streamlit
      ExportStrategyDNA("backtest_results.csv");
     }
   ```
4. Compile your EA and run a Strategy Tester backtest. When the test finishes, the file `backtest_results.csv` will be generated in your `Tester/Files/` directory.

#### 2. How to get the Live Trading Data (`DataExtractor.mq5`)
1. Place `src/DataExtractor.mq5` into your MetaTrader 5 `MQL5/Scripts/` folder and compile it.
2. Open your Live MT5 account and drag the `DataExtractor` script onto any chart.
3. It will generate `trade_results.csv` in your MT5 `MQL5/Files/` directory. (Rename it to `live_results.csv` if desired).

## Future Phases
- Full Dockerization for SaaS Deployment
- Database integration for saving user reports and parameters
- PDF Report generation for consulting hand-offs