"""Database access. The agent only ever sees a read-only, authorizer-guarded connection."""
import sqlite3
import time

from .config import DB_PATH, QUERY_TIMEOUT_S

_ALLOWED = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED else sqlite3.SQLITE_DENY


def _ro() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)


def execute(sql: str, max_rows: int = 200):
    """Run a (already validated) query. Returns (columns, rows). Raises sqlite3.Error."""
    conn = _ro()
    try:
        conn.set_authorizer(_authorizer)
        deadline = time.time() + QUERY_TIMEOUT_S
        conn.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 20000)
        cur = conn.execute(sql)
        cols = [c[0] for c in cur.description] if cur.description else []
        return cols, [list(r) for r in cur.fetchmany(max_rows)]
    finally:
        conn.close()


def schema_text() -> str:
    """CREATE statements + a few real values so the LLM spells filters correctly."""
    conn = _ro()
    try:
        ddl = [r[0] for r in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

        def vals(q):
            return ", ".join(repr(r[0]) for r in conn.execute(q))

        notes = [
            "products.category values: " + vals("SELECT DISTINCT category FROM products ORDER BY 1"),
            "warehouses.city values: " + vals("SELECT DISTINCT city FROM warehouses ORDER BY 1"),
            "suppliers.city values: " + vals("SELECT DISTINCT city FROM suppliers ORDER BY 1"),
            "sales_orders.status values: " + vals("SELECT DISTINCT status FROM sales_orders ORDER BY 1"),
            "stock_movements.movement_type values: 'in' (received from supplier), 'out' (dispatched)",
            "All dates are ISO text (YYYY-MM-DD). Use date('now', '-30 day') for relative dates.",
        ]
        return "\n\n".join(ddl) + "\n\n-- Notes\n" + "\n".join("-- " + n for n in notes)
    finally:
        conn.close()


def table_overview():
    conn = _ro()
    try:
        out = []
        names = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        for (name,) in names:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')]
            n = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            out.append({"table": name, "rows": n, "columns": cols})
        return out
    finally:
        conn.close()


def stats() -> dict:
    conn = _ro()
    try:
        def q(s):
            return conn.execute(s).fetchone()[0]

        wh = [
            {"name": r[0], "city": r[1], "units": r[2] or 0, "value": round(r[3] or 0, 2)}
            for r in conn.execute(
                """SELECT w.name, w.city, SUM(sl.quantity), SUM(sl.quantity * p.unit_price)
                   FROM warehouses w LEFT JOIN stock_levels sl ON sl.warehouse_id = w.id
                   LEFT JOIN products p ON p.id = sl.product_id GROUP BY w.id ORDER BY w.id""")
        ]
        return {
            "products": q("SELECT COUNT(*) FROM products"),
            "low_stock": q("""SELECT COUNT(*) FROM (SELECT 1 FROM products p JOIN stock_levels sl ON sl.product_id=p.id
                              GROUP BY p.id HAVING SUM(sl.quantity) <= p.reorder_level)"""),
            "orders_7d": q("SELECT COUNT(*) FROM sales_orders WHERE order_date >= date('now','-7 day')"),
            "warehouses": wh,
        }
    finally:
        conn.close()
