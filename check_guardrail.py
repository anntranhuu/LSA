"""
Does the grounding guardrail actually work?

Option C task 12. Run this before you trust the guardrail, because a check you
have not tested is not a check, it is a hope.

    python3 check_guardrail.py

Five explanations, all judged against the same retrieved note. Two of the five
answers are wrong, and finding out which two is the exercise.
"""

import importlib
import config
import pipeline as P

NOTE = [{
    "id": "rag#0", "heading": "What RAG means",
    "text": ("What RAG means. RAG stands for retrieval augmented generation. "
             "The model does not know about your documents. RAG is the step "
             "where you find the relevant bits of your own material first, "
             "and put them in front of the model before you ask the question."),
}]

CASES = [
    ("copied almost word for word from the note",
     "RAG stands for retrieval augmented generation, the step where you find "
     "relevant bits of your material and put them in front of the model."),
    ("correct, but written in the explainer's own words",
     "This role wants someone who can feed a language model the right "
     "background information from company files before it answers."),
    ("plausible sounding and entirely invented",
     "This employer requires expertise in quantised adapter tuning and "
     "reinforcement alignment across multimodal encoder stacks."),
    ("half true, half invented",
     "RAG means retrieval augmented generation, and it requires expertise in "
     "quantised adapter tuning across multimodal stacks."),
    ("empty",
     ""),
]


def main():
    config.REQUIRE_GROUNDING = True
    importlib.reload(P)
    P.config = config

    print(f"{'case':<52}{'verdict':<10}why")
    print("-" * 100)
    for label, explanation in CASES:
        state = {"ok": True, "passages": NOTE, "answer": {
            "role": "AI Engineer", "seniority": "mid", "work_mode": "remote",
            "key_skills": ["Python"], "jargon_explained": explanation}}
        _, rec = P.check(state)
        print(f"{label:<52}{'passed' if rec['ok'] else 'REFUSED':<10}"
              f"{rec['detail'][:40]}")

    print()
    print("Now decide, for each row, whether the guardrail was right.")
    print()
    print("Two of them are wrong. One is a false positive: a correct answer")
    print("thrown away. One is a false negative: an invention let through.")
    print("Both matter, and they matter differently.")
    print()
    print("The threshold lives in check() in pipeline.py, as minOverlap.")
    print("Change it and run this again. You will find you cannot fix one")
    print("failure without making the other worse, which is the whole point.")


if __name__ == "__main__":
    main()
