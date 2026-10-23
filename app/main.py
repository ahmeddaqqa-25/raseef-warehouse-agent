"""FastAPI server. Run:  python -m uvicorn app.main:app --port 8000"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import agent, config, db

app = FastAPI(title="Raseef - Warehouse SQL Agent")
STATIC = Path(__file__).parent / "static"


@app.on_event("startup")
def _ensure_db() -> None:
    if not config.DB_PATH.exists():
        from data.generate_data import build
        build(config.DB_PATH)


class Ask(BaseModel):
    question: str


def _clean(q: str) -> str:
    q = q.strip()
    if not q:
        raise HTTPException(400, "question is empty")
    if len(q) > 500:
        raise HTTPException(400, "question is too long (max 500 characters)")
    return q


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": config.provider(), "model": config.model_name(), "engine": agent.ENGINE}


@app.get("/api/stats")
def stats():
    return db.stats()


@app.get("/api/schema")
def schema():
    return db.table_overview()


@app.post("/api/ask")
def ask_stream(body: Ask):
    """Streams one JSON line per agent step, then a final 'done' line."""
    q = _clean(body.question)

    def gen():
        for ev in agent.run(q):
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/ask/sync")
def ask_sync(body: Ask):
    return agent.ask(_clean(body.question))
