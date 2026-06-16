"""
demo_market_data.py — Synthetic market-data shim for the public demo.

Why this exists
----------------
PythonAnywhere's FREE tier only allows outbound web requests to a small
domain whitelist, which does NOT include Yahoo Finance. yfinance calls
would simply fail there. Rather than let every screener/analyser/backtest
route 502 in the public demo, this module monkey-patches `yfinance.Ticker`
and `yfinance.download` (only when DEMO_MODE is on) with deterministic,
clearly-synthetic data so the UI stays fully functional to play with.

This does NOT touch the real app — it's only ever activated by
app.py when DEMO_MODE=1, and only inside public-demo/.
"""

import hashlib
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# Curated baseline quotes for common tickers used in the seed data /
# screener defaults, so the demo "looks right" out of the box. Anything
# else falls back to a deterministic synthetic price derived from the
# ticker's hash, so arbitrary lookups still return *something* sane
# instead of erroring out.
_BASELINE = {
    "AAPL":  {"price": 212.50, "name": "Apple Inc.",            "sector": "Technology", "industry": "Consumer Electronics"},
    "MSFT":  {"price": 441.80, "name": "Microsoft Corp.",        "sector": "Technology", "industry": "Software"},
    "NVDA":  {"price": 131.20, "name": "NVIDIA Corp.",           "sector": "Technology", "industry": "Semiconductors"},
    "GOOGL": {"price": 178.30, "name": "Alphabet Inc.",          "sector": "Technology", "industry": "Internet Content"},
    "AMZN":  {"price": 205.40, "name": "Amazon.com Inc.",        "sector": "Consumer Cyclical", "industry": "Internet Retail"},
    "META":  {"price": 590.10, "name": "Meta Platforms Inc.",    "sector": "Technology", "industry": "Internet Content"},
    "TSLA":  {"price": 215.60, "name": "Tesla Inc.",             "sector": "Consumer Cyclical", "industry": "Auto Manufacturers"},
    "O":     {"price": 58.10,  "name": "Realty Income Corp.",    "sector": "Real Estate", "industry": "REIT"},
    "VOO":   {"price": 512.30, "name": "Vanguard S&P 500 ETF",   "sector": "ETF", "industry": "Index Fund"},
    "SPY":   {"price": 560.20, "name": "SPDR S&P 500 ETF",       "sector": "ETF", "industry": "Index Fund"},
    "PLTR":  {"price": 24.80,  "name": "Palantir Technologies",  "sector": "Technology", "industry": "Software"},
    "CRWD":  {"price": 345.00, "name": "CrowdStrike Holdings",   "sector": "Technology", "industry": "Cybersecurity"},
    "LLY":   {"price": 780.50, "name": "Eli Lilly and Co.",      "sector": "Healthcare", "industry": "Drug Manufacturers"},
    "SMCI":  {"price": 38.20,  "name": "Super Micro Computer",   "sector": "Technology", "industry": "Computer Hardware"},
    "LNG":   {"price": 230.00, "name": "Cheniere Energy Inc.",   "sector": "Energy", "industry": "Oil & Gas Midstream"},
}

DEMO_NOTICE = (
    "Demo mode: this is synthetic sample market data, not a live feed "
    "(the free hosting tier blocks outbound calls to Yahoo Finance)."
)


def _seed_for(ticker: str) -> int:
    return int(hashlib.sha256(ticker.upper().encode()).hexdigest(), 16) % (2**32)


def _baseline_price(ticker: str) -> float:
    if ticker.upper() in _BASELINE:
        return _BASELINE[ticker.upper()]["price"]
    rnd = random.Random(_seed_for(ticker))
    return round(rnd.uniform(15, 450), 2)


def _synthetic_history(ticker: str, n_days: int = 760) -> pd.DataFrame:
    """Deterministic pseudo-random-walk daily OHLCV series, ending 'today'."""
    rnd = random.Random(_seed_for(ticker))
    np_rng = np.random.RandomState(_seed_for(ticker) % (2**31))
    end = datetime.today()
    dates = pd.bdate_range(end=end, periods=n_days)
    price = _baseline_price(ticker) * rnd.uniform(0.6, 0.85)  # start lower, drift up
    closes = []
    for _ in range(len(dates)):
        drift = rnd.uniform(-0.018, 0.021)
        price = max(0.5, price * (1 + drift))
        closes.append(price)
    closes = np.array(closes)
    # Anchor the final close to the curated baseline (or hashed baseline) for consistency.
    closes = closes * (_baseline_price(ticker) / closes[-1])
    opens  = closes * (1 + np_rng.uniform(-0.006, 0.006, len(closes)))
    highs  = np.maximum(opens, closes) * (1 + np_rng.uniform(0.001, 0.012, len(closes)))
    lows   = np.minimum(opens, closes) * (1 - np_rng.uniform(0.001, 0.012, len(closes)))
    vols   = np_rng.randint(1_000_000, 40_000_000, len(closes))
    df = pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows, "Close": closes,
        "Adj Close": closes, "Volume": vols,
    }, index=dates)
    df.index.name = "Date"
    return df


