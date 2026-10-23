"""Run with:  python -m pytest -q     (or just: python tests/test_safety.py)"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, safety  # noqa: E402


def test_plain_select_gets_limit():
    v = safety.validate("SELECT name FROM products")
    assert v.ok and v.sql.endswith("LIMIT 100")


def test_existing_limit_is_kept():
    assert safety.validate("SELECT name FROM products LIMIT 3").sql.endswith("LIMIT 3")


def test_cte_allowed():
    assert safety.validate("WITH t AS (SELECT 1 AS x) SELECT x FROM t").ok


def test_write_statements_are_blocked():
    for sql in ["DROP TABLE products", "DELETE FROM products", "UPDATE products SET unit_price=0",
                "INSERT INTO warehouses(name,city) VALUES('a','b')", "ALTER TABLE products ADD x INT",
                "PRAGMA writable_schema=1", "ATTACH DATABASE 'x' AS y"]:
        v = safety.validate(sql)
        assert not v.ok and v.blocked, sql


def test_stacked_statements_blocked():
    v = safety.validate("SELECT 1; DROP TABLE products")
    assert not v.ok and v.blocked


def test_keywords_inside_strings_and_comments_are_fine():
    assert safety.validate("SELECT name FROM products WHERE name = 'delete me' -- drop table").ok


def test_non_select_is_not_blocked_but_rejected():
    v = safety.validate("Sorry, I cannot help with that")
    assert not v.ok and not v.blocked          # retryable: the LLM may fix its output


def test_database_layer_refuses_writes_even_if_gate_is_bypassed():
    for sql in ["DELETE FROM products", "DROP TABLE products", "UPDATE products SET unit_price = 0"]:
        try:
            db.execute(sql)
        except sqlite3.Error:
            continue
        raise AssertionError(f"not blocked: {sql}")


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            n += 1
            print("ok ", name)
    print(f"{n} tests passed")
