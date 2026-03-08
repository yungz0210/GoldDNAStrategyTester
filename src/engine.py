import pandas as pd
import numpy as np
import math

# --- PHASE 1: INTEGRITY SCORE ENGINE ---

def calculate_metrics(df: pd.DataFrame) -> dict:
    """Calculates standard trading metrics required for the Integrity Score."""
    if 'PnL' not in df.columns:
        return {'PF': 1.0, 'DD': 0.0, 'Expectancy': 0.0, 'MeanReturn': 0.0, 'StdReturn': 0.0, 'TotalTrades': 0, 'NetProfit': 0.0, 'RecoveryFactor': 0.0, 'WinRate': 0.0}

    profits = df[df['PnL'] > 0]['PnL']
    losses = df[df['PnL'] < 0]['PnL']

    gross_profit = profits.sum()
    gross_loss = abs(losses.sum())
    net_profit = df['PnL'].sum()

    if gross_loss == 0:
        pf = float('inf') if gross_profit > 0 else 1.0
    else:
        pf = gross_profit / gross_loss

    cum_pnl = df['PnL'].cumsum()
    running_max = cum_pnl.cummax()
    drawdown = running_max - cum_pnl
    max_dd_abs = drawdown.max()

    if max_dd_abs == 0:
        rf = 99.9 if net_profit > 0 else 0.0
    else:
        rf = net_profit / max_dd_abs
        # Cap recovery factor to 99.9 if requested for UI purposes
        rf = min(rf, 99.9)

    total_trades = len(df)
    if total_trades == 0:
        return {'PF': 1.0, 'DD': 0.0, 'Expectancy': 0.0, 'MeanReturn': 0.0, 'StdReturn': 0.0, 'TotalTrades': 0, 'NetProfit': 0.0, 'RecoveryFactor': 0.0, 'WinRate': 0.0}

    win_rate = len(profits) / total_trades
    loss_rate = len(losses) / total_trades

    avg_win = profits.mean() if not profits.empty else 0.0
    avg_loss = abs(losses.mean()) if not losses.empty else 0.0

    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

    mean_return = df['PnL'].mean()
    std_return = df['PnL'].std()

    return {
        'PF': pf,
        'DD': max_dd_abs,
        'Expectancy': expectancy,
        'MeanReturn': mean_return,
        'StdReturn': std_return,
        'TotalTrades': total_trades,
        'NetProfit': net_profit,
        'RecoveryFactor': rf,
        'WinRate': win_rate
    }

def calculate_integrity_score(df_backtest: pd.DataFrame, df_live: pd.DataFrame) -> dict:
    """Calculates the Integrity Score (0-100) and the DNA Z-Score based on the mathematical model."""
    bt_metrics = calculate_metrics(df_backtest)
    live_metrics = calculate_metrics(df_live)

    pf_bt = bt_metrics['PF']
    pf_live = live_metrics['PF']

    if pf_bt <= 1.0:
        r_pf = 0.0
    else:
        r_pf = max(0.0, min(1.0, (pf_live - 1.0) / (pf_bt - 1.0)))

    dd_bt = bt_metrics['DD']
    dd_live = live_metrics['DD']

    if dd_live == 0.0:
        p_dd = 1.0
    elif dd_bt == 0.0:
        p_dd = 0.0
    else:
        p_dd = min(1.0, dd_bt / dd_live)

    e_bt = bt_metrics['Expectancy']
    e_live = live_metrics['Expectancy']

    if e_bt <= 0.0:
        m_e = 0.0
    else:
        m_e = max(0.0, min(1.0, e_live / e_bt))

    i_score = (0.40 * r_pf + 0.30 * p_dd + 0.30 * m_e) * 100.0

    mu_live = live_metrics['MeanReturn']
    mu_bt = bt_metrics['MeanReturn']
    sigma_bt = bt_metrics['StdReturn']
    n_live = live_metrics['TotalTrades']

    if sigma_bt == 0.0 or n_live == 0 or pd.isna(sigma_bt):
        z_score = 0.0
    else:
        z_score = (mu_live - mu_bt) / (sigma_bt / math.sqrt(n_live))

    if z_score >= -1.96 and z_score <= 1.96:
        dna_status = "Match (95% confidence)"
    elif z_score < -2.0:
        dna_status = "Broken / Curve-Fitted"
    else:
        dna_status = "Overperforming / Anomalous"

    return {
        'IntegrityScore': i_score,
        'Components': {'R_PF': r_pf, 'P_DD': p_dd, 'M_E': m_e},
        'ZScore': z_score,
        'DNA_Status': dna_status,
        'BacktestMetrics': bt_metrics,
        'LiveMetrics': live_metrics
    }

# --- PHASE 2: BI, REGIME ANALYSIS & MONTE CARLO ---

