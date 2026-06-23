"""yfinanceを使って株価データを取得するモジュール。"""

import time
import yfinance as yf
import pandas as pd
from typing import Optional


def fetch_ohlcv(ticker: str, period: str = "6mo", interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    指定ティッカーのOHLCVデータを取得する。

    Returns:
        DataFrame (columns: Open, High, Low, Close, Volume) or None on failure.
    """
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period=period, interval=interval, auto_adjust=True)
        if df is None or df.empty or len(df) < 80:
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index)
        df = df.dropna()
        return df
    except Exception:
        return None


def fetch_multiple(tickers: list[str], period: str = "6mo", delay: float = 0.2) -> dict[str, pd.DataFrame]:
    """
    複数銘柄のOHLCVデータを取得する。

    Args:
        tickers: ティッカーリスト
        period: 取得期間
        delay: 各リクエスト間の待機秒数（レート制限対策）

    Returns:
        {ticker: DataFrame} の辞書（取得失敗した銘柄は含まない）
    """
    results = {}
    for ticker in tickers:
        df = fetch_ohlcv(ticker, period=period)
        if df is not None:
            results[ticker] = df
        time.sleep(delay)
    return results
