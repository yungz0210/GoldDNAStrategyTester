# The Strategy DNA Tester: Complete End-to-End Workflow

The Strategy DNA Tester is a professional SaaS application and consulting tool designed to rigorously audit automated trading systems (MetaTrader 5 Expert Advisors).

It prevents traders from being scammed by curve-fitted backtests, calculates the exact probability of passing Prop Firm evaluations, and uses Machine Learning to macro-filter live trading environments.

Here is the complete workflow, from generating data in MT5 to visualizing the final ML Equity Curve.

---

## Step 1: Extract the Backtest DNA (MetaTrader 5)
You have developed a strategy—for example, the "EMA Gold Crossover" EA. You run a 1-year backtest in the MT5 Strategy Tester. The equity curve looks like a perfect 45-degree angle. **Is it real, or is it curve-fitted?**

To find out, you need to extract its "DNA."
1. Open your EA's source code in MetaEditor.
2. Add `#include <StrategyDNA.mqh>` to the top of your code.
3. Inside your `OnDeinit()` function, add this single line:
   ```cpp
   ExportStrategyDNA("gold_backtest");
   ```
4. Recompile the EA and run your Strategy Tester backtest.
5. When the backtest finishes, look at your **"Journal"** tab. You will see:
   `StrategyDNA: SUCCESS! You can find your file at: Terminal/Common/Files/gold_backtest_20231015_143022.csv`
   *(This CSV contains every trade, exactly when it opened/closed, the Profit/Loss, and crucially: the exact 14-period ATR, 20-period StdDev, and MAE/MFE at the precise second the trade executed).*

---

## Step 2: Extract the Live Execution (MetaTrader 5)
You (or your client) plug this "perfect" Gold EA into a live $10,000 account. After 3 months, the account is losing money. Why did it break?

To find out, you extract the live trading history:
1. Drag the `DataExtractor.mq5` script directly onto your live MT5 chart.
2. Look at your **"Experts"** tab. It will say:
   `StrategyDNA: SUCCESS! You can find your file at: Terminal/Common/Files/live_results_20231015_143500.csv`

---

## Step 3: The Integrity Score (Python / Streamlit)
You open the Streamlit Web Dashboard and upload **both** CSV files.

The app's mathematical engine instantly compares the two datasets to calculate the **Integrity Score (0-100)**:
*   **Profit Factor Retention (40%):** In the backtest, your Profit Factor was 3.5. Live, it is 1.1. You lost 80% of your edge to slippage and spread.
*   **Drawdown Penalty (30%):** Your backtest max drawdown was 5%. Live, you hit a 15% drawdown. The strategy is penalized heavily.
*   **Expectancy Match (30%):** You expected to make $15 per trade. Live, you are making $2 per trade.
*   **The DNA Z-Score:** The app calculates the statistical variance between the two datasets. If your Z-Score is `-3.5`, the dashboard flashes **RED**.
    *   *Conclusion:* The live trades do not belong to the same mathematical distribution as the backtest. The strategy is officially flagged as **"Curve-Fitted / Broken"**.

---

## Step 4: BI & Regime Analysis
Now that you know the strategy is broken, you want to know *why*. You click the **"BI & Regime Analysis"** tab (analyzing just the live data).

1.  **Regime Terciles:** The app splits your trades into "Low Volatility," "Normal," and "High Volatility" regimes based on the ATR recorded at execution. You discover the EA has a 70% Win Rate in High Volatility, but a disastrous 30% Win Rate in Low Volatility.
2.  **Session Heatmaps:** The interactive Plotly heatmap shows that trades taken between 14:00 and 16:00 (New York open) are highly profitable, while trades taken during the Asian session (01:00 to 04:00) bleed money.

---

## Step 5: Prop-Firm Monte Carlo Simulator
Your client wants to know if this EA can pass a $100,000 FTMO Challenge (5% Max Daily Drawdown, 10% Max Total Drawdown, 10% Profit Target).

You click the **"Prop-Firm Monte Carlo"** tab:
1.  You set the sliders: $100,000 Balance, 5% Daily DD, 10% Total DD, 10% Target.
2.  The engine runs **1,000 Bootstrapped Simulations**, randomly reshuffling the live trades into simulated "days."
3.  **The Output:** The app generates 1,000 alternate realities. It reveals a **65% Probability of Ruin** (failing the challenge).
    *   *Insight:* Even if the strategy is technically profitable over a year, its sequence-of-returns risk is too high. The simulated equity curves visually show that 40% of paths hit the 5% Daily Drawdown limit within the first 10 days.

---

## Step 6: Machine Learning Macro-Filter (Phase 4)
You now know the EA struggles in low volatility and fails Prop Firm challenges due to choppy drawdown streaks. You decide to build a Machine Learning filter to fix it.

You click the **"ML Strategy Filter"** tab:
1.  You enter the yfinance ticker `GC=F` (Gold Futures).
2.  The app downloads the daily Gold data and engineers macro features (14-ADX, 14-ATR, Distance from the 200 SMA, Daily Return).
3.  **Look-Ahead Bias Prevention:** The app safely shifts these features forward by 1 day. It trains a `RandomForestClassifier` (using a 5-fold Walk-Forward `TimeSeriesSplit`) to predict if *Today* will be "Trending" or "Choppy" based on *Yesterday's* closing data.
4.  **Data Fusion:** The app merges these daily ML predictions with your intraday M5 MT5 trades. It completely deletes any trades your EA took on days the AI predicted would be "Choppy."
5.  **The Final Result:** The app plots the "Original Equity Curve" vs the "ML-Filtered Equity Curve" side-by-side.
    *   *Outcome:* By filtering out the choppy days, Total Trades drop from 500 to 250, but the Win Rate jumps from 45% to 62%. The Profit Factor doubles, and the Max Drawdown is cut in half. The strategy is saved!