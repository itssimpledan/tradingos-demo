"""
backtester.py — Options Strategy Backtest Engine

Simulates historical options strategy performance using:
  - Historical daily price data (yfinance)
  - Approximate premium estimation via historical volatility
  - Rolling entry/exit on each trade cycle

Strategies implemented:
  - covered_call      : sell OTM call each cycle, hold stock
  - cash_secured_put  : sell OTM put each cycle, cash secured
  - iron_condor       : sell strangle with defined wings
  - long_call / long_put : buy ATM/OTM option each cycle

NOTE: This is a simplified simulation. Real options backtest requires
      actual historical options chain data (e.g., CBOE, OptionsDX, Orats).
      IV is approximated from realised historical volatility.
"""

import yfinance as yf
import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime


# ─────────────────────────────────────────────
# Black-Scholes price estimator (shared util)
# ─────────────────────────────────────────────

def bs_price(S, K, T, r, sigma, option_type="call") -> float:
    if T <= 0 or sigma <= 0:
        return max(0, S - K) if option_type == "call" else max(0, K - S)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


# ─────────────────────────────────────────────
# Core backtest runner
# ─────────────────────────────────────────────

def run_backtest(
    ticker       : str,
    strategy     : str,
    period       : str  = "2y",     # yfinance period string
    dte          : int  = 30,       # target days-to-expiry per trade
    otm_pct      : float = 0.05,   # how far OTM, as % of spot (5% = 5 pts OTM on a $100 stock)
    risk_free    : float = 0.05,   # annualised risk-free rate
    contracts    : int  = 1,
    width_mode   : str  = "pct",    # "pct" (% of spot, scales with price) or "fixed" ($ width, constant)
    strike_width : float = 5.0,     # used when width_mode="fixed": $ OTM distance AND $ gap between spread legs
) -> dict:
    """
    Simulate rolling options trades over the historical window.

    Returns
    -------
    {
      "ticker"        : str,
      "strategy"      : str,
      "period"        : str,
      "trades"        : list[dict],   all simulated trade results
      "summary"       : dict,         aggregate stats
      "equity_curve"  : list[float],  cumulative P&L over time
    }
    """
    t   = yf.Ticker(ticker)
    df  = t.history(period=period).reset_index()
    if df.empty or len(df) < dte * 2:
        return {"error": f"Insufficient data for {ticker} over {period}"}

    df["Date"]    = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    df            = df.set_index("Date").sort_index()
    closes        = df["Close"]

    trades        = []
    exit_indices  = []
    multiplier    = 100 * contracts

    i = 0
    while i < len(closes) - dte:
        entry_date = closes.index[i]
        exit_idx   = min(i + dte, len(closes) - 1)
        exit_date  = closes.index[exit_idx]

        S_entry = float(closes.iloc[i])
        S_exit  = float(closes.iloc[exit_idx])

        # Compute HV over prior 30 days as IV proxy
        window = closes.iloc[max(0, i-30):i]
        if len(window) < 5:
            i += dte
            continue
        log_ret = np.log(window / window.shift(1)).dropna()
        hv      = float(log_ret.std() * np.sqrt(252))

        T       = dte / 365.0
        result  = _simulate_trade(strategy, S_entry, S_exit, hv, T, risk_free, otm_pct, multiplier,
                                   width_mode, strike_width)

        result.update({
            "entry_date": str(entry_date.date()),
            "exit_date" : str(exit_date.date()),
            "S_entry"   : round(S_entry, 2),
            "S_exit"    : round(S_exit, 2),
            "hv_used"   : round(hv * 100, 1),
        })
        trades.append(result)
        exit_indices.append(exit_idx)
        i += dte   # roll to next cycle

    if not trades:
        return {"error": "No trades generated"}

    pnls        = [t["pnl"] for t in trades]
    equity      = list(np.cumsum(pnls))
    win_trades  = [p for p in pnls if p > 0]
    loss_trades = [p for p in pnls if p <= 0]

    summary = {
        "total_trades"   : len(trades),
        "winning_trades" : len(win_trades),
        "losing_trades"  : len(loss_trades),
        "win_rate_pct"   : round(len(win_trades) / len(trades) * 100, 1),
        "total_pnl"      : round(sum(pnls), 2),
        "avg_pnl"        : round(np.mean(pnls), 2),
        "avg_win"        : round(np.mean(win_trades), 2) if win_trades else 0,
        "avg_loss"       : round(np.mean(loss_trades), 2) if loss_trades else 0,
        "max_win"        : round(max(pnls), 2),
        "max_loss"       : round(min(pnls), 2),
        "profit_factor"  : round(sum(win_trades) / abs(sum(loss_trades)), 2) if loss_trades else None,
        "sharpe_approx"  : _sharpe(pnls),
        "max_drawdown"   : round(_max_drawdown(equity), 2),
    }

    # ── Buy & hold comparison ──────────────────────────────────────
    # Same share count (multiplier) bought once at the first trade's
    # entry price and held to each trade's exit date — gives a like-for-like
    # equity curve to chart next to the options-strategy curve.
    bh_entry_price = float(closes.iloc[0])
    bh_equity      = [
        round((float(closes.iloc[idx]) - bh_entry_price) * multiplier, 2)
        for idx in exit_indices
    ]
    bh_total_pnl   = bh_equity[-1] if bh_equity else 0.0
    bh_return_pct  = round((bh_total_pnl) / (bh_entry_price * multiplier) * 100, 2) if bh_entry_price else None

    buy_hold_summary = {
        "entry_price"   : round(bh_entry_price, 2),
        "exit_price"    : round(float(closes.iloc[exit_indices[-1]]), 2) if exit_indices else None,
        "shares"        : multiplier,
        "total_pnl"     : bh_total_pnl,
        "return_pct"    : bh_return_pct,
        "max_drawdown"  : round(_max_drawdown(bh_equity), 2),
    }

    summary["vs_buy_hold"] = {
        "options_pnl"  : summary["total_pnl"],
        "buy_hold_pnl" : bh_total_pnl,
        "edge"         : round(summary["total_pnl"] - bh_total_pnl, 2),
        "outperformed" : summary["total_pnl"] > bh_total_pnl,
    }

    return {
        "ticker"          : ticker.upper(),
        "strategy"        : strategy,
        "period"          : period,
        "dte"             : dte,
        "otm_pct"         : otm_pct,
        "width_mode"      : width_mode,
        "strike_width"    : strike_width,
        "trades"          : trades,
        "summary"         : summary,
        "equity_curve"    : [round(e, 2) for e in equity],
        "buy_hold_curve"  : bh_equity,
        "buy_hold_summary": buy_hold_summary,
    }


