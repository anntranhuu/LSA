"""
=============================================================================
 THE SETTINGS FILE
-----------------------------------------------------------------------------
 Plain English. This is the only file Option A has to change.
 Every value here changes what the running service does.
=============================================================================
"""

# --- Stage 2: the instruction the backend wraps around the user's input ----
SYSTEM_PROMPT = """
You read a job advert and explain it to someone deciding whether to apply.
Answer with JSON only.
"""

# --- Stage 3: retrieval ----------------------------------------------------
# Which files in knowledge/ the service is allowed to look in.
# NOTE: knowledge/mlops.md exists but is NOT in this list.
KNOWLEDGE_FILES = [
    "rag.md",
    "agents.md",
    "cloud.md",
    "evaluation.md",
]

# How many passages to put in front of the model.
PASSAGES = 2

# A passage scoring below this is treated as irrelevant and dropped.
RELEVANCE_FLOOR = 0.08

# --- Stage 5: guardrails ---------------------------------------------------
# Words the answer must never contain.
BANNED_PHRASES = ["as an ai", "i am a language model"]

# The service refuses anything longer than this many characters.
MAX_INPUT_CHARS = 6000

# Refuse to answer if the retrieved passages do not support the answer.
REQUIRE_GROUNDING = False

# --- The model -------------------------------------------------------------
MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0

# --- Which world is this? --------------------------------------------------
# "development" on your laptop, "production" on the cloud.
# The service reads this from the environment, never from code.
DEFAULT_ENVIRONMENT = "development"

# --- Show the five pipeline stages in the response? ------------------------
SHOW_TRACE = True
