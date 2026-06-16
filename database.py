"""
database.py — SQLite layer for the Options Trading System
Tables:
  - trades           : options trades entered / exited
  - equities         : stock/ETF holdings
  - equity_purchases : individual purchase lots per equity (for history + weighted avg cost)
  - crypto           : crypto asset holdings
  - platforms        : brokerage / exchange list (user-extensible)
  - watchlist        : tickers under active screening
  - backtest_runs    : saved backtest results
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "options.db"


# ─────────────────────────────────────────────
# Connection helper
# ─────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─────────────────────────────────────────────
# Schema — initial tables (safe CREATE IF NOT EXISTS)
# ─────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    strategy        TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    option_type     TEXT    NOT NULL,
    strike          REAL    NOT NULL,
    expiry          TEXT    NOT NULL,
    contracts       INTEGER NOT NULL DEFAULT 1,
    premium         REAL    NOT NULL,
    open_date       TEXT    NOT NULL,
    close_date      TEXT,
    close_premium   REAL,
    status          TEXT    NOT NULL DEFAULT 'OPEN',
    pnl             REAL,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS equities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    company         TEXT,
    sector          TEXT,
    industry        TEXT,
    shares          REAL    NOT NULL,
    cost_price      REAL    NOT NULL,
    current_price   REAL,
    price_date      TEXT,
    purchase_date   TEXT,
    currency        TEXT    NOT NULL DEFAULT 'USD',
    platform        TEXT,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS equity_purchases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    equity_id   INTEGER NOT NULL,
    shares      REAL    NOT NULL,
    price       REAL    NOT NULL,
    date        TEXT    NOT NULL,
    platform    TEXT,
    notes       TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (equity_id) REFERENCES equities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crypto (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    name            TEXT,
    quantity        REAL    NOT NULL,
    cost_price      REAL    NOT NULL,
    current_price   REAL,
    price_date      TEXT,
    platform        TEXT,
    purchase_date   TEXT,
    currency        TEXT    NOT NULL DEFAULT 'USD',
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS platforms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    category    TEXT    NOT NULL DEFAULT 'all'
);

CREATE TABLE IF NOT EXISTS watchlist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL UNIQUE,
    sector          TEXT,
    screener_theme  TEXT,
    score           INTEGER,
    added_date      TEXT    NOT NULL DEFAULT (datetime('now')),
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    strategy    TEXT    NOT NULL,
    params      TEXT    NOT NULL,
    result      TEXT    NOT NULL,
    run_date    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cash (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform     TEXT    NOT NULL,
    amount       REAL    NOT NULL,
    currency     TEXT    NOT NULL DEFAULT 'SGD',
    notes        TEXT,
    updated_date TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS networth_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT    NOT NULL DEFAULT 'other',
    label       TEXT    NOT NULL,
    amount      REAL    NOT NULL DEFAULT 0,
    currency    TEXT    NOT NULL DEFAULT 'SGD',
    liquid      INTEGER NOT NULL DEFAULT 1,
    notes       TEXT,
    details     TEXT,
    sort_order  INTEGER DEFAULT 0,
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS monthly_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    month               TEXT    NOT NULL UNIQUE,  -- e.g. '2026-06'
    portfolio_value     REAL    NOT NULL DEFAULT 0,
    equities_value      REAL    NOT NULL DEFAULT 0,
    crypto_value        REAL    NOT NULL DEFAULT 0,
    options_pnl         REAL    NOT NULL DEFAULT 0,
    options_open        INTEGER NOT NULL DEFAULT 0,
    win_rate            REAL    NOT NULL DEFAULT 0,
    net_worth           REAL    NOT NULL DEFAULT 0,
    total_assets        REAL    NOT NULL DEFAULT 0,
    total_liabilities   REAL    NOT NULL DEFAULT 0,
    notes               TEXT,
    breakdown_json      TEXT,
    saved_at            TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

DEFAULT_PLATFORMS = [
    ("CDP",      "equity"),
    ("Webull",   "equity"),
    ("SCB",      "equity"),
    ("IB",       "equity"),
    ("Binance",  "crypto"),
    ("Coinbase", "crypto"),
    ("Bybit",    "crypto"),
    ("Kraken",   "crypto"),
    ("OKX",      "crypto"),
]


def init_db() -> None:
    """Create all tables and seed default platforms. Safe to call every startup."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Seed default platforms (ignore if already exist)
        for name, cat in DEFAULT_PLATFORMS:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO platforms (name, category) VALUES (?,?)",
                    (name, cat)
                )
            except Exception:
                pass
        # Safe migration: add columns that may not exist yet
        _safe_alter(conn, "ALTER TABLE equities ADD COLUMN platform TEXT")
        _safe_alter(conn, "ALTER TABLE trades ADD COLUMN platform TEXT")
        _safe_alter(conn, "ALTER TABLE trades ADD COLUMN trade_group TEXT")
        _safe_alter(conn, "ALTER TABLE networth_items ADD COLUMN details TEXT")
        _safe_alter(conn, "ALTER TABLE monthly_snapshots ADD COLUMN breakdown_json TEXT")
        _safe_alter(conn, "ALTER TABLE watchlist ADD COLUMN screener_theme TEXT")
        _safe_alter(conn, "ALTER TABLE watchlist ADD COLUMN score INTEGER")
    print(f"[DB] Initialised → {DB_PATH}")


