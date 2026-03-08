import pandas as pd
import numpy as np
import math

def calculate_metrics(df: pd.DataFrame) -> dict:
    """
    Calculates standard trading metrics required for the Integrity Score.

    Assumes df has at least: 'PnL'
    (Optionally, for real world use, it might need 'Balance' over time to calc exact DD,
    but we will approximate based on cumulative PnL for now or assume DD is provided).
    """

    # Basic PnL stats
    profits = df[df['PnL'] > 0]['PnL']
    losses = df[df['PnL'] < 0]['PnL']

    gross_profit = profits.sum()
    gross_loss = abs(losses.sum())

    # 1. Profit Factor
    if gross_loss == 0:
        pf = float('inf') if gross_profit > 0 else 1.0
    else:
        pf = gross_profit / gross_loss

    # 2. Maximum Drawdown (based on Cumulative PnL)
    # Note: In a real scenario, DD is often calculated based on Equity/Balance percentage.
    # Here we use the cumulative PnL drop from the peak as an absolute value for demonstration.
    cum_pnl = df['PnL'].cumsum()
    running_max = cum_pnl.cummax()
    drawdown = running_max - cum_pnl
    max_dd_abs = drawdown.max()

    # We'll normalize this later if needed, but for the ratio, absolute DD works if starting balances are similar.
    # To be safe and comparable, let's assume we return absolute Max DD.

    # 3. Expectancy
    total_trades = len(df)
    if total_trades == 0:
        return {'PF': 1.0, 'DD': 0.0, 'Expectancy': 0.0, 'MeanReturn': 0.0, 'StdReturn': 0.0, 'TotalTrades': 0}

    win_rate = len(profits) / total_trades
    loss_rate = len(losses) / total_trades

    avg_win = profits.mean() if not profits.empty else 0.0
    avg_loss = abs(losses.mean()) if not losses.empty else 0.0

    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

    # Stats for Z-score
    mean_return = df['PnL'].mean()
    std_return = df['PnL'].std()

    return {
        'PF': pf,
        'DD': max_dd_abs,
        'Expectancy': expectancy,
        'MeanReturn': mean_return,
        'StdReturn': std_return,
        'TotalTrades': total_trades
    }

def calculate_integrity_score(df_backtest: pd.DataFrame, df_live: pd.DataFrame) -> dict:
    """
    Calculates the Integrity Score (0-100) and the DNA Z-Score based on the provided mathematical model.
    """
    bt_metrics = calculate_metrics(df_backtest)
    live_metrics = calculate_metrics(df_live)

    # 1. Profit Factor Retention (R_PF) - Weight: 40%
    pf_bt = bt_metrics['PF']
    pf_live = live_metrics['PF']

    if pf_bt <= 1.0:
        r_pf = 0.0 # Backtest had no edge to begin with
    else:
        r_pf = max(0.0, min(1.0, (pf_live - 1.0) / (pf_bt - 1.0)))

    # 2. Drawdown Expansion Penalty (P_DD) - Weight: 30%
    dd_bt = bt_metrics['DD']
    dd_live = live_metrics['DD']

    if dd_live == 0.0:
        p_dd = 1.0
    elif dd_bt == 0.0:
        p_dd = 0.0 # Backtest had 0 DD, live has some DD -> penalty
    else:
        p_dd = min(1.0, dd_bt / dd_live)

    # 3. Trade Expectancy Match (M_E) - Weight: 30%
    e_bt = bt_metrics['Expectancy']
    e_live = live_metrics['Expectancy']

    if e_bt <= 0.0:
        m_e = 0.0
    else:
        # We only care about positive expectancy matching
        m_e = max(0.0, min(1.0, e_live / e_bt))

    # The Final Composite Formula
    i_score = (0.40 * r_pf + 0.30 * p_dd + 0.30 * m_e) * 100.0

    # Advanced Upgrade: The "DNA" Z-Score Check
    mu_live = live_metrics['MeanReturn']
    mu_bt = bt_metrics['MeanReturn']
    sigma_bt = bt_metrics['StdReturn']
    n_live = live_metrics['TotalTrades']

    if sigma_bt == 0.0 or n_live == 0 or pd.isna(sigma_bt):
        z_score = 0.0
    else:
        z_score = (mu_live - mu_bt) / (sigma_bt / math.sqrt(n_live))

    # Determine Status based on Z-Score
    if z_score >= -1.96 and z_score <= 1.96:
        dna_status = "Match (95% confidence)"
    elif z_score < -2.0:
        dna_status = "Broken / Curve-Fitted"
    else:
        dna_status = "Overperforming / Anomalous"

    return {
        'IntegrityScore': i_score,
        'Components': {
            'R_PF': r_pf,
            'P_DD': p_dd,
            'M_E': m_e
        },
        'ZScore': z_score,
        'DNA_Status': dna_status,
        'BacktestMetrics': bt_metrics,
        'LiveMetrics': live_metrics
    }
