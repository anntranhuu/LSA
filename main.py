"""
The backend.

    GET  /            the frontend
    POST /api/decode  the five stage pipeline
    GET  /api/recent  what the database remembers
    GET  /api/health  is this thing alive, and which world is it in

The API key is read from the environment here, on the server, and never
reaches the browser. That is the whole reason this file exists rather than
the page calling the model directly.
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
import pipeline
import store

HERE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="Job Advert Decoder", docs_url="/api/docs")

ENVIRONMENT = os.environ.get("ENVIRONMENT", config.DEFAULT_ENVIRONMENT)

try:
    store.init()
    STORE_READY, STORE_ERROR = True, None
except Exception as err:                      # a broken database must not
    STORE_READY, STORE_ERROR = False, str(err)  # take the whole service down


@app.exception_handler(Exception)
async def anything_unexpected(request: Request, err: Exception):
    """
    Nobody should ever see a blank "Internal Server Error".

    This catches whatever escaped and returns the actual message, so you can
    read it in the browser instead of hunting through the server log. Any
    endpoint you add is covered by this too.
    """
    return JSONResponse({
        "ok": False,
        "error": f"{type(err).__name__}: {err}",
        "where": str(request.url.path),
        "hint": ("If this mentions a missing column, your database file is "
                 "older than your code. Delete the .db file and let it rebuild."),
    }, status_code=500)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "environment": ENVIRONMENT,
        "model": config.MODEL,
        "api_key_configured": bool(os.environ.get("GROQ_API_KEY")),
        "database": store.backend(),
        "database_ready": STORE_READY,
        "database_error": STORE_ERROR,
        "warning": store.warning(),
        "knowledge_files": config.KNOWLEDGE_FILES,
    }


@app.post("/api/decode")
async def decode(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "the body must be JSON"}, status_code=400)

    advert = str(body.get("advert", ""))
    try:
        result = pipeline.run(advert, api_key=os.environ.get("GROQ_API_KEY"))
    except Exception as err:          # last line of defence. A participant
        return JSONResponse({         # must never see a blank 500.
            "ok": False, "answer": None,
            "refusal": f"The service hit an unexpected error: {err}",
            "trace": None, "environment": ENVIRONMENT,
        }, status_code=500)

    if STORE_READY:
        try:
            store.record(result, len(advert), ENVIRONMENT)
        except Exception as err:
            result["store_error"] = str(err)

    result["environment"] = ENVIRONMENT
    return JSONResponse(result, status_code=200 if result["ok"] else 422)


@app.get("/api/recent")
def recent(limit: int = 20):
    if not STORE_READY:
        return JSONResponse({"error": STORE_ERROR}, status_code=503)
    return {"rows": store.recent(min(limit, 100)), "stats": store.stats(),
            "backend": store.backend(), "warning": store.warning()}


@app.get("/")
def home():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")),
          name="static")
