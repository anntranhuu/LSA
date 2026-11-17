"""
The five stages.

    1  receive        the frontend sent something, is it usable
    2  retrieve       find the passages that might help
    3  build_prompt   wrap the input in an instruction
    4  call_model     someone else's model, over an API
    5  check          guardrails, then send it back

Each stage is its own function that takes a state and returns a state plus a
record of what it did. The record is what the trace shows, so the diagram from
the session is literally what comes back over the wire.
"""

import json
import math
import os
import re
import time
import urllib.error
import urllib.request

import config

HERE = os.path.dirname(os.path.abspath(__file__))
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "for",
    "from", "has", "have", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "their", "them", "then", "there", "these", "they", "this", "to",
    "was", "were", "what", "when", "which", "who", "why", "will", "with",
    "you", "your", "we", "our", "us", "do", "does", "how",
}


def terms(text):
    words = re.sub(r"[^a-z0-9\s-]", " ", str(text).lower()).split()
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


# ---------------------------------------------------------------------------
#  knowledge base
# ---------------------------------------------------------------------------
def load_knowledge(files=None):
    """Read the allowed files and cut them into passages at '## ' headings."""
    files = files if files is not None else config.KNOWLEDGE_FILES
    passages = []
    for name in files:
        path = os.path.join(HERE, "knowledge", name)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        text = re.sub(r"^#\s+.*\n", "", text, count=1)
        parts = re.split(r"^##\s+(.+)$", text, flags=re.MULTILINE)
        for i in range(1, len(parts), 2):
            heading = parts[i].strip()
            body = " ".join(parts[i + 1].split()) if i + 1 < len(parts) else ""
            if body:
                passages.append({
                    "id": f"{name.replace('.md','')}#{len(passages)}",
                    "file": name,
                    "heading": heading,
                    "text": f"{heading}. {body}",
                })
    return passages


# ---------------------------------------------------------------------------
#  stage 1 of 5
# ---------------------------------------------------------------------------
def receive(state):
    t0 = time.perf_counter()
    text = str(state.get("advert", "")).strip()
    ok, detail = True, f"{len(text)} characters"

    if not text:
        ok, detail = False, "nothing was sent"
    elif len(text) > config.MAX_INPUT_CHARS:
        ok, detail = False, (f"{len(text)} characters, the limit is "
                             f"{config.MAX_INPUT_CHARS}")

    state["advert"] = text
    state["ok"] = ok
    if not ok:
        state["refusal"] = "That input cannot be processed."
    return state, {"stage": 1, "name": "receive", "ok": ok, "detail": detail,
                   "ms": round((time.perf_counter() - t0) * 1000, 1)}


# ---------------------------------------------------------------------------
#  stage 2 of 5
# ---------------------------------------------------------------------------
def score_passage(query_terms, passage_terms):
    """Shared words, damped by passage length so long passages cannot win on size."""
    q, p = set(query_terms), set(passage_terms)
    if not q or not p:
        return 0.0
    return len(q & p) / math.sqrt(len(p))


def retrieve(state):
    t0 = time.perf_counter()
    passages = load_knowledge()
    q = terms(state["advert"])

    scored = []
    for p in passages:
        s = score_passage(q, terms(p["text"]))
        scored.append({**p, "score": round(s, 4)})

    scored.sort(key=lambda x: (-x["score"], x["id"]))
    kept = [p for p in scored if p["score"] > config.RELEVANCE_FLOOR][:config.PASSAGES]

    state["passages"] = kept
    return state, {
        "stage": 2, "name": "retrieve", "ok": True,
        "detail": (f"{len(kept)} of {len(passages)} passages above "
                   f"{config.RELEVANCE_FLOOR}"),
        "passages": [{"id": p["id"], "heading": p["heading"], "score": p["score"]}
                     for p in kept],
        "ms": round((time.perf_counter() - t0) * 1000, 1),
    }


