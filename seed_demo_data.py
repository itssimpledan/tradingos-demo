"""
seed_demo_data.py — Wipe the database and load fictional sample data
for the public TradingOS demo.

Run once after deploying:  python seed_demo_data.py

All tickers, prices, and dates below are illustrative only — none of
this reflects any real portfolio.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from database import init_db, get_conn, DB_PATH

TODAY = datetime.today()


def d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def wipe_all_data():
    """Delete all rows from every user-data table, keep schema + default platforms."""
    with get_conn() as conn:
        for table in [
            "trades", "equities", "equity_purchases", "crypto",
            "watchlist", "backtest_runs", "cash", "networth_items",
            "monthly_snapshots",
        ]:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence")  # reset autoincrement ids


def seed_platforms():
    with get_conn() as conn:
        for name, cat in [("CDP", "equity"), ("IB", "equity"), ("Webull", "equity"),
                           ("Coinbase", "crypto"), ("Binance", "crypto")]:
            conn.execute("INSERT OR IGNORE INTO platforms (name, category) VALUES (?,?)", (name, cat))


def seed_equities():
    rows = [
        dict(ticker="AAPL", company="Apple Inc.", sector="Technology", industry="Consumer Electronics",
             shares=40, cost_price=178.20, current_price=212.50, price_date=d(0),
             purchase_date=d(420), currency="USD", platform="IB", notes="Demo holding"),
        dict(ticker="MSFT", company="Microsoft Corp.", sector="Technology", industry="Software",
             shares=18, cost_price=339.10, current_price=441.80, price_date=d(0),
             purchase_date=d(380), currency="USD", platform="IB", notes="Demo holding"),
        dict(ticker="NVDA", company="NVIDIA Corp.", sector="Technology", industry="Semiconductors",
             shares=25, cost_price=98.40, current_price=131.20, price_date=d(0),
             purchase_date=d(300), currency="USD", platform="Webull", notes="Demo holding"),
        dict(ticker="O", company="Realty Income Corp.", sector="Real Estate", industry="REIT",
             shares=120, cost_price=54.30, current_price=58.10, price_date=d(0),
             purchase_date=d(540), currency="USD", platform="CDP", notes="Demo holding — income play"),
        dict(ticker="VOO", company="Vanguard S&P 500 ETF", sector="ETF", industry="Index Fund",
             shares=15, cost_price=420.00, current_price=512.30, price_date=d(0),
             purchase_date=d(700), currency="USD", platform="IB", notes="Demo holding — core position"),
    ]
    for r in rows:
        from database import add_equity
        add_equity(r)


def seed_crypto():
    rows = [
        dict(symbol="BTC", name="Bitcoin", quantity=0.35, cost_price=58000, current_price=67500,
             price_date=d(0), platform="Coinbase", purchase_date=d(260), currency="USD",
             notes="Demo holding"),
        dict(symbol="ETH", name="Ethereum", quantity=3.2, cost_price=2600, current_price=3550,
             price_date=d(0), platform="Binance", purchase_date=d(200), currency="USD",
             notes="Demo holding"),
    ]
    for r in rows:
        from database import add_crypto
        add_crypto(r)


def seed_cash():
    rows = [
        dict(platform="IB",       amount=8500,  currency="USD", notes="Demo cash buffer"),
        dict(platform="CDP",      amount=4200,  currency="SGD", notes="Demo cash buffer"),
        dict(platform="Coinbase", amount=600,   currency="USD", notes="Demo idle balance"),
    ]
    for r in rows:
        from database import add_cash
        add_cash(r)


def seed_trades():
    """A mix of closed (won/lost) and open options trades across strategies."""
    from database import add_trade, close_trade

    closed = [
        # ticker, strategy, direction, type, strike, expiry(days_from_open), contracts, premium, open_days_ago, close_premium_diff_days, close_premium, win
        dict(ticker="AAPL", strategy="bear_call_spread", direction="SELL", option_type="call",
             strike=225, expiry=d(-15), contracts=2, premium=2.10, open_date=d(45),
             platform="IB", notes="Demo trade", trade_group="AAPL-BCS-1",
             close_date=d(15), close_premium=0.40),
        dict(ticker="LNG", strategy="bear_call_spread", direction="SELL", option_type="call",
             strike=230, expiry=d(-50), contracts=1, premium=3.80, open_date=d(80),
             platform="IB", notes="Demo trade", trade_group="LNG-BCS-1",
             close_date=d(50), close_premium=9.25),  # loser
        dict(ticker="MSFT", strategy="covered_call", direction="SELL", option_type="call",
             strike=460, expiry=d(-20), contracts=3, premium=4.50, open_date=d(50),
             platform="IB", notes="Demo trade", trade_group="MSFT-CC-1",
             close_date=d(20), close_premium=0.20),
        dict(ticker="NVDA", strategy="cash_secured_put", direction="SELL", option_type="put",
             strike=120, expiry=d(-25), contracts=2, premium=3.10, open_date=d(55),
             platform="Webull", notes="Demo trade", trade_group="NVDA-CSP-1",
             close_date=d(25), close_premium=0.15),
        dict(ticker="O", strategy="bull_put_spread", direction="SELL", option_type="put",
             strike=55, expiry=d(-10), contracts=4, premium=1.20, open_date=d(40),
             platform="CDP", notes="Demo trade", trade_group="O-BPS-1",
             close_date=d(10), close_premium=2.90),  # loser
    ]

    for t in closed:
        close_date  = t.pop("close_date")
        close_prem  = t.pop("close_premium")
        trade_id = add_trade(t)
        close_trade(trade_id, close_premium=close_prem, close_date=close_date)

    open_trades = [
        dict(ticker="VOO", strategy="covered_call", direction="SELL", option_type="call",
             strike=530, expiry=(TODAY + timedelta(days=18)).strftime("%Y-%m-%d"),
             contracts=1, premium=3.40, open_date=d(12), platform="IB",
             notes="Demo open trade", trade_group="VOO-CC-1"),
        dict(ticker="AAPL", strategy="bull_call_spread", direction="BUY", option_type="call",
             strike=210, expiry=(TODAY + timedelta(days=30)).strftime("%Y-%m-%d"),
             contracts=2, premium=6.10, open_date=d(8), platform="IB",
             notes="Demo open trade", trade_group="AAPL-BUCS-1"),
        dict(ticker="NVDA", strategy="iron_condor", direction="SELL", option_type="call",
             strike=140, expiry=(TODAY + timedelta(days=21)).strftime("%Y-%m-%d"),
             contracts=1, premium=2.80, open_date=d(5), platform="Webull",
             notes="Demo open trade", trade_group="NVDA-IC-1"),
    ]
    for t in open_trades:
        add_trade(t)


def seed_watchlist():
    from database import add_to_watchlist
    for ticker, sector, theme, score in [
        ("PLTR", "Technology", "AI Application Layer", 82),
        ("CRWD", "Technology", "Cybersecurity", 78),
        ("LLY",  "Healthcare", "GLP-1 / Obesity", 75),
        ("SMCI", "Technology", "AI Infrastructure", 64),
    ]:
        add_to_watchlist(ticker, sector=sector, score=score, screener_theme=theme,
                          notes="Demo watchlist entry")


def seed_networth():
    from database import add_networth_item
    rows = [
        dict(category="cash",       label="Bank Accounts (demo)",        amount=18000, currency="SGD", liquid=1, sort_order=1),
        dict(category="cpf_srs",    label="CPF / SRS (demo)",            amount=62000, currency="SGD", liquid=0, sort_order=2),
        dict(category="property",   label="Primary Residence (demo)",    amount=850000, currency="SGD", liquid=0, sort_order=3),
        dict(category="investment", label="Brokerage Portfolio (demo)",  amount=145000, currency="SGD", liquid=1, sort_order=4),
        dict(category="liability",  label="Mortgage Balance (demo)",     amount=420000, currency="SGD", liquid=0, sort_order=5),
    ]
    for r in rows:
        add_networth_item(r)


def main():
    print(f"[seed] Using database at {DB_PATH}")
    init_db()
    print("[seed] Wiping existing data…")
    wipe_all_data()
    print("[seed] Seeding demo platforms…")
    seed_platforms()
    print("[seed] Seeding demo equities…")
    seed_equities()
    print("[seed] Seeding demo crypto…")
    seed_crypto()
    print("[seed] Seeding demo cash balances…")
    seed_cash()
    print("[seed] Seeding demo options trades…")
    seed_trades()
    print("[seed] Seeding demo watchlist…")
    seed_watchlist()
    print("[seed] Seeding demo net worth items…")
    seed_networth()
    print("[seed] Done. This database now contains fictional sample data only.")


if __name__ == "__main__":
    main()
