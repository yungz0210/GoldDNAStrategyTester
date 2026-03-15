import pandas as pd
import numpy as np
import yfinance as yf
import pandas_ta as ta

# --- PHASE 1: Baseline Data Ingestion & Timezone Localization ---

def load_and_localize_mt5_data(filepath: str) -> pd.DataFrame:
    """
    Loads StrategyDNA CSV format (EntryTime, PnL, Commission, Swap, etc.).
    Calculates Net PnL.
    Localizes MT5 Broker Time (EET/EEST) to US/Eastern to align with yfinance NY close.
    """
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return pd.DataFrame()

    required_cols = ['EntryTime', 'PnL', 'Commission', 'Swap']
    for col in required_cols:
        if col not in df.columns:
            print(f"Missing required column: {col}")
            return pd.DataFrame()

    # Calculate Net PnL (in MT5, Deals already separate Commission/Swap from base Profit)
    # Note: Our StrategyDNA.mqh/DataExtractor.mq5 already calculates `PnL` as the Net PnL,
    # but we will enforce it here just in case the user modifies the output.
    df['NetPnL'] = df['PnL']

    # Convert EntryTime to datetime
    # MT5 format: YYYY.MM.DD HH:MM:SS
    df['EntryTime'] = pd.to_datetime(df['EntryTime'], format='%Y.%m.%d %H:%M:%S', errors='coerce')
    df = df.dropna(subset=['EntryTime'])

    # MT5 Servers (like MetaQuotes Demo or most Forex brokers) operate on EET/EEST (UTC+2 / UTC+3).
    # We localize the naive timestamps to 'Europe/Bucharest' (which correctly handles EET/EEST DST),
    # then convert them to 'US/Eastern' (NY Time) to align exactly with daily yfinance bars.
    df['EntryTime_NY'] = df['EntryTime'].dt.tz_localize('Europe/Bucharest').dt.tz_convert('US/Eastern')

    # Extract the calendar date in NY time to use as the merge key later
    df['TradeDate_NY'] = df['EntryTime_NY'].dt.date

    return df

def calculate_baseline_metrics(df: pd.DataFrame) -> dict:
    """Calculates standard execution metrics: Total Trades, Win Rate, Profit Factor, Max Drawdown."""
    if df.empty or 'NetPnL' not in df.columns:
        return {}

    profits = df[df['NetPnL'] > 0]['NetPnL']
    losses = df[df['NetPnL'] < 0]['NetPnL']

    total_trades = len(df)
    win_rate = (len(profits) / total_trades) * 100 if total_trades > 0 else 0.0

    gross_profit = profits.sum()
    gross_loss = abs(losses.sum())

    if gross_loss == 0:
        pf = float('inf') if gross_profit > 0 else 1.0
    else:
        pf = gross_profit / gross_loss

    # Max Drawdown based on Cumulative PnL
    cum_pnl = df['NetPnL'].cumsum()
    running_max = cum_pnl.cummax()
    drawdown = running_max - cum_pnl
    max_dd = drawdown.max()

    return {
        'Total Trades': total_trades,
        'Win Rate (%)': win_rate,
        'Profit Factor': pf,
        'Max Drawdown': max_dd,
        'Net Profit': df['NetPnL'].sum()
    }


# --- PHASE 2: Feature Engineering (yfinance Macro Data) ---

def fetch_and_engineer_macro_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Uses yfinance to pull daily OHLCV data.
    Uses pandas-ta to engineer ADX (14), ATR (14), SMA (200) Distance, and Daily Return.
    Creates a 'Target_Label' indicating Trending (1) vs Choppy (0).
    """
    # yfinance expects YYYY-MM-DD strings
    # Add a small buffer to start_date to ensure we have enough lookback data for the 200 SMA
    buffer_start = pd.to_datetime(start_date) - pd.Timedelta(days=300)

    try:
        df_yf = yf.download(symbol, start=buffer_start.strftime('%Y-%m-%d'), end=end_date)

        # Flatten MultiIndex columns if yf.download returned them (common in recent yfinance versions)
        if isinstance(df_yf.columns, pd.MultiIndex):
            # Take the first level (Price) and drop the Ticker level
            df_yf.columns = df_yf.columns.get_level_values(0)
    except Exception as e:
        print(f"Error fetching yfinance data for {symbol}: {e}")
        return pd.DataFrame()

    if df_yf.empty:
        print(f"No data returned from yfinance for {symbol}.")
        return pd.DataFrame()

    # 1. Calculate 14-period Daily ADX
    adx_df = df_yf.ta.adx(length=14)
    # The default pandas-ta adx method returns 3 columns: ADX_14, DMP_14, DMN_14
    if adx_df is not None and not adx_df.empty:
        df_yf['ADX_14'] = adx_df.iloc[:, 0] # First column is typically ADX
    else:
        df_yf['ADX_14'] = np.nan

    # 2. Calculate 14-period Daily ATR
    df_yf['ATR_14'] = df_yf.ta.atr(length=14)

    # 3. Calculate 200-period Simple Moving Average
    df_yf['SMA_200'] = df_yf.ta.sma(length=200)

    # Calculate Distance from Daily 200 SMA (as a percentage)
    df_yf['SMA_200_Dist_Pct'] = ((df_yf['Close'] - df_yf['SMA_200']) / df_yf['SMA_200']) * 100

    # 4. Calculate Daily Return (Close vs. Previous Close as a percentage)
    df_yf['Daily_Return_Pct'] = df_yf['Close'].pct_change() * 100

    # Clean up NaN values resulting from indicator lookbacks
    df_yf.dropna(inplace=True)

    # Ensure the index is a flat Date column for merging later
    df_yf.reset_index(inplace=True)
    df_yf['Date'] = df_yf['Date'].dt.date

    # 5. Create Target Label: Trending (1) vs Choppy (0)
    # Criteria: Daily ADX > 25 AND absolute Daily Return > 0.5%
    df_yf['Target_Label'] = np.where(
        (df_yf['ADX_14'] > 25.0) & (df_yf['Daily_Return_Pct'].abs() > 0.5),
        1, # Trending
        0  # Choppy
    )

    # Filter out the buffer period to only return the requested date range
    start_dt = pd.to_datetime(start_date).date()
    end_dt = pd.to_datetime(end_date).date()
    df_final = df_yf[(df_yf['Date'] >= start_dt) & (df_yf['Date'] <= end_dt)].copy()

    return df_final
