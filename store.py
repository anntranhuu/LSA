"""
Where the service remembers things.

Two backends, chosen by the environment and not by the code:

    DATABASE_URL is set   ->  Postgres, which survives a deploy
    DATABASE_URL is unset ->  a SQLite file, which does not

That second line is the whole lesson. A SQLite file works perfectly on your
laptop and silently loses every row on a platform that throws the container
away between requests. The service warns you when it spots that combination.
"""

import json
import os
import sqlite3
import time

SQLITE_PATH = os.environ.get("SQLITE_PATH",
                             os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "requests.db"))

CREATE_SQLITE = """
CREATE TABLE IF NOT EXISTS requests (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL    NOT NULL,
  environment TEXT   NOT NULL,
  advert_chars INTEGER NOT NULL,
  ok         INTEGER NOT NULL,
  mode       TEXT,
  seniority  TEXT,
  work_mode  TEXT,
  total_ms   REAL,
  tokens     INTEGER,
  trace      TEXT
)
"""

CREATE_PG = CREATE_SQLITE.replace(
    "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
).replace("REAL", "DOUBLE PRECISION").replace("ok         INTEGER", "ok BOOLEAN")


def backend():
    return "postgres" if os.environ.get("DATABASE_URL") else "sqlite"


def warning():
    """The one that catches everybody on their first deploy."""
    env = os.environ.get("ENVIRONMENT", "development")
    if env == "production" and backend() == "sqlite":
        return ("Running in production on a SQLite file. On a serverless or "
                "free-tier host this file is thrown away, so every row you "
                "write here will be gone. Set DATABASE_URL to a hosted "
                "database.")
    return None


def _pg():
    import psycopg  # only imported when DATABASE_URL is set
    return psycopg.connect(os.environ["DATABASE_URL"])


def init():
    if backend() == "postgres":
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(CREATE_PG)
            conn.commit()
    else:
        with sqlite3.connect(SQLITE_PATH) as conn:
            conn.execute(CREATE_SQLITE)
            conn.commit()


def record(result, advert_chars, environment):
    trace = result.get("trace") or []
    call = next((t for t in trace if t["name"] == "call_model"), {})
    answer = result.get("answer") or {}
    row = (time.time(), environment, advert_chars, bool(result["ok"]),
           call.get("mode"), answer.get("seniority"), answer.get("work_mode"),
           result.get("total_ms"),
           (call.get("usage") or {}).get("total_tokens"),
           json.dumps(trace))

    if backend() == "postgres":
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO requests (created_at, environment, advert_chars,"
                " ok, mode, seniority, work_mode, total_ms, tokens, trace)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", row)
            conn.commit()
    else:
        with sqlite3.connect(SQLITE_PATH) as conn:
            conn.execute(
                "INSERT INTO requests (created_at, environment, advert_chars,"
                " ok, mode, seniority, work_mode, total_ms, tokens, trace)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)", row)
            conn.commit()


def _safe(fn, fallback):
    """The database is somewhere to write things down, not a reason for the
    whole service to fall over when it disappears underneath us."""
    try:
        return fn()
    except Exception:
        return fallback


def recent(limit=20):
    cols = ("id, created_at, environment, advert_chars, ok, mode, seniority,"
            " work_mode, total_ms, tokens")
    init()                      # the file may have been thrown away
    if backend() == "postgres":
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {cols} FROM requests ORDER BY id DESC LIMIT %s",
                        (limit,))
            rows, names = cur.fetchall(), [d[0] for d in cur.description]
    else:
        with sqlite3.connect(SQLITE_PATH) as conn:
            cur = conn.execute(
                f"SELECT {cols} FROM requests ORDER BY id DESC LIMIT ?", (limit,))
            rows, names = cur.fetchall(), [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in rows]


def stats():
    init()
    if backend() == "postgres":
        with _pg() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), AVG(total_ms), SUM(tokens) FROM requests")
            n, avg, tok = cur.fetchone()
    else:
        with sqlite3.connect(SQLITE_PATH) as conn:
            n, avg, tok = conn.execute(
                "SELECT COUNT(*), AVG(total_ms), SUM(tokens) FROM requests"
            ).fetchone()
    return {"requests": n or 0,
            "mean_ms": round(avg, 1) if avg else None,
            "total_tokens": tok or 0}
