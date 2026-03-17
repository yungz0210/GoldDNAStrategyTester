import pandas as pd
import numpy as np
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit

# --- HELPER FUNCTIONS: Native Indicators (To Avoid pandas-ta / Python 3.14 Crash) ---

def calc_atr(df, period=14):
    high = df['High']
    low = df['Low']
    prev_close = df['Close'].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's Smoothing for ATR
    atr = np.zeros(len(df))
    atr[period] = tr[1:period+1].mean()
    for i in range(period + 1, len(df)):
        atr[i] = (atr[i-1] * (period - 1) + tr.iloc[i]) / period

    atr[:period] = np.nan
    return pd.Series(atr, index=df.index)

def calc_adx(df, period=14):
    high = df['High']
    low = df['Low']
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = high - low
    tr2 = (high - df['Close'].shift(1)).abs()
    tr3 = (low - df['Close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's Smoothing
    def wilder_smooth(data, n):
        res = np.zeros(len(data))
        res[n] = data[1:n+1].sum()
        for i in range(n + 1, len(data)):
            res[i] = res[i-1] - (res[i-1] / n) + data.iloc[i]
        res[:n] = np.nan
        return pd.Series(res, index=data.index)

    tr_smooth = wilder_smooth(tr, period)
    plus_di = 100 * (wilder_smooth(pd.Series(plus_dm), period) / tr_smooth)
    minus_di = 100 * (wilder_smooth(pd.Series(minus_dm), period) / tr_smooth)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)

    # ADX is the Wilder's Moving Average of DX
    # Wait until DX has enough non-nan values. dx starts having values at index period.
    # We need 'period' values of DX to take the first mean.
    adx = np.zeros(len(df))
    dx = dx.fillna(0.0) # To avoid nan propagating in simple loops

    adx_start = period * 2 - 1
    # Check if we have enough data
    if len(df) > adx_start:
        # Initial ADX is the simple moving average of DX
        adx[adx_start] = dx.iloc[period:adx_start+1].mean()
        for i in range(adx_start + 1, len(df)):
            adx[i] = ((adx[i-1] * (period - 1)) + dx.iloc[i]) / period

    adx = pd.Series(adx, index=df.index)
    adx.iloc[:adx_start+1] = np.nan
    return adx

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
    # Add a buffer to start_date to ensure we have enough trading days for the 200 SMA and ADX logic
    # Since there are ~252 trading days in a year, a 300 calendar day buffer might barely produce 200 bars,
    # and ADX/Smoothing logic drops more at the start. So we use a 400 day buffer.
    buffer_start = pd.to_datetime(start_date) - pd.Timedelta(days=400)

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

    # 1. Calculate 14-period Daily ADX (Native)
    df_yf['ADX_14'] = calc_adx(df_yf, period=14)

    # 2. Calculate 14-period Daily ATR (Native)
    df_yf['ATR_14'] = calc_atr(df_yf, period=14)

    # 3. Calculate 200-period Simple Moving Average (Native)
    df_yf['SMA_200'] = df_yf['Close'].rolling(window=200).mean()

    # Calculate Distance from Daily 200 SMA (as a percentage)
    df_yf['SMA_200_Dist_Pct'] = ((df_yf['Close'] - df_yf['SMA_200']) / df_yf['SMA_200']) * 100

    # 4. Calculate Daily Return (Close vs. Previous Close as a percentage)
    df_yf['Daily_Return_Pct'] = df_yf['Close'].pct_change() * 100


    # Clean up NaN values resulting from indicator lookbacks
    df_yf = df_yf.dropna(subset=['ADX_14', 'ATR_14', 'SMA_200', 'Daily_Return_Pct'])

    # Ensure the index is a flat Date column for merging later
    df_yf = df_yf.reset_index()

    # yfinance returns 'Date' as a DatetimeIndex usually
    # If the column is still datetime64, convert it to date()
    try:
        df_yf['Date'] = pd.to_datetime(df_yf['Date']).dt.date
    except Exception as e:
        pass # If it's already a Date object, leave it

    # 5. Create Target Label: Trending (1) vs Choppy (0)
    # Criteria: Daily ADX > 25 AND absolute Daily Return > 0.5%
    df_yf['Target_Label'] = np.where(
        (df_yf['ADX_14'] > 25.0) & (df_yf['Daily_Return_Pct'].abs() > 0.5),
        1, # Trending
        0  # Choppy
    )

    # CRITICAL: Prevent Look-Ahead Bias
    # We must predict TODAY's label using YESTERDAY'S features.
    # Therefore, shift the features forward by 1 day.
    feature_cols = ['ADX_14', 'ATR_14', 'SMA_200_Dist_Pct', 'Daily_Return_Pct']
    for col in feature_cols:
        df_yf[f'{col}_Shift1'] = df_yf[col].shift(1)

    df_yf = df_yf.dropna(subset=[f'{col}_Shift1' for col in feature_cols])

    # Filter out the buffer period to only return the requested date range
    start_dt = pd.to_datetime(start_date).date()
    end_dt = pd.to_datetime(end_date).date()

    df_final = df_yf[(df_yf['Date'] >= start_dt) & (df_yf['Date'] <= end_dt)].copy()

    return df_final

# --- PHASE 3: The Regime Classifier Model ---

def train_and_predict_regimes(df_macro: pd.DataFrame) -> pd.DataFrame:
    """
    Trains a Random Forest Classifier using TimeSeriesSplit (Walk-Forward).
    Predicts the Target_Label for the dataset.
    """
    if df_macro.empty:
        return df_macro

    features = ['ADX_14_Shift1', 'ATR_14_Shift1', 'SMA_200_Dist_Pct_Shift1', 'Daily_Return_Pct_Shift1']
    X = df_macro[features].values
    y = df_macro['Target_Label'].values

    # Initialize the model and cross-validator
    model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)

    # Safely handle very small datasets by adjusting the number of splits
    n_samples = len(y)
    n_splits = 5 if n_samples >= 6 else max(1, n_samples - 1)

    if n_splits < 1:
        # If we have 1 or 0 samples, we can't do TimeSeriesSplit at all
        df_macro['ML_Prediction'] = 0
        return df_macro

    tscv = TimeSeriesSplit(n_splits=n_splits)

    predictions = np.zeros(len(y))
    predictions[:] = np.nan # Use NaN to mark unpredicted rows (like the initial training buffer)

    # Perform walk-forward training/prediction
    for train_index, test_index in tscv.split(X):
        X_train, X_test = X[train_index], X[test_index]
        y_train, y_test = y[train_index], y[test_index]

        # Only train if we have both classes in the training set
        if len(np.unique(y_train)) > 1:
            model.fit(X_train, y_train)
            pred = model.predict(X_test)
            predictions[test_index] = pred
        else:
            # If a fold lacks variation, fallback to predicting 0 (Choppy/Filter On)
            predictions[test_index] = 0

    df_macro['ML_Prediction'] = predictions

    # For the earliest data points that couldn't be predicted (Fold 0 training set),
    # we conservatively default to 0 (Choppy) to simulate the model being "offline" initially.
    df_macro['ML_Prediction'] = df_macro['ML_Prediction'].fillna(0)

    return df_macro


