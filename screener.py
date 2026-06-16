"""
screener.py — Stock Screening Module
Fetches data via yfinance and filters tickers against user-defined criteria.

Criteria supported (skeleton — expand each as needed):
  Fundamental : market_cap, pe_ratio, dividend_yield, revenue_growth
  Technical   : rsi, ma_crossover, avg_volume, price_vs_52w
  Options-specific : iv_rank, options_volume, put_call_ratio
"""

import yfinance as yf
import pandas as pd
from typing import Any

# ── Default screening criteria ────────────────────────────────────────────────
DEFAULT_CRITERIA = {
    # Fundamental
    "min_market_cap"    : 1e9,          # $1B minimum
    "max_pe_ratio"      : 50,
    "min_avg_volume"    : 1_000_000,    # shares/day

    # Technical
    "rsi_min"           : 30,
    "rsi_max"           : 70,

    # Options
    "min_options_volume": 500,          # contracts/day
}


# ─────────────────────────────────────────────
# Data fetching helpers
# ─────────────────────────────────────────────

def fetch_ticker_info(ticker: str) -> dict[str, Any]:
    """
    Pull summary info for a single ticker from yfinance.
    Returns a flat dict of relevant fields; missing fields default to None.
    """
    t = yf.Ticker(ticker)
    info = t.info or {}

    return {
        "ticker"          : ticker.upper(),
        "company"         : info.get("longName"),
        "sector"          : info.get("sector"),
        "industry"        : info.get("industry"),
        "market_cap"      : info.get("marketCap"),
        "pe_ratio"        : info.get("trailingPE"),
        "forward_pe"      : info.get("forwardPE"),
        "dividend_yield"  : info.get("dividendYield"),
        "avg_volume"      : info.get("averageVolume"),
        "price"           : info.get("currentPrice") or info.get("regularMarketPrice"),
        "week_52_high"    : info.get("fiftyTwoWeekHigh"),
        "week_52_low"     : info.get("fiftyTwoWeekLow"),
        "beta"            : info.get("beta"),
        "revenue_growth"  : info.get("revenueGrowth"),
    }


def fetch_price_history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Return OHLCV DataFrame for the given period."""
    t = yf.Ticker(ticker)
    df = t.history(period=period)
    df.index = pd.to_datetime(df.index)
    return df


def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """Compute the most-recent RSI value for a price series."""
    delta = prices.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


# ─────────────────────────────────────────────
# Core screening function
# ─────────────────────────────────────────────

def screen_tickers(tickers: list[str], criteria: dict = None) -> list[dict]:
    """
    Screen a list of tickers against the given criteria dict.
    Returns only those that pass all filters, enriched with computed fields.

    Parameters
    ----------
    tickers  : list of ticker symbols, e.g. ["AAPL", "MSFT", "TSLA"]
    criteria : dict overriding DEFAULT_CRITERIA; partial overrides are merged.

    Returns
    -------
    List of dicts, each representing a passing ticker with all fetched fields.
    """
    cfg = {**DEFAULT_CRITERIA, **(criteria or {})}
    results = []

    for ticker in tickers:
        try:
            info = fetch_ticker_info(ticker)

            # ── Fundamental filters ────────────────
            if cfg.get("min_market_cap") and (info["market_cap"] or 0) < cfg["min_market_cap"]:
                continue
            if cfg.get("max_pe_ratio") and info["pe_ratio"] and info["pe_ratio"] > cfg["max_pe_ratio"]:
                continue
            if cfg.get("min_avg_volume") and (info["avg_volume"] or 0) < cfg["min_avg_volume"]:
                continue

            # ── Technical filters ──────────────────
            hist = fetch_price_history(ticker, "3mo")
            if not hist.empty:
                rsi = compute_rsi(hist["Close"])
                info["rsi"] = rsi
                if rsi < cfg.get("rsi_min", 0) or rsi > cfg.get("rsi_max", 100):
                    continue
            else:
                info["rsi"] = None

            # ── Options-specific filters ───────────
            # TODO: integrate options volume / IV rank when data source is confirmed
            info["options_volume"] = None   # placeholder
            info["iv_rank"]        = None   # placeholder

            info["passed"] = True
            results.append(info)

        except Exception as e:
            results.append({"ticker": ticker, "passed": False, "error": str(e)})

    return results


# ─────────────────────────────────────────────
# Sector / universe helpers
# ─────────────────────────────────────────────

# Starter universes — expand as needed
UNIVERSES = {
    "sp500_tech": [
        "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ORCL", "AMD", "QCOM", "TXN"
    ],
    "sp500_finance": [
        "JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW", "AXP", "COF", "USB"
    ],
    "sp500_healthcare": [
        "UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY", "AMGN"
    ],
    "sp500_consumer": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "TGT", "COST", "LOW", "TJX"
    ],
    "etfs": [
        "SPY", "QQQ", "IWM", "XLE", "XLF", "XLK", "GLD", "TLT", "VXX", "ARKK"
    ],
}


def get_universe(name: str) -> list[str]:
    """Return a predefined ticker list by universe name."""
    return UNIVERSES.get(name, [])


if __name__ == "__main__":
    # Quick smoke-test
    hits = screen_tickers(["AAPL", "MSFT"], criteria={"min_market_cap": 5e11})
    for h in hits:
        print(h)