def _safe_alter(conn, sql: str) -> None:
    try:
        conn.execute(sql)
    except Exception:
        pass  # column already exists


# ═══════════════════════════════════════════════
# PLATFORMS
# ═══════════════════════════════════════════════

def list_platforms(category: str = None) -> list[dict]:
    sql = "SELECT * FROM platforms"
    params = []
    if category:
        sql += " WHERE category=? OR category='all'"
        params.append(category)
    sql += " ORDER BY name"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def add_platform(name: str, category: str = "all") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO platforms (name, category) VALUES (?,?)",
            (name.strip(), category)
        )
        return cur.lastrowid


def delete_platform(platform_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM platforms WHERE id=?", (platform_id,))


# ═══════════════════════════════════════════════
# EQUITIES
# ═══════════════════════════════════════════════

def add_equity(data: dict) -> int:
    cols = ["ticker", "company", "sector", "industry", "shares",
            "cost_price", "current_price", "price_date", "purchase_date",
            "currency", "platform", "notes"]
    values = [data.get(c) for c in cols]
    sql = f"INSERT INTO equities ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
    with get_conn() as conn:
        cur = conn.execute(sql, values)
        eq_id = cur.lastrowid
        # Record initial purchase lot
        if data.get("shares") and data.get("cost_price"):
            conn.execute(
                "INSERT INTO equity_purchases (equity_id, shares, price, date, platform, notes) VALUES (?,?,?,?,?,?)",
                (eq_id, data["shares"], data["cost_price"],
                 data.get("purchase_date") or datetime.today().strftime("%Y-%m-%d"),
                 data.get("platform"), data.get("notes"))
            )
        return eq_id


def list_equities() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM equities ORDER BY ticker").fetchall()]


def get_equity(eq_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM equities WHERE id=?", (eq_id,)).fetchone()
        return dict(row) if row else None


def update_equity(eq_id: int, data: dict) -> None:
    allowed = ["ticker", "company", "sector", "industry", "shares",
               "cost_price", "current_price", "price_date", "purchase_date",
               "currency", "platform", "notes"]
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE equities SET {set_clause} WHERE id=?",
            list(fields.values()) + [eq_id]
        )


def update_equity_price(eq_id: int, price: float, price_date: str = None) -> None:
    if price_date is None:
        price_date = datetime.today().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            "UPDATE equities SET current_price=?, price_date=? WHERE id=?",
            (price, price_date, eq_id)
        )


