"""
analyser.py — Deep Analysis & Explanation Module

For a selected ticker + strategy, produces a structured explanation covering:
  - Why this ticker now
  - Why this specific strategy
  - Key risk factors
  - Suggested strike / expiry parameters
  - Greeks overview (delta, theta, vega sensitivity)
"""

import yfinance as yf
import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime, timedelta


# ─────────────────────────────────────────────
# Black-Scholes Greeks
# ─────────────────────────────────────────────

def black_scholes_greeks(
    S: float,       # current stock price
    K: float,       # strike price
    T: float,       # time to expiry in years
    r: float,       # risk-free rate (annualised, decimal)
    sigma: float,   # implied volatility (annualised, decimal)
    option_type: str = "call"
) -> dict:
    """
    Compute Black-Scholes price and key Greeks.
    Returns: price, delta, gamma, theta (per day), vega (per 1% IV move).
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {"error": "Invalid inputs for B-S model"}

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type.lower() == "call":
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1

    gamma  = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    theta  = (
        -(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
        - r * K * np.exp(-r * T) * norm.cdf(d2 if option_type == "call" else -d2)
    ) / 365
    vega   = S * norm.pdf(d1) * np.sqrt(T) / 100   # per 1% IV move

    return {
        "price" : round(price, 4),
        "delta" : round(delta, 4),
        "gamma" : round(gamma, 6),
        "theta" : round(theta, 4),   # $ per day
        "vega"  : round(vega, 4),    # $ per 1% IV
    }


# ─────────────────────────────────────────────
# Support / Resistance (simplified)
# ─────────────────────────────────────────────

def find_key_levels(ticker: str, period: str = "6mo") -> dict:
    """
    Identify recent support and resistance levels using rolling pivots.
    Returns dict with support, resistance, and 52-week range.
    """
    t  = yf.Ticker(ticker)
    df = t.history(period=period)
    if df.empty:
        return {}

    pivot      = (df["High"] + df["Low"] + df["Close"]) / 3
    support    = float(pivot.rolling(20).min().iloc[-1])
    resistance = float(pivot.rolling(20).max().iloc[-1])
    current    = float(df["Close"].iloc[-1])

    return {
        "current_price": round(current, 2),
        "support"      : round(support, 2),
        "resistance"   : round(resistance, 2),
        "week_52_high" : round(float(df["High"].max()), 2),
        "week_52_low"  : round(float(df["Low"].min()), 2),
        "pct_from_52h" : round((current / df["High"].max() - 1) * 100, 1),
        "pct_from_52l" : round((current / df["Low"].min() - 1) * 100, 1),
    }


# ─────────────────────────────────────────────
# Strike / Expiry suggestion
# ─────────────────────────────────────────────

def suggest_parameters(
    ticker   : str,
    strategy : str,
    dte_range: tuple = (21, 45)   # days-to-expiry window
) -> dict:
    """
    Suggest strike prices and expiry dates for a given strategy.

    Strategy-specific logic (skeleton):
      covered_call / cash_secured_put : 0.20–0.30 delta (slightly OTM)
      iron_condor                     : ±1 SD wings
      spreads                         : 5–10 pt wide depending on price
      long options                    : ATM or slight OTM

    Returns suggested strike, expiry date, and rationale notes.
    """
    t    = yf.Ticker(ticker)
    info = t.info or {}
    price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
    hv    = info.get("beta", 1) * 0.20   # very rough IV proxy; replace with real IV

    target_dte  = (dte_range[0] + dte_range[1]) // 2
    expiry_date = (datetime.today() + timedelta(days=target_dte)).strftime("%Y-%m-%d")

    # Strategy-specific strike suggestions
    if strategy in ("covered_call", "cash_secured_put"):
        otm_pct = 0.05
        strike  = round(price * (1 + otm_pct if strategy == "covered_call" else 1 - otm_pct), 0)
        note    = f"~5% OTM targeting 0.25–0.30 delta for premium income."
    elif strategy == "iron_condor":
        sd_move = price * hv * np.sqrt(target_dte / 365)
        strike  = {
            "put_sell" : round(price - sd_move, 0),
            "put_buy"  : round(price - sd_move * 1.5, 0),
            "call_sell": round(price + sd_move, 0),
            "call_buy" : round(price + sd_move * 1.5, 0),
        }
        note = f"±1 SD strikes based on {target_dte}-day expected move of ${sd_move:.1f}."
    elif strategy in ("bull_call_spread", "bear_put_spread"):
        strike = {
            "long" : round(price, 0),
            "short": round(price * (1.05 if "call" in strategy else 0.95), 0),
        }
        note = "ATM long leg, 5% OTM short leg."
    else:   # long_call / long_put / others
        strike = round(price, 0)
        note   = "ATM strike for maximum delta sensitivity."

    return {
        "suggested_strike"  : strike,
        "suggested_expiry"  : expiry_date,
        "target_dte"        : target_dte,
        "current_price"     : round(price, 2),
        "rationale"         : note,
    }


# ─────────────────────────────────────────────
# Core analysis function
# ─────────────────────────────────────────────

def analyse(ticker: str, strategy: str, risk_free_rate: float = 0.05) -> dict:
    """
    Full analysis report for ticker + strategy combination.

    Returns a structured dict consumed by the frontend's Analysis tab.
    """
    t    = yf.Ticker(ticker)
    info = t.info or {}
    hist = t.history(period="6mo")

    price   = info.get("currentPrice") or info.get("regularMarketPrice", 0)
    hv_1y   = float(np.log(hist["Close"] / hist["Close"].shift(1)).dropna().std() * np.sqrt(252)) if not hist.empty else 0

    levels  = find_key_levels(ticker)
    params  = suggest_parameters(ticker, strategy)

    # Compute Greeks for the suggested strike (approximate)
    K   = params["suggested_strike"] if isinstance(params["suggested_strike"], (int, float)) else price
    T   = params["target_dte"] / 365
    opt_type = "put" if strategy in ("long_put", "bear_put_spread", "cash_secured_put") else "call"
    greeks  = black_scholes_greeks(price, K, T, risk_free_rate, hv_1y, opt_type)

    # Fundamental snapshot
    fundamental = {
        "company"        : info.get("longName"),
        "sector"         : info.get("sector"),
        "market_cap_b"   : round((info.get("marketCap") or 0) / 1e9, 1),
        "pe_ratio"       : info.get("trailingPE"),
        "forward_pe"     : info.get("forwardPE"),
        "dividend_yield" : round((info.get("dividendYield") or 0) * 100, 2),
        "beta"           : info.get("beta"),
        "revenue_growth" : info.get("revenueGrowth"),
        "earnings_date"  : str(info.get("earningsDate", "N/A")),
    }

    # Narrative explanation (template — enhance with LLM later)
    explanation = _build_explanation(ticker, strategy, fundamental, levels, params, greeks)

    return {
        "ticker"       : ticker.upper(),
        "strategy"     : strategy,
        "fundamental"  : fundamental,
        "price_levels" : levels,
        "parameters"   : params,
        "greeks"       : greeks,
        "hv_1y_pct"    : round(hv_1y * 100, 1),
        "explanation"  : explanation,
    }


def _build_explanation(ticker, strategy, fundamental, levels, params, greeks) -> list[str]:
    """
    Return a list of bullet-point explanations for why this trade makes sense.
    Each string is one reasoning bullet displayed in the UI.
    """
    bullets = []

    company = fundamental.get("company") or ticker
    price   = levels.get("current_price", "N/A")
    support = levels.get("support", "N/A")
    resist  = levels.get("resistance", "N/A")

    bullets.append(
        f"{company} is currently trading at ${price}, with near-term support at "
        f"${support} and resistance at ${resist}."
    )

    if fundamental.get("beta"):
        bullets.append(
            f"Beta of {fundamental['beta']:.2f} indicates the stock moves "
            f"{'more' if fundamental['beta'] > 1 else 'less'} than the broad market — "
            f"{'elevated' if fundamental['beta'] > 1.2 else 'moderate'} options premium expected."
        )

    bullets.append(
        f"Strategy selected: {strategy.replace('_', ' ').title()}. "
        f"{params.get('rationale', '')}"
    )

    if greeks.get("theta"):
        bullets.append(
            f"Theta (time decay): ${abs(greeks['theta']):.2f}/day "
            f"{'in our favour (net seller)' if greeks['theta'] < 0 else 'working against us (net buyer)'}."
        )

    if greeks.get("delta"):
        bullets.append(
            f"Delta of {greeks['delta']:.2f} means the position gains/loses ~${abs(greeks['delta'])*100:.0f} "
            f"for every $1 move in {ticker}."
        )

    bullets.append(
        "⚠ Key risk: always confirm no upcoming earnings events within the trade window "
        "that could cause an outsized gap move."
    )

    return bullets


if __name__ == "__main__":
    report = analyse("AAPL", "covered_call")
    for k, v in report.items():
        print(f"{k}: {v}")
