"""
recommender.py — Options Strategy Recommendation Module

Given a screened ticker with its market data, this module selects the most
appropriate options strategy based on:
  - Market trend / bias  (bullish / bearish / neutral)
  - Implied Volatility   (high IV → sell premium; low IV → buy options)
  - Time horizon
  - Risk tolerance

Strategies covered (skeleton):
  Bullish  : Covered Call, Cash-Secured Put, Bull Call Spread, Long Call
  Bearish  : Protective Put, Bear Put Spread, Long Put
  Neutral  : Iron Condor, Short Straddle, Short Strangle, Calendar Spread
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Literal

# ─────────────────────────────────────────────
# Strategy catalogue
# ─────────────────────────────────────────────

STRATEGIES = {
    "covered_call": {
        "name"        : "Covered Call",
        "bias"        : "neutral_to_bullish",
        "iv_condition": "high",
        "risk"        : "low",
        "description" : "Sell OTM call against existing long stock position to generate income.",
        "max_profit"  : "Premium received + (strike - stock price) × 100",
        "max_loss"    : "Stock price - premium received (downside risk)",
        "backtest_supported": True,
    },
    "cash_secured_put": {
        "name"        : "Cash-Secured Put",
        "bias"        : "neutral_to_bullish",
        "iv_condition": "high",
        "risk"        : "low",
        "description" : "Sell OTM put with enough cash set aside to buy 100 shares.",
        "max_profit"  : "Premium received",
        "max_loss"    : "(Strike - premium) × 100 (stock goes to zero)",
        "backtest_supported": True,
    },
    "bull_call_spread": {
        "name"        : "Bull Call Spread",
        "bias"        : "bullish",
        "iv_condition": "low",
        "risk"        : "medium",
        "description" : "Buy lower-strike call, sell higher-strike call. Defined risk bullish bet (debit).",
        "max_profit"  : "(Width of strikes - net debit) × 100",
        "max_loss"    : "Net debit × 100",
        "backtest_supported": True,
    },
    "bull_put_spread": {
        "name"        : "Bull Put Spread",
        "bias"        : "bullish",
        "iv_condition": "high",
        "risk"        : "low",
        "description" : "Sell higher-strike put, buy lower-strike put. Defined risk bullish bet (credit).",
        "max_profit"  : "Net credit × 100",
        "max_loss"    : "(Width of strikes - net credit) × 100",
        "backtest_supported": True,
    },
    "bear_call_spread": {
        "name"        : "Bear Call Spread",
        "bias"        : "bearish",
        "iv_condition": "high",
        "risk"        : "low",
        "description" : "Sell lower-strike call, buy higher-strike call. Defined risk bearish bet (credit).",
        "max_profit"  : "Net credit × 100",
        "max_loss"    : "(Width of strikes - net credit) × 100",
        "backtest_supported": True,
    },
    "iron_condor": {
        "name"        : "Iron Condor",
        "bias"        : "neutral",
        "iv_condition": "high",
        "risk"        : "medium",
        "description" : "Sell OTM put spread + OTM call spread. Profit if stock stays in range.",
        "max_profit"  : "Net credit received × 100",
        "max_loss"    : "(Width of strikes - net credit) × 100",
        "backtest_supported": True,
    },
    "iron_butterfly": {
        "name"        : "Iron Butterfly",
        "bias"        : "neutral",
        "iv_condition": "very_high",
        "risk"        : "medium",
        "description" : "Sell ATM call + ATM put, buy OTM wings for protection. Tighter range bet than an iron condor.",
        "max_profit"  : "Net credit received × 100",
        "max_loss"    : "(Width of wings - net credit) × 100",
        "backtest_supported": True,
    },
    "long_call": {
        "name"        : "Long Call",
        "bias"        : "bullish",
        "iv_condition": "low",
        "risk"        : "medium",
        "description" : "Buy a call option. Unlimited upside, premium is max loss.",
        "max_profit"  : "Unlimited",
        "max_loss"    : "Premium paid × 100",
        "backtest_supported": True,
    },
    "long_put": {
        "name"        : "Long Put",
        "bias"        : "bearish",
        "iv_condition": "low",
        "risk"        : "medium",
        "description" : "Buy a put option. Profits as stock falls below strike.",
        "max_profit"  : "(Strike - 0) × 100 (theoretical)",
        "max_loss"    : "Premium paid × 100",
        "backtest_supported": True,
    },
    "protective_put": {
        "name"        : "Protective Put",
        "bias"        : "neutral_to_bullish",
        "iv_condition": "low",
        "risk"        : "low",
        "description" : "Hold long stock and buy a put as downside insurance. Caps loss, keeps upside.",
        "max_profit"  : "Unlimited (stock upside) - premium paid",
        "max_loss"    : "(Stock price - strike) + premium paid",
        "backtest_supported": True,
    },
    "bear_put_spread": {
        "name"        : "Bear Put Spread",
        "bias"        : "bearish",
        "iv_condition": "low",
        "risk"        : "medium",
        "description" : "Buy higher-strike put, sell lower-strike put. Defined risk bearish bet (debit).",
        "max_profit"  : "(Width of strikes - net debit) × 100",
        "max_loss"    : "Net debit × 100",
        "backtest_supported": True,
    },
    "short_straddle": {
        "name"        : "Short Straddle",
        "bias"        : "neutral",
        "iv_condition": "very_high",
        "risk"        : "high",
        "description" : "Sell ATM call and ATM put. Profit from IV crush and range-bound price.",
        "max_profit"  : "Total premium received × 100",
        "max_loss"    : "Unlimited (call side) / Strike - premium (put side)",
        "backtest_supported": True,
    },
    "short_strangle": {
        "name"        : "Short Strangle",
        "bias"        : "neutral",
        "iv_condition": "very_high",
        "risk"        : "high",
        "description" : "Sell OTM call and OTM put. Wider breakeven range than a short straddle, lower premium.",
        "max_profit"  : "Total premium received × 100",
        "max_loss"    : "Unlimited (call side) / Strike - premium (put side)",
        "backtest_supported": True,
    },
    "collar": {
        "name"        : "Collar",
        "bias"        : "neutral_to_bullish",
        "iv_condition": "any",
        "risk"        : "low",
        "description" : "Hold long stock, buy protective put, sell covered call to offset the put's cost.",
        "max_profit"  : "(Call strike - stock price) × 100 + net credit/debit",
        "max_loss"    : "(Stock price - put strike) × 100 + net credit/debit",
        "backtest_supported": True,
    },
    "calendar_spread": {
        "name"        : "Calendar Spread",
        "bias"        : "neutral",
        "iv_condition": "any",
        "risk"        : "medium",
        "description" : "Sell near-term option, buy far-term option at same strike. Profit from time decay differential.",
        "max_profit"  : "When near-term expires worthless at the strike",
        "max_loss"    : "Net debit paid",
        "backtest_supported": False,
        "backtest_note": "Needs two option expiries priced simultaneously — the single-cycle BS simulator here can't model that yet.",
    },
    "diagonal_spread": {
        "name"        : "Diagonal Spread",
        "bias"        : "neutral_to_bullish",
        "iv_condition": "any",
        "risk"        : "medium",
        "description" : "Like a calendar spread but with different strikes (e.g. 'poor man's covered call' — long far-dated ITM call, short near-dated OTM call).",
        "max_profit"  : "Varies — capped by short leg, extended by long leg's later expiry",
        "max_loss"    : "Net debit paid (worst case)",
        "backtest_supported": False,
        "backtest_note": "Needs two option expiries priced simultaneously — the single-cycle BS simulator here can't model that yet.",
    },
}


# ─────────────────────────────────────────────
# Market analysis helpers
# ─────────────────────────────────────────────

def detect_trend(ticker: str, lookback: int = 50) -> Literal["bullish", "bearish", "neutral"]:
    """
    Simple 20/50 SMA crossover to classify recent price trend.
    TODO: enhance with momentum, sector analysis, earnings proximity.
    """
    t   = yf.Ticker(ticker)
    df  = t.history(period="6mo")["Close"]
    if len(df) < lookback:
        return "neutral"

    sma20 = df.rolling(20).mean().iloc[-1]
    sma50 = df.rolling(50).mean().iloc[-1]
    price = df.iloc[-1]

    if price > sma20 > sma50:
        return "bullish"
    elif price < sma20 < sma50:
        return "bearish"
    return "neutral"


def estimate_iv_rank(ticker: str) -> dict:
    """
    Approximate IV rank using historical volatility as a proxy.
    Real IV rank requires options chain data — this is the skeleton placeholder.

    Returns:
      { "iv_rank": float, "hv_30": float, "condition": str }
    """
    t   = yf.Ticker(ticker)
    df  = t.history(period="1y")["Close"]
    if len(df) < 30:
        return {"iv_rank": None, "hv_30": None, "condition": "unknown"}

    log_ret = np.log(df / df.shift(1)).dropna()
    hv_30   = float(log_ret.rolling(30).std().iloc[-1] * np.sqrt(252) * 100)

    # Rough HV-based percentile over 1 year as IV-rank proxy
    rolling_hv = log_ret.rolling(30).std().dropna() * np.sqrt(252) * 100
    iv_rank    = float((rolling_hv < hv_30).mean() * 100)

    if iv_rank >= 60:
        condition = "high"
    elif iv_rank >= 40:
        condition = "medium"
    else:
        condition = "low"

    return {"iv_rank": round(iv_rank, 1), "hv_30": round(hv_30, 1), "condition": condition}


# ─────────────────────────────────────────────
# Core recommendation function
# ─────────────────────────────────────────────

def recommend(ticker: str, risk_tolerance: str = "medium") -> dict:
    """
    Generate ranked strategy recommendations for a ticker.

    Parameters
    ----------
    ticker         : e.g. "AAPL"
    risk_tolerance : "low" | "medium" | "high"

    Returns
    -------
    {
      "ticker"      : str,
      "trend"       : str,
      "iv_data"     : dict,
      "recommended" : [list of strategy dicts, ranked by fit score],
      "top_pick"    : str   (strategy key of #1 recommendation)
    }
    """
    trend   = detect_trend(ticker)
    iv_data = estimate_iv_rank(ticker)
    iv_cond = iv_data["condition"]

    risk_map  = {"low": 1, "medium": 2, "high": 3, "very_high": 4}
    user_risk = risk_map.get(risk_tolerance, 2)

    scored = []
    for key, strat in STRATEGIES.items():
        score = 0
        reasons = []

        # ── Trend alignment (max 3 pts) ──────────────────────────────
        if strat["bias"] == trend:
            trend_pts = 3
            reasons.append(f"Strategy bias ({strat['bias']}) matches the detected {trend} trend.")
        elif strat["bias"] == "neutral":
            trend_pts = 1
            reasons.append(f"Strategy is trend-neutral; current trend is {trend}, so it's a partial fit.")
        elif "neutral" in strat["bias"] and trend != "bearish":
            trend_pts = 2
            reasons.append(f"Strategy bias ({strat['bias']}) loosely fits the {trend} trend.")
        else:
            trend_pts = 0
            reasons.append(f"Strategy bias ({strat['bias']}) does not align with the detected {trend} trend.")
        score += trend_pts

        # ── IV alignment (max 3 pts) ──────────────────────────────────
        if strat["iv_condition"] == iv_cond:
            iv_pts = 3
            reasons.append(f"Strategy wants {strat['iv_condition']} IV, and current IV condition is {iv_cond} — good fit.")
        elif strat["iv_condition"] == "any":
            iv_pts = 1
            reasons.append("Strategy is not IV-sensitive, so current IV condition is a non-factor.")
        else:
            iv_pts = 0
            reasons.append(f"Strategy wants {strat['iv_condition']} IV, but current IV condition is {iv_cond} — mismatch.")
        score += iv_pts

        # ── Risk filter (max 1 pt) ──────────────────────────────────
        strat_risk = risk_map.get(strat["risk"], 2)
        if strat_risk <= user_risk:
            risk_pts = 1
            reasons.append(f"Strategy risk ({strat['risk']}) fits within your {risk_tolerance} risk tolerance.")
        else:
            risk_pts = 0
            reasons.append(f"Strategy risk ({strat['risk']}) exceeds your {risk_tolerance} risk tolerance.")
        score += risk_pts

        scored.append({
            **strat,
            "key": key,
            "score": score,
            "max_score": 7,
            "score_breakdown": {
                "trend_pts": trend_pts, "iv_pts": iv_pts, "risk_pts": risk_pts,
            },
            "reasoning": reasons,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    return {
        "ticker"     : ticker.upper(),
        "trend"      : trend,
        "iv_data"    : iv_data,
        "recommended": scored,        # full ranked list — let the user browse all strategies
        "top_pick"   : scored[0]["key"] if scored else None,
    }


if __name__ == "__main__":
    r = recommend("AAPL")
    print(r["top_pick"], r["trend"], r["iv_data"])