# --- PHASE 4: Data Fusion & Filter Logic ---

def apply_ml_filter(df_mt5: pd.DataFrame, df_macro_predictions: pd.DataFrame) -> dict:
    """
    Merges MT5 trades with ML predictions.
    Generates a filtered Equity Curve where trades on 'Choppy' (Prediction == 0) days are skipped.
    """
    if df_mt5.empty or df_macro_predictions.empty:
        return {}

    # Merge the DataFrames based on the localized NY Date
    # We use a left join to keep all MT5 trades. If a day has no macro data (e.g. weekend),
    # the prediction will be NaN.
    df_merged = df_mt5.merge(
        df_macro_predictions[['Date', 'ML_Prediction']],
        left_on='TradeDate_NY',
        right_on='Date',
        how='left'
    )

    # For weekends/holidays where yfinance has no data, carry forward the Friday prediction (ffill)
    # We sort by EntryTime just in case.
    df_merged = df_merged.sort_values('EntryTime')
    df_merged['ML_Prediction'] = df_merged['ML_Prediction'].ffill()

    # Default to 0 (Filter out) if still NaN
    df_merged['ML_Prediction'] = df_merged['ML_Prediction'].fillna(0)

    # Create the Filtered Dataset
    # We KEEP trades where ML_Prediction == 1 (Trending)
    df_filtered = df_merged[df_merged['ML_Prediction'] == 1].copy()

    # Calculate Comparative Metrics
    baseline_metrics = calculate_baseline_metrics(df_mt5)
    filtered_metrics = calculate_baseline_metrics(df_filtered)

    # Generate Equity Curves
    eq_original = [0.0] + df_mt5['NetPnL'].cumsum().tolist()
    eq_filtered = [0.0] + df_filtered['NetPnL'].cumsum().tolist()

    return {
        'Baseline_Metrics': baseline_metrics,
        'Filtered_Metrics': filtered_metrics,
        'Equity_Original': eq_original,
        'Equity_Filtered': eq_filtered,
        'Filtered_DataFrame': df_filtered
    }