def _otm_strike(S_entry, otm_pct, strike_width, mode, direction):
    """Strike a fixed distance OTM from spot.
    direction=+1 for call-side strikes (above spot), -1 for put-side (below spot).
    mode="fixed" uses a constant $ distance (strike_width); mode="pct" (default)
    uses otm_pct as a fraction of spot, so the distance scales with stock price.
    """
    if mode == "fixed":
        return round(S_entry + direction * strike_width, 0)
    return round(S_entry * (1 + direction * otm_pct), 0)


def _spread_width(S_entry, otm_pct, strike_width, mode):
    """$ gap between the two legs of a 2-leg spread."""
    if mode == "fixed":
        return float(strike_width)
    return float(S_entry * otm_pct)


def _simulate_trade(strategy, S_entry, S_exit, hv, T, r, otm_pct, multiplier,
                     width_mode="pct", strike_width=5.0) -> dict:
    """Simulate P&L for one trade cycle given entry/exit stock prices."""

    if strategy == "covered_call":
        K       = _otm_strike(S_entry, otm_pct, strike_width, width_mode, +1)
        premium = bs_price(S_entry, K, T, r, hv, "call")
        # Stock P&L + premium collected - intrinsic if called away
        stock_pnl = S_exit - S_entry
        option_pnl = premium - max(0, S_exit - K)   # short call P&L
        pnl = (stock_pnl + option_pnl) * multiplier
        return {"strategy": "covered_call", "strike": K, "premium": round(premium, 4), "pnl": round(pnl, 2)}

    elif strategy == "cash_secured_put":
        K       = _otm_strike(S_entry, otm_pct, strike_width, width_mode, -1)
        premium = bs_price(S_entry, K, T, r, hv, "put")
        option_pnl = premium - max(0, K - S_exit)   # short put P&L
        pnl = option_pnl * multiplier
        return {"strategy": "cash_secured_put", "strike": K, "premium": round(premium, 4), "pnl": round(pnl, 2)}

    elif strategy == "long_call":
        K       = round(S_entry, 0)
        premium = bs_price(S_entry, K, T, r, hv, "call")
        pnl     = (max(0, S_exit - K) - premium) * multiplier
        return {"strategy": "long_call", "strike": K, "premium": round(premium, 4), "pnl": round(pnl, 2)}

    elif strategy == "long_put":
        K       = round(S_entry, 0)
        premium = bs_price(S_entry, K, T, r, hv, "put")
        pnl     = (max(0, K - S_exit) - premium) * multiplier
        return {"strategy": "long_put", "strike": K, "premium": round(premium, 4), "pnl": round(pnl, 2)}

    elif strategy == "iron_condor":
        sd      = S_entry * hv * np.sqrt(T)
        Kps     = round(S_entry - sd, 0)       # put sell
        Kpb     = round(S_entry - sd * 1.5, 0) # put buy
        Kcs     = round(S_entry + sd, 0)       # call sell
        Kcb     = round(S_entry + sd * 1.5, 0) # call buy

        net_credit = (
            bs_price(S_entry, Kps, T, r, hv, "put")  - bs_price(S_entry, Kpb, T, r, hv, "put") +
            bs_price(S_entry, Kcs, T, r, hv, "call") - bs_price(S_entry, Kcb, T, r, hv, "call")
        )
        put_loss  = max(0, Kps - S_exit) - max(0, Kpb - S_exit)
        call_loss = max(0, S_exit - Kcs) - max(0, S_exit - Kcb)
        pnl = (net_credit - put_loss - call_loss) * multiplier
        return {"strategy": "iron_condor", "net_credit": round(net_credit, 4), "pnl": round(pnl, 2)}

    elif strategy == "bull_call_spread":
        K_long  = round(S_entry, 0)
        width   = _spread_width(S_entry, otm_pct, strike_width, width_mode)
        K_short = K_long + width
        net_debit = bs_price(S_entry, K_long, T, r, hv, "call") - bs_price(S_entry, K_short, T, r, hv, "call")
        payoff  = max(0, S_exit - K_long) - max(0, S_exit - K_short)
        pnl     = (payoff - net_debit) * multiplier
        return {"strategy": "bull_call_spread", "strikes": [K_long, K_short], "net_debit": round(net_debit, 4), "pnl": round(pnl, 2)}

    elif strategy == "bear_put_spread":
        K_long  = round(S_entry, 0)
        width   = _spread_width(S_entry, otm_pct, strike_width, width_mode)
        K_short = K_long - width
        net_debit = bs_price(S_entry, K_long, T, r, hv, "put") - bs_price(S_entry, K_short, T, r, hv, "put")
        payoff  = max(0, K_long - S_exit) - max(0, K_short - S_exit)
        pnl     = (payoff - net_debit) * multiplier
        return {"strategy": "bear_put_spread", "strikes": [K_long, K_short], "net_debit": round(net_debit, 4), "pnl": round(pnl, 2)}

    elif strategy == "bull_put_spread":
        K_short = _otm_strike(S_entry, otm_pct, strike_width, width_mode, -1)   # sell higher put
        width   = _spread_width(S_entry, otm_pct, strike_width, width_mode)
        K_long  = K_short - width                                               # buy lower put
        net_credit = bs_price(S_entry, K_short, T, r, hv, "put") - bs_price(S_entry, K_long, T, r, hv, "put")
        loss    = max(0, K_short - S_exit) - max(0, K_long - S_exit)
        pnl     = (net_credit - loss) * multiplier
        return {"strategy": "bull_put_spread", "strikes": [K_long, K_short], "net_credit": round(net_credit, 4), "pnl": round(pnl, 2)}

    elif strategy == "bear_call_spread":
        K_short = _otm_strike(S_entry, otm_pct, strike_width, width_mode, +1)   # sell lower call
        width   = _spread_width(S_entry, otm_pct, strike_width, width_mode)
        K_long  = K_short + width                                               # buy higher call
        net_credit = bs_price(S_entry, K_short, T, r, hv, "call") - bs_price(S_entry, K_long, T, r, hv, "call")
        loss    = max(0, S_exit - K_short) - max(0, S_exit - K_long)
        pnl     = (net_credit - loss) * multiplier
        return {"strategy": "bear_call_spread", "strikes": [K_short, K_long], "net_credit": round(net_credit, 4), "pnl": round(pnl, 2)}

    elif strategy == "protective_put":
        K       = _otm_strike(S_entry, otm_pct, strike_width, width_mode, -1)
        premium = bs_price(S_entry, K, T, r, hv, "put")
        stock_pnl  = S_exit - S_entry
        option_pnl = max(0, K - S_exit) - premium
        pnl     = (stock_pnl + option_pnl) * multiplier
        return {"strategy": "protective_put", "strike": K, "premium": round(premium, 4), "pnl": round(pnl, 2)}

    elif strategy == "short_straddle":
        K       = round(S_entry, 0)
        premium = bs_price(S_entry, K, T, r, hv, "call") + bs_price(S_entry, K, T, r, hv, "put")
        loss    = max(0, S_exit - K) + max(0, K - S_exit)
        pnl     = (premium - loss) * multiplier
        return {"strategy": "short_straddle", "strike": K, "premium": round(premium, 4), "pnl": round(pnl, 2)}