def _slice_period(df: pd.DataFrame, period=None, start=None, end=None) -> pd.DataFrame:
    if start or end:
        s = pd.to_datetime(start) if start else df.index.min()
        e = pd.to_datetime(end) if end else df.index.max()
        return df.loc[(df.index >= s) & (df.index <= e)]
    days_map = {
        "1d": 1, "5d": 5, "1mo": 22, "3mo": 66, "6mo": 132,
        "1y": 252, "2y": 504, "5y": 1260, "10y": 2520, "max": len(df),
    }
    n = days_map.get(period, 252)
    return df.tail(n)


class _DemoFastInfo:
    def __init__(self, ticker: str, df: pd.DataFrame):
        last = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2]) if len(df) > 1 else last
        self.last_price = last
        self.lastPrice = last
        self.previous_close = prev
        self.previousClose = prev
        self.day_high = float(df["High"].iloc[-1])
        self.day_low = float(df["Low"].iloc[-1])
        self.year_high = float(df["High"].tail(252).max())
        self.year_low = float(df["Low"].tail(252).min())
        self.market_cap = last * 1_000_000_000
        self.currency = "USD"

    def __getitem__(self, key):
        return getattr(self, key, None)


class DemoTicker:
    """Drop-in stand-in for yfinance.Ticker, backed by synthetic data."""

    def __init__(self, ticker: str):
        self.ticker = ticker
        meta = _BASELINE.get(ticker.upper(), {})
        self._df = _synthetic_history(ticker)
        last = float(self._df["Close"].iloc[-1])
        prev = float(self._df["Close"].iloc[-2]) if len(self._df) > 1 else last
        self.info = {
            "symbol": ticker.upper(),
            "shortName": meta.get("name", f"{ticker.upper()} (Demo)"),
            "longName": meta.get("name", f"{ticker.upper()} (Demo)"),
            "sector": meta.get("sector", "Diversified"),
            "industry": meta.get("industry", "Diversified"),
            "currentPrice": last,
            "regularMarketPrice": last,
            "previousClose": prev,
            "marketCap": last * 1_000_000_000,
            "trailingPE": round(random.Random(_seed_for(ticker)).uniform(12, 38), 1),
            "forwardPE": round(random.Random(_seed_for(ticker) + 1).uniform(11, 34), 1),
            "dividendYield": round(random.Random(_seed_for(ticker) + 2).uniform(0, 0.035), 4),
            "beta": round(random.Random(_seed_for(ticker) + 3).uniform(0.6, 1.8), 2),
            "fiftyTwoWeekHigh": float(self._df["High"].tail(252).max()),
            "fiftyTwoWeekLow": float(self._df["Low"].tail(252).min()),
            "averageVolume": int(self._df["Volume"].tail(30).mean()),
            "currency": "USD",
            "quoteType": "EQUITY",
            "longBusinessSummary": (
                f"{meta.get('name', ticker.upper())} — demo profile. "
                "This description and all figures are synthetic sample data "
                "generated for the public TradingOS demo."
            ),
        }

    @property
    def fast_info(self):
        return _DemoFastInfo(self.ticker, self._df)

    @property
    def calendar(self):
        nxt = datetime.today() + timedelta(days=random.Random(_seed_for(self.ticker)).randint(10, 80))
        return {"Earnings Date": [nxt.date()]}

    def history(self, period=None, start=None, end=None, **kwargs):
        return _slice_period(self._df, period, start, end).copy()

    def get_calendar(self, *a, **kw):
        return self.calendar


def demo_download(tickers, period=None, start=None, end=None,
                   group_by="column", auto_adjust=True, progress=False,
                   threads=True, **kwargs):
    """Drop-in stand-in for yfinance.download."""
    single = isinstance(tickers, str)
    ticker_list = [tickers] if single else list(tickers)

    if single or len(ticker_list) == 1:
        df = _slice_period(_synthetic_history(ticker_list[0]), period, start, end)
        return df.copy()

    frames = {t: _slice_period(_synthetic_history(t), period, start, end) for t in ticker_list}
    if group_by == "ticker":
        return pd.concat(frames, axis=1)
    # group_by == "column" (yfinance default): MultiIndex (Field, Ticker)
    fields = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    cols = pd.MultiIndex.from_product([fields, ticker_list])
    out = pd.DataFrame(index=next(iter(frames.values())).index, columns=cols)
    for t, df in frames.items():
        for f in fields:
            out[(f, t)] = df[f]
    return out


def patch_yfinance():
    """Monkey-patch the yfinance module in place. Call once at app startup
    when DEMO_MODE is on, before any yf.Ticker/yf.download calls happen."""
    import yfinance
    yfinance.Ticker = DemoTicker
    yfinance.download = demo_download
    print("[demo_market_data] yfinance patched with synthetic data (DEMO_MODE).")
