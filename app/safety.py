"""SQL gate. Layer 1 of 3: text checks. (Layer 2: SQLite authorizer, Layer 3: read-only connection.)"""
import re
from dataclasses import dataclass

from .config import ROW_LIMIT

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|reindex|"
    r"truncate|grant|revoke|begin|commit|rollback|savepoint|load_extension)\b",
    re.I,
)


@dataclass
class Verdict:
    ok: bool
    sql: str          # cleaned SQL (LIMIT enforced) when ok
    reason: str       # why it was refused
    blocked: bool     # True = attempt to write/alter data -> never retried


def _strip_comments(s: str) -> str:
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    return re.sub(r"--[^\n]*", " ", s)


def _strip_literals(s: str) -> str:
    s = re.sub(r"'(?:[^']|'')*'", "''", s)
    return re.sub(r'"(?:[^"]|"")*"', '""', s)


def validate(sql: str, limit: int = ROW_LIMIT) -> Verdict:
    if not sql or not sql.strip():
        return Verdict(False, "", "empty query", False)
    s = _strip_comments(sql).strip().rstrip(";").strip()
    scan = _strip_literals(s)
    if ";" in scan:
        return Verdict(False, "", "multiple statements are not allowed", True)
    hit = FORBIDDEN.search(scan)
    if hit:
        return Verdict(False, "", f"{hit.group(1).upper()} is not allowed (read-only access)", True)
    if not re.match(r"\s*(select|with)\b", scan, re.I):
        return Verdict(False, "", "only SELECT statements are allowed", False)
    if not re.search(r"\blimit\s+\d+", scan, re.I):
        s = f"{s} LIMIT {limit}"
    return Verdict(True, s, "", False)
