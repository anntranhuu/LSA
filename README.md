# Job Advert Decoder

A small production service. Paste a job advert, get back the facts plus a
plain-English explanation of the jargon, and see all five pipeline stages that
produced it.

This is the diagram from the session, running.

```
  you type          the backend          the backend        someone else's       the backend
  something    ->   finds relevant  ->   wraps it in   ->   model, over     ->   checks the
                    notes                an instruction     an API               answer
  1 receive         2 retrieve           3 build_prompt     4 call_model         5 check
```

## Run it

```bash
pip install -r requirements.txt
uvicorn main:app --reload        # then open http://localhost:8000
python -m unittest discover -s tests   # 52 tests
```

It works with **no API key**. Without one it answers from rules instead of a
model and labels itself DEMO MODE, so you can see everything working before
you sign up for anything.

## The parts, and which is which

| File | Which part of the session it is |
|---|---|
| `static/` | **Frontend**. Runs on the user's device. Holds no secrets |
| `main.py` | **Backend** and the **API**. The contract between the two |
| `pipeline.py` | The five stages |
| `store.py` | **Database**. SQLite locally, Postgres in the cloud |
| `config.py` | Every setting, in plain English |
| `knowledge/` | What the retrieval stage reads |
| `.github/workflows/ci.yml` | **CI**. Tested automatically on every push |
| `vercel.json`, `render.yaml` | **Deployment** |

## Environment variables

Nothing secret belongs in the code. The service reads these from the
environment:

| Variable | What happens without it |
|---|---|
| `GROQ_API_KEY` | Demo mode, using rules instead of a model |
| `ENVIRONMENT` | Assumes `development` |
| `DATABASE_URL` | Uses a SQLite file, which a cloud host throws away |

## The one that catches everyone

A SQLite file works perfectly on your laptop and loses every row on a free
cloud host, because the container is thrown away between requests. Deploy with
`ENVIRONMENT=production` and no `DATABASE_URL` and the service tells you so on
`/api/health`. That warning is not a bug. It is the lesson.

## Deploy

Either host works and neither needs a payment card.

**Vercel**: push to GitHub, import the repo, add `GROQ_API_KEY` under
Environment Variables. The Python runtime detects FastAPI from
`requirements.txt` and uses the `app` in `main.py`.

**Render**: push to GitHub, New Web Service, pick the repo. `render.yaml`
already has the build and start commands. Free services sleep after 15 minutes
of no traffic and take about a minute to wake up.

Afterwards open `/api/health` on your live URL. If it does not say
`"api_key_configured": true`, the variable did not reach the build. Add it and
redeploy.

## Your key

Goes in `.env` locally, which is gitignored, or in the host's Environment
Variables. Never in a file you commit, never in a screenshot, never in the
group chat. CI fails the build if it finds one.