# ---------------------------------------------------------------------------
#  stage 3 of 5
# ---------------------------------------------------------------------------
def build_prompt(state):
    t0 = time.perf_counter()
    notes = "\n\n".join(f"[{p['id']}] {p['text']}" for p in state["passages"])

    system = config.SYSTEM_PROMPT.strip() + "\n\n" + "\n".join([
        "Return exactly these fields:",
        '  role            the job title in plain words',
        '  seniority       one of junior, mid, senior',
        '  work_mode       one of remote, hybrid, onsite, unknown',
        '  key_skills      a list of the skills the advert requires',
        '  jargon_explained  a short plain-English note on the technical terms,',
        '                    using ONLY the reference notes below',
    ])
    if notes:
        system += "\n\nREFERENCE NOTES:\n" + notes
    else:
        system += ("\n\nThere are no reference notes. Leave jargon_explained "
                   "empty rather than inventing an explanation.")

    state["system"] = system
    state["user"] = f"Job advert:\n\n{state['advert']}\n\nAnswer with JSON only."
    chars = len(system) + len(state["user"])
    return state, {
        "stage": 3, "name": "build_prompt", "ok": True,
        "detail": f"{chars} characters, about {math.ceil(chars/4)} tokens",
        "chars": chars, "estimated_tokens": math.ceil(chars / 4),
        "ms": round((time.perf_counter() - t0) * 1000, 1),
    }


# ---------------------------------------------------------------------------
#  stage 4 of 5
# ---------------------------------------------------------------------------
_SENIOR = r"\b(senior|lead|principal|staff|head of)\b"
_JUNIOR = r"\b(junior|graduate|intern|trainee|no experience)\b"
_SKILLS = ["Python", "SQL", "Excel", "R", "Go", "Rust", "TypeScript", "React",
           "PyTorch", "Spark", "Kubernetes", "Docker", "AWS", "Airflow", "dbt",
           "Power BI", "LangChain", "CUDA", "NLP", "Statistics"]


def demo_model(state):
    """
    Not a model. Rules, so the service runs before anyone has an API key.

    It is deliberately mediocre and it says so in its own output.
    """
    low = state["advert"].lower()

    years = None
    m = re.search(r"\b(\d+)\s*(?:\+|plus)?\s*years", low)
    if m:
        years = int(m.group(1))

    if re.search(_JUNIOR, low):
        seniority = "junior"
    elif re.search(_SENIOR, low) or (years is not None and years >= 6):
        seniority = "senior"
    else:
        seniority = "mid"

    if re.search(r"\b(fully remote|remote first|remote|no offices)\b", low):
        work_mode = "remote"
    elif re.search(r"\b(hybrid|days a week|two days|three days)\b", low):
        work_mode = "hybrid"
    elif re.search(r"\b(in the office|on site|onsite|five days|based at)\b", low):
        work_mode = "onsite"
    else:
        work_mode = "unknown"

    found = [s for s in _SKILLS
             if re.search(rf"(?<![A-Za-z]){re.escape(s.lower())}(?![A-Za-z])", low)]

    jargon = ""
    if state["passages"]:
        first = state["passages"][0]
        jargon = (f"[DEMO MODE] From the notes on {first['heading']}: "
                  + " ".join(first["text"].split()[:28]) + " ...")

    return {
        "role": (re.sub(r"\s+", " ",
                        re.sub(_SENIOR, "", low.split(".")[0])).strip()[:60]
                 .title() or "Unknown"),
        "seniority": seniority,
        "work_mode": work_mode,
        "key_skills": found[:5],
        "jargon_explained": jargon,
    }


def parse_reply(text):
    """Get JSON out of whatever came back. Returns (data, problem)."""
    if not text or not text.strip():
        return None, "empty reply"
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        pass
    brace = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0)), "had text around the JSON"
        except json.JSONDecodeError:
            return None, "braces found but contents were not valid JSON"
    return None, "no JSON in the reply"


class ModelUnavailable(RuntimeError):
    """The model could not be reached. Not the participant's fault, and not
    a reason to return a blank 500 with no explanation."""