def analyze_regimes(df: pd.DataFrame, indicator: str) -> pd.DataFrame:
    """
    Categorizes the dataset into Low, Normal, and High regimes based on terciles
    of the specified indicator (e.g., 'ATR' or 'StdDev').
    Returns a DataFrame with metrics per regime.
    """
    if indicator not in df.columns or len(df) == 0:
        return pd.DataFrame()

    # Drop NaNs for the calculation
    valid_df = df.dropna(subset=[indicator, 'PnL']).copy()
    if valid_df.empty:
        return pd.DataFrame()

    p33 = valid_df[indicator].quantile(0.33)
    p66 = valid_df[indicator].quantile(0.66)

    def categorize(val):
        if pd.isna(val): return 'Unknown'
        if val <= p33: return 'Low Volatility'
        if val <= p66: return 'Normal Volatility'
        return 'High Volatility'

    valid_df['Regime'] = valid_df[indicator].apply(categorize)

    regime_stats = []
    for regime in ['Low Volatility', 'Normal Volatility', 'High Volatility']:
        regime_df = valid_df[valid_df['Regime'] == regime]
        metrics = calculate_metrics(regime_df)

        regime_stats.append({
            'Regime': regime,
            'Total Trades': metrics['TotalTrades'],
            'Win Rate (%)': metrics['WinRate'] * 100,
            'Profit Factor': metrics['PF'] if metrics['PF'] != float('inf') else 99.9,
            'Recovery Factor': metrics['RecoveryFactor'],
            'Net Profit': metrics['NetProfit']
        })

    return pd.DataFrame(regime_stats)

def calculate_session_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Groups trades by EntryHour to calculate Win Rate and Profit Factor for heatmaps.
    """
    if 'EntryHour' not in df.columns or 'PnL' not in df.columns or df.empty:
        return pd.DataFrame()

    session_stats = []
    for hour in range(24):
        hour_df = df[df['EntryHour'] == hour]
        metrics = calculate_metrics(hour_df)
        session_stats.append({
            'EntryHour': hour,
            'Total Trades': metrics['TotalTrades'],
            'Win Rate (%)': metrics['WinRate'] * 100,
            'Profit Factor': metrics['PF'] if metrics['PF'] != float('inf') else 99.9,
            'Net Profit': metrics['NetProfit']
        })

    return pd.DataFrame(session_stats)

def run_prop_firm_monte_carlo(df: pd.DataFrame,
                              starting_balance: float = 100000.0,
                              max_daily_dd_pct: float = 0.05,
                              max_total_dd_pct: float = 0.10,
                              profit_target_pct: float = 0.10,
                              simulations: int = 1000) -> dict:
    """
    Runs a Prop Firm Monte Carlo simulation using bootstrapping with replacement.
    Groups trades into simulated "days" to check Daily Drawdown.
    """
    if 'PnL' not in df.columns or len(df) == 0:
        return {'error': 'No PnL data available'}

    trades = df['PnL'].values
    n_trades = len(trades)

    # Calculate average trades per day from the historical dataset
    if 'EntryTime' in df.columns:
        # Assuming EntryTime is string format YYYY.MM.DD HH:MM:SS or similar
        try:
            dates = pd.to_datetime(df['EntryTime']).dt.date
            unique_days = dates.nunique()
            trades_per_day = max(1, int(round(n_trades / unique_days))) if unique_days > 0 else 1
        except:
            trades_per_day = max(1, int(round(n_trades / 20))) # Fallback approx 20 days
    else:
        trades_per_day = max(1, int(round(n_trades / 20)))

    max_daily_loss_allowed = starting_balance * max_daily_dd_pct
    max_total_loss_allowed = starting_balance * max_total_dd_pct
    profit_target_amount = starting_balance * profit_target_pct

    passed_count = 0
    failed_daily_count = 0
    failed_total_count = 0
    survived_but_failed_target_count = 0

    # We will store a few random paths for visualization
    sample_paths = []

    for i in range(simulations):
        # Sample with replacement
        simulated_trades = np.random.choice(trades, size=n_trades, replace=True)

        current_balance = starting_balance
        peak_balance = starting_balance

        # Determine daily chunks
        num_days = math.ceil(n_trades / trades_per_day)

        failed = False
        passed = False

        equity_curve = [starting_balance]

        for d in range(num_days):
            if failed or passed:
                break

            day_trades = simulated_trades[d * trades_per_day : (d+1) * trades_per_day]

            # Daily DD in Prop Firms is usually based on the starting balance of THAT day
            # or the highest watermark of that day.
            # Standard: Equity cannot drop X% below the initial day's balance.
            day_start_balance = current_balance

            for t_pnl in day_trades:
                current_balance += t_pnl
                equity_curve.append(current_balance)

                if current_balance > peak_balance:
                    peak_balance = current_balance

                # Check Total DD
                if (starting_balance - current_balance) >= max_total_loss_allowed:
                    failed_total_count += 1
                    failed = True
                    break

                # Check Daily DD
                if (day_start_balance - current_balance) >= max_daily_loss_allowed:
                    failed_daily_count += 1
                    failed = True
                    break

                # Check Target (Prop firms usually pass you the moment you hit the target)
                if (current_balance - starting_balance) >= profit_target_amount:
                    passed_count += 1
                    passed = True
                    break

        if not failed and not passed:
            # Survived the period but didn't hit the target
            survived_but_failed_target_count += 1

        # Store the first 50 paths for UI charting
        if i < 50:
            sample_paths.append(equity_curve)

    prob_pass = (passed_count / simulations) * 100
    prob_fail_daily = (failed_daily_count / simulations) * 100
    prob_fail_total = (failed_total_count / simulations) * 100
    prob_survive_no_target = (survived_but_failed_target_count / simulations) * 100
    prob_ruin = prob_fail_daily + prob_fail_total

    return {
        'Simulations': simulations,
        'TradesPerDay': trades_per_day,
        'ProbPass': prob_pass,
        'ProbFailDaily': prob_fail_daily,
        'ProbFailTotal': prob_fail_total,
        'ProbSurviveNoTarget': prob_survive_no_target,
        'ProbRuin': prob_ruin,
        'SamplePaths': sample_paths
    }
