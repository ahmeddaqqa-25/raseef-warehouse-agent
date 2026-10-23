"""The agent: get_schema -> generate_sql -> validate_sql -> execute_sql -> generate_answer,
with a self-correction loop and a hard stop for write attempts.

Runs on LangGraph. If langgraph is not installed it falls back to a tiny built-in runner that
uses the exact same nodes and routing functions (so the behaviour is identical)."""
import sqlite3
import time
from typing import Any, Dict, Iterator, List, Optional, TypedDict

from . import config, db, llm, safety

try:
    from langgraph.graph import END, StateGraph
    ENGINE = "langgraph"
except Exception:  # pragma: no cover
    END, StateGraph, ENGINE = None, None, "builtin"


class State(TypedDict, total=False):
    question: str
    lang: str
    schema: str
    sql: str
    error: str
    status: str          # "" | ok | rejected | failed | unsupported
    fatal: bool
    attempts: int
    columns: List[str]
    rows: List[list]
    answer: str
    last_step: Dict[str, Any]


def _timed(fn):
    def wrapper(state: State) -> dict:
        t = time.perf_counter()
        out = fn(state)
        out["last_step"]["ms"] = round((time.perf_counter() - t) * 1000)
        out["last_step"]["attempt"] = out.get("attempts", state.get("attempts", 0))
        return out
    wrapper.__name__ = fn.__name__
    return wrapper


@_timed
def get_schema(state: State) -> dict:
    schema = db.schema_text()
    n = schema.count("CREATE TABLE")
    return {"schema": schema, "attempts": 0, "status": "", "error": "",
            "last_step": {"node": "get_schema", "ok": True, "detail": f"{n} tables read"}}


@_timed
def generate_sql(state: State) -> dict:
    attempts = state.get("attempts", 0) + 1
    try:
        sql = llm.generate_sql(state["question"], state["schema"], state.get("sql", ""), state.get("error", ""))
    except Exception as e:
        msg = f"LLM call failed: {type(e).__name__}: {e}"
        return {"attempts": attempts, "sql": "", "error": msg, "status": "failed", "fatal": True,
                "last_step": {"node": "generate_sql", "ok": False, "detail": msg}}
    if not sql:
        return {"attempts": attempts, "sql": "", "status": "unsupported", "error": "",
                "last_step": {"node": "generate_sql", "ok": False, "detail": "no query produced"}}
    return {"attempts": attempts, "sql": sql, "error": "",
            "last_step": {"node": "generate_sql", "ok": True, "detail": sql}}


@_timed
def validate_sql(state: State) -> dict:
    v = safety.validate(state["sql"])
    if v.ok:
        return {"sql": v.sql, "error": "",
                "last_step": {"node": "validate_sql", "ok": True, "detail": "read-only SELECT, row limit enforced",
                              "sql": v.sql}}
    out = {"error": v.reason,
           "last_step": {"node": "validate_sql", "ok": False, "detail": v.reason, "blocked": v.blocked}}
    if v.blocked:
        out["status"] = "rejected"
    return out


@_timed
def execute_sql(state: State) -> dict:
    try:
        cols, rows = db.execute(state["sql"])
    except sqlite3.Error as e:
        return {"error": str(e), "last_step": {"node": "execute_sql", "ok": False, "detail": str(e)}}
    return {"columns": cols, "rows": rows, "error": "", "status": "ok",
            "last_step": {"node": "execute_sql", "ok": True, "detail": f"{len(rows)} rows"}}


@_timed
def generate_answer(state: State) -> dict:
    status = state.get("status") or "failed"
    answer = llm.write_answer(state["question"], state.get("columns", []), state.get("rows", []),
                              status, state["lang"], reason=state.get("error", ""),
                              attempts=state.get("attempts", 0))
    return {"answer": answer, "status": status,
            "last_step": {"node": "generate_answer", "ok": status == "ok", "detail": ""}}


# ---- routing (shared by LangGraph and the built-in runner) ------------------
def after_generate(s: State) -> str:
    return "generate_answer" if (s.get("fatal") or not s.get("sql")) else "validate_sql"


def after_validate(s: State) -> str:
    if not s.get("error"):
        return "execute_sql"
    if s.get("status") == "rejected":
        return "generate_answer"                 # write attempt: stop, never retry
    return "generate_sql" if s.get("attempts", 0) < config.MAX_ATTEMPTS else "generate_answer"


def after_execute(s: State) -> str:
    if not s.get("error"):
        return "generate_answer"
    return "generate_sql" if s.get("attempts", 0) < config.MAX_ATTEMPTS else "generate_answer"


NODES = {"get_schema": get_schema, "generate_sql": generate_sql, "validate_sql": validate_sql,
         "execute_sql": execute_sql, "generate_answer": generate_answer}
ROUTES = {"get_schema": lambda s: "generate_sql", "generate_sql": after_generate,
          "validate_sql": after_validate, "execute_sql": after_execute, "generate_answer": lambda s: None}


def _build_graph():
    g = StateGraph(State)
    for name, fn in NODES.items():
        g.add_node(name, fn)
    g.set_entry_point("get_schema")
    g.add_edge("get_schema", "generate_sql")
    g.add_conditional_edges("generate_sql", after_generate,
                            {"validate_sql": "validate_sql", "generate_answer": "generate_answer"})
    g.add_conditional_edges("validate_sql", after_validate,
                            {"execute_sql": "execute_sql", "generate_sql": "generate_sql",
                             "generate_answer": "generate_answer"})
    g.add_conditional_edges("execute_sql", after_execute,
                            {"generate_answer": "generate_answer", "generate_sql": "generate_sql"})
    g.add_edge("generate_answer", END)
    return g.compile()


_GRAPH = _build_graph() if ENGINE == "langgraph" else None


def _steps(state: State) -> Iterator[tuple]:
    if _GRAPH is not None:
        for chunk in _GRAPH.stream(state, stream_mode="updates"):
            for node, upd in chunk.items():
                yield node, upd
    else:
        node: Optional[str] = "get_schema"
        while node:
            upd = NODES[node](state)
            state.update(upd)
            yield node, upd
            node = ROUTES[node](state)


def run(question: str) -> Iterator[dict]:
    """Yield one event per node, then a final 'done' event."""
    t0 = time.perf_counter()
    state: State = {"question": question.strip(), "lang": llm.detect_lang(question)}
    for node, upd in _steps(dict(state)):
        state.update(upd)
        yield {"type": "step", **upd["last_step"]}
    yield {
        "type": "done",
        "status": state.get("status", "failed"),
        "answer": state.get("answer", ""),
        "sql": state.get("sql", ""),
        "columns": state.get("columns", []),
        "rows": state.get("rows", []),
        "attempts": state.get("attempts", 0),
        "total_ms": round((time.perf_counter() - t0) * 1000),
        "provider": config.provider(),
        "model": config.model_name(),
        "engine": ENGINE,
    }


def ask(question: str) -> dict:
    last = {}
    for ev in run(question):
        last = ev
    return last
