<<<<<<< HEAD
# Raseef (رصيف) - Warehouse SQL Agent

Ask a warehouse database questions in **Arabic or English**. A LangGraph agent writes the SQL, checks it,
runs it read-only, repairs its own mistakes, and answers in your language. You watch every step on a live
"agent line".

> "شو الأصناف اللي رح تخلص هالأسبوع؟" -> SQL -> table -> a one-line answer.

## How it works

```
Read schema -> Write SQL -> Safety gate -> Run query -> Write answer
                   ^             |              |
                   +-- rewrite --+---- error ---+      (max 3 attempts)
```

| Node | What it does |
|---|---|
| Read schema | Loads table definitions and real category/city values so filters are spelled correctly |
| Write SQL | An LLM writes one SQLite `SELECT` (self-corrects using the previous error) |
| Safety gate | Allows `SELECT`/`WITH` only, rejects stacked statements, adds `LIMIT`. Write attempts are **never retried** |
| Run query | Executes on a read-only connection with a 5 s timeout |
| Write answer | Replies in the language of the question |

### Three independent safety layers
1. **Text gate** (`app/safety.py`): blocks `DROP / DELETE / UPDATE / INSERT / ATTACH / PRAGMA`, comments and `;` tricks.
2. **SQLite authorizer** (`app/db.py`): the engine itself denies anything except reads.
3. **Read-only file connection** (`mode=ro`): the database file cannot be written through this app.

`tests/test_safety.py` proves each layer, including the case where the text gate is bypassed.

## Run on Windows

1. Install Python 3.10 - 3.13 from python.org (tick **Add python.exe to PATH**).
2. Double-click **`run.bat`**. First run creates a virtual environment, installs packages, generates demo data
   and opens `http://127.0.0.1:8000`.

It works immediately in **offline demo mode** (a rule-based engine that understands ~8 warehouse questions).
For free-form questions, connect a real model:

1. Copy `.env.example` to `.env` (run.bat does this for you).
2. Fill one option (Anthropic, OpenAI, or free local **Ollama**) and restart `run.bat`.

The header chips show which engine and model are active.

## Evaluate

Double-click **`eval.bat`** (or `python eval/run_eval.py`). It runs 23 data questions (simple, JOIN,
aggregate, dates) and 3 destructive requests, compares results with gold SQL, and prints accuracy,
retries, and blocked attempts.

| Model | Data questions correct | Unsafe blocked | Needed retry |
|---|---|---|---|
| _fill in after running with your model_ | _x/23_ | _3/3_ | _n_ |

(Offline mode scores low on purpose: it only knows a fixed set of questions.)

## Project layout

```
app/agent.py      LangGraph graph, nodes, routing (falls back to a built-in runner if langgraph is missing)
app/safety.py     SQL gate          app/db.py       read-only access + authorizer
app/llm.py        Anthropic / OpenAI-compatible / offline     app/offline.py  rule-based demo engine
app/main.py       FastAPI (streams agent steps as NDJSON)     app/static/     the web UI
data/generate_data.py   fake but realistic warehouse data (3 warehouses, 33 products, 1,400 movements)
eval/             26-question benchmark       tests/   safety tests
```

## API

- `POST /api/ask` streams one JSON line per agent step, then a final `done` line
- `POST /api/ask/sync` returns the final result as one JSON object
- `GET /api/health`, `GET /api/stats`, `GET /api/schema`

## Docker

```
docker build -t raseef . && docker run -p 8000:8000 --env-file .env raseef
```

Data is synthetic and generated locally. No real company data is used.
=======
# raseef-warehouse-agent
>>>>>>> 8f4acb25e2f872705b3ef975f9a28f8132669806
