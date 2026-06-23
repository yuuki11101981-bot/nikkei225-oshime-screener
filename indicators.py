"""テクニカル指標を計算するモジュール。"""

import numpy as np
import pandas as pd


def add_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """MA5, MA25, MA75を追加する。"""
    df = df.copy()
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA25"] = df["Close"].rolling(25).mean()
    df["MA75"] = df["Close"].rolling(75).mean()
    return df


def add_bollinger_bands(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """ボリンジャーバンド（MID, +1σ, -1σ, +2σ, -2σ）を追加する。"""
    df = df.copy()
    mid = df["Close"].rolling(period).mean()
    std = df["Close"].rolling(period).std()
    df["BB_MID"] = mid
    df["BB_UPPER1"] = mid + std
    df["BB_LOWER1"] = mid - std
    df["BB_UPPER2"] = mid + 2 * std
    df["BB_LOWER2"] = mid - 2 * std
    return df


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """RSIを追加する。"""
    df = df.copy()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def add_rci(df: pd.DataFrame, period: int = 9) -> pd.DataFrame:
    """RCI（順位相関指数）を追加する。短期（9）と中期（26）を計算。"""
    df = df.copy()

    def _rci(series: pd.Series, n: int) -> pd.Series:
        result = []
        for i in range(len(series)):
            if i < n - 1:
                result.append(np.nan)
                continue
            window = series.iloc[i - n + 1: i + 1].values
            time_rank = np.arange(n, 0, -1)  # 最新=1
            price_rank = n + 1 - pd.Series(window).rank(ascending=True).values
            d = time_rank - price_rank
            rci_val = (1 - 6 * np.sum(d ** 2) / (n * (n ** 2 - 1))) * 100
            result.append(rci_val)
        return pd.Series(result, index=series.index)

    df["RCI_SHORT"] = _rci(df["Close"], period)
    df["RCI_MID"] = _rci(df["Close"], 26)
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD, シグナル, ヒストグラムを追加する。"""
    df = df.copy()
    ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=signal, adjust=False).mean()
    df["MACD_HIST"] = df["MACD"] - df["MACD_SIGNAL"]
    return df


def add_volume_ma(df: pd.DataFrame, period: int = 25) -> pd.DataFrame:
    """出来高移動平均を追加する。"""
    df = df.copy()
    df["VOL_MA"] = df["Volume"].rolling(period).mean()
    return df


def calc_fibonacci(df: pd.DataFrame, lookback: int = 60) -> dict:
    """
    直近lookback日の高値・安値からフィボナッチリトレースメントを計算する。

    Returns:
        {"high": float, "low": float, "382": float, "500": float, "618": float}
    """
    window = df["Close"].tail(lookback)
    high = window.max()
    low = window.min()
    rng = high - low
    return {
        "high": high,
        "low": low,
        "fib_382": high - rng * 0.382,
        "fib_500": high - rng * 0.500,
        "fib_618": high - rng * 0.618,
    }


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """全テクニカル指標を一括追加する。"""
    df = add_moving_averages(df)
    df = add_bollinger_bands(df)
    df = add_rsi(df)
    df = add_rci(df)
    df = add_macd(df)
    df = add_volume_ma(df)
    return df
