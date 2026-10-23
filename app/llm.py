"""LLM access: Anthropic, any OpenAI-compatible endpoint (OpenAI, Ollama, Groq...), or the offline engine."""
import os
import re
from datetime import date

from . import config, offline

SQL_SYSTEM = """You are a careful data analyst writing SQLite queries for a warehouse database.
Rules:
- Output ONE SQLite SELECT statement and nothing else (no explanation, no markdown).
- Use only the tables and columns in the schema. Never invent columns.
- Product names exist in English (name) and Arabic (name_ar). Questions may be Arabic or English.
- 'this week' = last 7 days, 'this month' / 'last month' = last 30 days.
- Prefer explicit JOINs, readable aliases, and ORDER BY for ranked answers.
Today's date: {today}

Schema:
{schema}"""

ANSWER_SYSTEM = """You turn SQL results into a short answer for a warehouse manager.
Reply in the same language as the question (Arabic or English), 1-3 sentences, plain text, no markdown.
State the key numbers and names. Do not mention SQL. If there are no rows, say nothing matched."""


def detect_lang(text: str) -> str:
    return "ar" if re.search(r"[\u0600-\u06FF]", text) else "en"


def _chat(system: str, user: str, max_tokens: int = 700) -> str:
    import httpx  # imported lazily: offline mode needs no network library
    p = config.provider()
    if p == "anthropic":
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": config.model_name(), "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=60)
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])
    if p == "openai":
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        r = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', 'none')}"},
            json={"model": config.model_name(), "max_tokens": max_tokens, "temperature": 0,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    raise RuntimeError("no LLM provider configured")


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    if m:
        text = m.group(1)
    m = re.search(r"\b(select|with)\b", text, re.I)
    return text[m.start():].strip() if m else text.strip()


def generate_sql(question: str, schema: str, prev_sql: str = "", error: str = "") -> str:
    if config.provider() == "offline":
        return offline.sql_for(question) or ""
    user = f"Question: {question}"
    if prev_sql and error:
        user += f"\n\nYour previous query:\n{prev_sql}\n\nfailed with: {error}\nWrite a corrected query."
    out = _chat(SQL_SYSTEM.format(today=date.today().isoformat(), schema=schema), user)
    return extract_sql(out)


MESSAGES = {
    "rejected": {"ar": "رفضت التنفيذ: {reason}. النظام للقراءة فقط وما تغيّر شي بالبيانات.",
                 "en": "Refused: {reason}. This system is read-only and nothing in the data was changed."},
    "failed": {"ar": "ما قدرت أجيب جواب صحيح بعد {n} محاولات. آخر خطأ: {reason}",
               "en": "I could not produce a working query after {n} attempts. Last error: {reason}"},
    "unsupported": {"ar": "هالسؤال خارج اللي بفهمه بدون نموذج لغوي. أضف مفتاح API بملف .env وجرب مرة ثانية.",
                    "en": "That question is outside what the offline engine understands. Add an API key in .env and retry."},
}


def _fmt(v):
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _template_answer(columns, rows, lang):
    if not rows:
        return "ما لقيت نتائج مطابقة." if lang == "ar" else "No matching rows."
    if len(rows) == 1 and len(columns) == 1:
        return (f"النتيجة: {_fmt(rows[0][0])}" if lang == "ar" else f"Result: {_fmt(rows[0][0])}")
    first = " / ".join(_fmt(v) for v in rows[0])
    if lang == "ar":
        return f"لقيت {len(rows)} نتيجة. الأولى: {first}. التفاصيل بالجدول تحت."
    return f"Found {len(rows)} rows. First: {first}. Full table below."


def write_answer(question, columns, rows, status, lang, reason="", attempts=0) -> str:
    if status in MESSAGES:
        return MESSAGES[status][lang].format(reason=reason, n=attempts)
    if config.provider() == "offline":
        return _template_answer(columns, rows, lang)
    try:
        sample = "\n".join(" | ".join(_fmt(v) for v in r) for r in rows[:20])
        user = (f"Question: {question}\nColumns: {', '.join(columns)}\nRows ({len(rows)} total, first 20):\n{sample}")
        return _chat(ANSWER_SYSTEM, user, 300).strip()
    except Exception:
        return _template_answer(columns, rows, lang)