def call_groq(system, user, api_key, retries=3):
    payload = {
        "model": config.MODEL,
        "temperature": config.TEMPERATURE,
        "max_tokens": 2000,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
    GROQ_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "python-groq-client/1.0"
    }
)
    for _ in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return (body["choices"][0]["message"]["content"],
                        body.get("usage", {}))
        except urllib.error.HTTPError as err:
            if err.code == 429:
                time.sleep(float(err.headers.get("retry-after", 5)) + 1)
                continue
            if err.code in (401, 403):
                raise ModelUnavailable(
                    f"the model API rejected the key ({err.code}). Check "
                    "GROQ_API_KEY is correct and has not been revoked."
                ) from None
            raise ModelUnavailable(
                f"the model API returned {err.code}") from None
        except urllib.error.URLError as err:
            raise ModelUnavailable(
                f"could not reach the model API: {err.reason}. Check your "
                "network, or run without a key to use demo mode."
            ) from None
        except (TimeoutError, OSError) as err:
            raise ModelUnavailable(
                f"the model API did not respond: {err}") from None
    raise ModelUnavailable("rate limited repeatedly, wait a minute and retry")


def call_model(state, api_key=None):
    t0 = time.perf_counter()
    usage, problem = {}, None

    if api_key:
        mode = "groq"
        try:
            text, usage = call_groq(state["system"], state["user"], api_key)
        except ModelUnavailable as err:
            state["ok"] = False
            state["refusal"] = str(err)
            return state, {
                "stage": 4, "name": "call_model", "ok": False,
                "detail": str(err), "mode": mode, "usage": {},
                "ms": round((time.perf_counter() - t0) * 1000, 1),
            }
        data, problem = parse_reply(text)
        if data is None:
            state["ok"] = False
            state["refusal"] = "The model returned something unreadable."
            data = {}
    else:
        data, mode = demo_model(state), "demo"

    state["answer"] = data
    return state, {
        "stage": 4, "name": "call_model", "ok": state.get("ok", True),
        "detail": (f"{mode}" + (f", {usage.get('total_tokens')} tokens"
                                if usage.get("total_tokens") else "")
                   + (f", {problem}" if problem else "")),
        "mode": mode, "usage": usage,
        "ms": round((time.perf_counter() - t0) * 1000, 1),
    }


# ---------------------------------------------------------------------------
#  stage 5 of 5
# ---------------------------------------------------------------------------
def check(state):
    t0 = time.perf_counter()
    answer = state.get("answer") or {}
    failures = []

    blob = json.dumps(answer).lower()
    for phrase in config.BANNED_PHRASES:
        if phrase.lower() in blob:
            failures.append(f"banned phrase: {phrase}")

    allowed_sen = {"junior", "mid", "senior"}
    if answer.get("seniority") not in allowed_sen:
        failures.append(f"seniority {answer.get('seniority')!r} is not allowed")

    allowed_wm = {"remote", "hybrid", "onsite", "unknown"}
    if answer.get("work_mode") not in allowed_wm:
        failures.append(f"work_mode {answer.get('work_mode')!r} is not allowed")

    if config.REQUIRE_GROUNDING and answer.get("jargon_explained"):
        notes = " ".join(p["text"].lower() for p in state["passages"])
        words = {w for w in terms(answer["jargon_explained"]) if len(w) > 4}
        if words:
            hits = sum(1 for w in words if w in notes)
            if hits / len(words) < 0.3:
                failures.append(
                    f"jargon_explained is not grounded in the retrieved notes "
                    f"({round(hits/len(words)*100)}% of its words appear there)")

    ok = not failures
    if not ok:
        state["ok"] = False
        state["refusal"] = "The answer did not pass the checks."
    return state, {"stage": 5, "name": "check", "ok": ok,
                   "detail": "all checks passed" if ok else "; ".join(failures),
                   "failures": failures,
                   "ms": round((time.perf_counter() - t0) * 1000, 1)}


# ---------------------------------------------------------------------------
#  the whole pipeline
# ---------------------------------------------------------------------------
def run(advert, api_key=None):
    state, trace = {"advert": advert, "ok": True}, []
    started = time.perf_counter()

    for step in (receive, retrieve, build_prompt):
        state, rec = step(state)
        trace.append(rec)
        if not state["ok"]:
            return _result(state, trace, started)

    state, rec = call_model(state, api_key)
    trace.append(rec)
    if not state["ok"]:
        return _result(state, trace, started)

    state, rec = check(state)
    trace.append(rec)
    return _result(state, trace, started)


def _result(state, trace, started):
    return {
        "ok": state["ok"],
        "answer": state.get("answer") if state["ok"] else None,
        "refusal": None if state["ok"] else state.get("refusal"),
        "trace": trace if config.SHOW_TRACE else None,
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
    }