def delete_equity(eq_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM equities WHERE id=?", (eq_id,))


def bulk_insert_equities(rows: list[dict]) -> tuple[int, list[str]]:
    """Insert multiple equity rows. Returns (count_inserted, error_list)."""
    count, errors = 0, []
    for row in rows:
        try:
            add_equity(row)
            count += 1
        except Exception as e:
            errors.append(f"{row.get('ticker','?')}: {e}")
    return count, errors


def equities_summary() -> dict:
    holdings = list_equities()
    if not holdings:
        return {"total_holdings": 0, "total_cost": 0, "total_value": 0,
                "total_pnl": 0, "total_pnl_pct": 0}
    total_cost  = sum((h["shares"] or 0) * (h["cost_price"] or 0) for h in holdings)
    total_value = sum((h["shares"] or 0) * (h["current_price"] or h["cost_price"] or 0) for h in holdings)
    total_pnl   = total_value - total_cost
    pnl_pct     = (total_pnl / total_cost * 100) if total_cost else 0
    return {
        "total_holdings": len(holdings),
        "total_cost"    : round(total_cost,  2),
        "total_value"   : round(total_value, 2),
        "total_pnl"     : round(total_pnl,   2),
        "total_pnl_pct" : round(pnl_pct,     2),
    }


# ═══════════════════════════════════════════════
# EQUITY PURCHASES (lot-level history)
# ═══════════════════════════════════════════════

def list_purchases(equity_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM equity_purchases WHERE equity_id=? ORDER BY date DESC",
            (equity_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def add_purchase(equity_id: int, shares: float, price: float,
                 date: str = None, platform: str = None, notes: str = None) -> dict:
    """
    Add a purchase lot and recalculate weighted-average cost + total shares on the parent equity.
    Returns updated equity dict.
    """
    if date is None:
        date = datetime.today().strftime("%Y-%m-%d")

    eq = get_equity(equity_id)
    if eq is None:
        raise ValueError(f"Equity {equity_id} not found")

    # Weighted average cost
    old_shares = eq["shares"] or 0
    old_cost   = eq["cost_price"] or 0
    new_shares = old_shares + shares
    new_cost   = ((old_shares * old_cost) + (shares * price)) / new_shares if new_shares else price

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO equity_purchases (equity_id, shares, price, date, platform, notes) VALUES (?,?,?,?,?,?)",
            (equity_id, shares, price, date, platform, notes)
        )
        conn.execute(
            "UPDATE equities SET shares=?, cost_price=? WHERE id=?",
            (round(new_shares, 6), round(new_cost, 6), equity_id)
        )

    return get_equity(equity_id)


def delete_purchase(purchase_id: int) -> None:
    """Delete a purchase lot and recalculate weighted avg on the parent equity."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM equity_purchases WHERE id=?", (purchase_id,)
        ).fetchone()
        if not row:
            return
        eq_id = row["equity_id"]
        conn.execute("DELETE FROM equity_purchases WHERE id=?", (purchase_id,))
        # Recalculate from remaining lots
        lots = conn.execute(
            "SELECT * FROM equity_purchases WHERE equity_id=?", (eq_id,)
        ).fetchall()
        if lots:
            total_shares = sum(l["shares"] for l in lots)
            avg_cost     = sum(l["shares"] * l["price"] for l in lots) / total_shares
            conn.execute(
                "UPDATE equities SET shares=?, cost_price=? WHERE id=?",
                (round(total_shares, 6), round(avg_cost, 6), eq_id)
            )
        else:
            # No lots left — zero out
            conn.execute(
                "UPDATE equities SET shares=0, cost_price=0 WHERE id=?", (eq_id,)
            )


# ═══════════════════════════════════════════════
# CRYPTO
# ═══════════════════════════════════════════════

def add_crypto(data: dict) -> int:
    cols = ["symbol", "name", "quantity", "cost_price", "current_price",
            "price_date", "platform", "purchase_date", "currency", "notes"]
    values = [data.get(c) for c in cols]
    sql = f"INSERT INTO crypto ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
    with get_conn() as conn:
        cur = conn.execute(sql, values)
        return cur.lastrowid


def list_crypto() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM crypto ORDER BY symbol").fetchall()]


def get_crypto(cr_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM crypto WHERE id=?", (cr_id,)).fetchone()
        return dict(row) if row else None


def update_crypto(cr_id: int, data: dict) -> None:
    allowed = ["symbol", "name", "quantity", "cost_price", "current_price",
               "price_date", "platform", "purchase_date", "currency", "notes"]
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE crypto SET {set_clause} WHERE id=?",
            list(fields.values()) + [cr_id]
        )


def update_crypto_price(cr_id: int, price: float, price_date: str = None) -> None:
    if price_date is None:
        price_date = datetime.today().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute(
            "UPDATE crypto SET current_price=?, price_date=? WHERE id=?",
            (price, price_date, cr_id)
        )


def delete_crypto(cr_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM crypto WHERE id=?", (cr_id,))


def crypto_summary() -> dict:
    holdings = list_crypto()
    if not holdings:
        return {"total_holdings": 0, "total_cost": 0, "total_value": 0,
                "total_pnl": 0, "total_pnl_pct": 0}
    total_cost  = sum((h["quantity"] or 0) * (h["cost_price"] or 0) for h in holdings)
    total_value = sum((h["quantity"] or 0) * (h["current_price"] or h["cost_price"] or 0) for h in holdings)
    total_pnl   = total_value - total_cost
    pnl_pct     = (total_pnl / total_cost * 100) if total_cost else 0
    return {
        "total_holdings": len(holdings),
        "total_cost"    : round(total_cost,  2),
        "total_value"   : round(total_value, 2),
        "total_pnl"     : round(total_pnl,   2),
        "total_pnl_pct" : round(pnl_pct,     2),
    }


# ═══════════════════════════════════════════════
# CASH
# ═══════════════════════════════════════════════

def list_cash() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cash ORDER BY platform, currency"
        ).fetchall()]


def add_cash(data: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO cash (platform, amount, currency, notes, updated_date) VALUES (?,?,?,?,?)",
            (data.get("platform"), float(data.get("amount", 0)),
             (data.get("currency") or "SGD").upper(),
             data.get("notes") or None,
             datetime.today().strftime("%Y-%m-%d"))
        )
        return cur.lastrowid


def update_cash(cash_id: int, data: dict) -> None:
    allowed = ["platform", "amount", "currency", "notes", "updated_date"]
    fields  = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return
    fields["updated_date"] = datetime.today().strftime("%Y-%m-%d")
    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE cash SET {set_clause} WHERE id=?",
            list(fields.values()) + [cash_id]
        )


def delete_cash(cash_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM cash WHERE id=?", (cash_id,))


# ═══════════════════════════════════════════════
# OPTIONS TRADES
# ═══════════════════════════════════════════════

def add_trade(data: dict) -> int:
    cols = ["ticker", "strategy", "direction", "option_type",
            "strike", "expiry", "contracts", "premium", "open_date", "platform", "notes",
            "trade_group"]
    values = [data.get(c) for c in cols]
    sql = f"INSERT INTO trades ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
    with get_conn() as conn:
        cur = conn.execute(sql, values)
        return cur.lastrowid


def close_trade(trade_id: int, close_premium: float, close_date: str = None,
                status: str = "CLOSED") -> None:
    if close_date is None:
        close_date = datetime.today().strftime("%Y-%m-%d")
    trade = get_trade(trade_id)
    if trade is None:
        raise ValueError(f"Trade {trade_id} not found")
    multiplier = 100 * trade["contracts"]
    pnl = (trade["premium"] - close_premium) * multiplier if trade["direction"] == "SELL" \
          else (close_premium - trade["premium"]) * multiplier
    with get_conn() as conn:
        conn.execute(
            "UPDATE trades SET status=?, close_date=?, close_premium=?, pnl=? WHERE id=?",
            (status.upper(), close_date, close_premium, pnl, trade_id)
        )


def update_trade(trade_id: int, data: dict) -> None:
    allowed = ["ticker", "strategy", "direction", "option_type", "strike", "expiry",
               "contracts", "premium", "open_date", "platform", "notes", "trade_group"]
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE trades SET {set_clause} WHERE id=?",
            list(fields.values()) + [trade_id]
        )


def get_trade(trade_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        return dict(row) if row else None


def list_trades(status: str = None) -> list[dict]:
    sql = "SELECT * FROM trades"
    params = []
    if status:
        sql += " WHERE status=?"
        params.append(status.upper())
    sql += " ORDER BY open_date DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def delete_trade(trade_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM trades WHERE id=?", (trade_id,))


# ═══════════════════════════════════════════════
# WATCHLIST
# ═══════════════════════════════════════════════

def add_to_watchlist(ticker: str, sector: str = None, notes: str = None,
                      score: int = None, screener_theme: str = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO watchlist (ticker, sector, notes, score, screener_theme) "
            "VALUES (?,?,?,?,?)",
            (ticker.upper(), sector, notes, score, screener_theme)
        )
        return cur.lastrowid


def list_watchlist() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM watchlist ORDER BY ticker").fetchall()]


def remove_from_watchlist(ticker: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker=?", (ticker.upper(),))


# ═══════════════════════════════════════════════
# BACKTESTS
# ═══════════════════════════════════════════════

def save_backtest(ticker: str, strategy: str, params: dict, result: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO backtest_runs (ticker, strategy, params, result) VALUES (?,?,?,?)",
            (ticker, strategy, json.dumps(params), json.dumps(result))
        )
        return cur.lastrowid


def list_backtests(ticker: str = None) -> list[dict]:
    sql = "SELECT id, ticker, strategy, run_date FROM backtest_runs"
    params = []
    if ticker:
        sql += " WHERE ticker=?"
        params.append(ticker.upper())
    sql += " ORDER BY run_date DESC LIMIT 50"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_backtest(run_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM backtest_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        r = dict(row)
        r["params"] = json.loads(r["params"])
        r["result"] = json.loads(r["result"])
        return r


# ═══════════════════════════════════════════════
# DASHBOARD SUMMARY
# ═══════════════════════════════════════════════

def portfolio_summary() -> dict:
    with get_conn() as conn:
        total     = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        open_pos  = conn.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()[0]
        closed    = conn.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED'").fetchone()[0]
        total_pnl = conn.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE status='CLOSED'").fetchone()[0]
        win_count = conn.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND pnl>0").fetchone()[0]
        win_rate  = round(win_count / closed * 100, 1) if closed > 0 else 0
    return {
        "total_trades"  : total,
        "open_positions": open_pos,
        "closed_trades" : closed,
        "total_pnl"     : round(total_pnl, 2),
        "win_rate"      : win_rate,
        "win_count"     : win_count,
        "equities"      : equities_summary(),
        "crypto"        : crypto_summary(),
    }


# ═══════════════════════════════════════════════
# NET WORTH ITEMS
# ═══════════════════════════════════════════════

def list_networth_items() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM networth_items ORDER BY category, sort_order, label"
        ).fetchall()]


def add_networth_item(data: dict) -> int:
    cols   = ["category", "label", "amount", "currency", "liquid", "notes", "details", "sort_order"]
    values = [data.get(c) for c in cols]
    sql    = f"INSERT INTO networth_items ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
    with get_conn() as conn:
        cur = conn.execute(sql, values)
        return cur.lastrowid


def update_networth_item(item_id: int, data: dict) -> None:
    allowed = ["category", "label", "amount", "currency", "liquid", "notes", "details", "sort_order"]
    # Only update columns present in the request — prevents NULLing out omitted fields
    cols = [c for c in allowed if c in data]
    if not cols:
        return
    sets = ", ".join(f"{c}=?" for c in cols)
    vals = [data[c] for c in cols] + [item_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE networth_items SET {sets} WHERE id=?", vals)


def delete_networth_item(item_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM networth_items WHERE id=?", (item_id,))


# ═══════════════════════════════════════════════
# MONTHLY SNAPSHOTS
# ═══════════════════════════════════════════════

def save_monthly_snapshot(data: dict) -> dict:
    """Insert or replace a monthly snapshot. 'month' must be 'YYYY-MM'."""
    cols = [
        "month", "portfolio_value", "equities_value", "crypto_value",
        "options_pnl", "options_open", "win_rate",
        "net_worth", "total_assets", "total_liabilities", "notes",
        "breakdown_json"
    ]
    vals = [data.get(c, 0 if c != "breakdown_json" else "{}") for c in cols]
    sql  = f"""
        INSERT INTO monthly_snapshots ({','.join(cols)})
        VALUES ({','.join(['?']*len(cols))})
        ON CONFLICT(month) DO UPDATE SET
            portfolio_value   = excluded.portfolio_value,
            equities_value    = excluded.equities_value,
            crypto_value      = excluded.crypto_value,
            options_pnl       = excluded.options_pnl,
            options_open      = excluded.options_open,
            win_rate          = excluded.win_rate,
            net_worth         = excluded.net_worth,
            total_assets      = excluded.total_assets,
            total_liabilities = excluded.total_liabilities,
            notes             = excluded.notes,
            breakdown_json    = excluded.breakdown_json,
            saved_at          = datetime('now')
    """
    with get_conn() as conn:
        conn.execute(sql, vals)
    return get_monthly_snapshot(data["month"])


def list_monthly_snapshots() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM monthly_snapshots ORDER BY month ASC"
        ).fetchall()]


def get_monthly_snapshot(month: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM monthly_snapshots WHERE month=?", (month,)
        ).fetchone()
        return dict(row) if row else None


def delete_monthly_snapshot(month: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM monthly_snapshots WHERE month=?", (month,)
        )
        conn.commit()
        return cur.rowcount > 0