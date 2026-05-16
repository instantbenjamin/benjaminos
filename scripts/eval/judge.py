"""LLM-as-judge eval. Classify N voicenotes, judge each, aggregate."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ingest.voicenote_loader import load_obsidian_voicenote
from pharoah.classifier.classifier import classify
from pharoah.classifier.envelope import Envelope

VN = Path("/home/benjaminbot/wiki/voicenotes")


CORPUS = [
    "2026-05-15 Therapy insights on acceptance and fear of emotional extremes.md",
    "2026-05-14 Smoke testing gas grip automation via voice note.md",
    "2026-05-14 Skylarking quote Skylarking, baby.md",
    "2026-05-14 Dr. Craig Wing POV draft reviewed, contract with Craig urgent priority.md",
    "2026-05-13 Birthday ritual, Dutch hormone test mix-up, planning for dad's mobility decline.md",
    "2026-05-07 Powerful Reiki session with Anna felt like unconditional love and acceptance.md",
    "2026-03-22 Refresh Menorca–Lisbon return flight quote for April 11; other legs confirmed.md",
    "2026-03-04 Agree on Civic Hub pitch and dinner intros; keep it casual and flexible.md",
]


def _load_prompt():
    return open("/tmp/judge_prompt.txt").read()


SCORE_TOOL = {
    "name": "score_envelope",
    "description": "Score the envelope on quality dimensions.",
    "input_schema": {
        "type": "object",
        "required": ["category_accuracy","destination_correctness","completeness",
                     "confidence_calibration","privacy_handling","failure_mode"],
        "properties": {
            "category_accuracy": {"type": "integer", "minimum": 1, "maximum": 5},
            "destination_correctness": {"type": "integer", "minimum": 1, "maximum": 5},
            "completeness": {"type": "integer", "minimum": 1, "maximum": 5},
            "confidence_calibration": {"type": "integer", "minimum": 1, "maximum": 5},
            "privacy_handling": {"type": "integer", "minimum": 1, "maximum": 5},
            "failure_mode": {"type": "string"},
        },
    },
}


def judge(transcript: str, envelope: Envelope) -> dict:
    """Call Claude with judge prompt + score_envelope tool."""
    import anthropic
    client = anthropic.Anthropic()
    env_dict = envelope.model_dump(mode="json")
    for k in ["envelope_id", "classified_at", "classifier_model",
              "classifier_version", "raw_classifier_output"]:
        env_dict.pop(k, None)
    user_msg = (f"## Transcript\n\n{transcript[:6000]}\n\n"
                f"## Envelope\n\n{json.dumps(env_dict, indent=2, default=str)}")
    return _call(client, user_msg)


def _call(client, user_msg: str) -> dict:
    resp = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=1024, temperature=0,
        system=_load_prompt(), tools=[SCORE_TOOL],
        tool_choice={"type": "tool", "name": "score_envelope"},
        messages=[{"role": "user", "content": user_msg}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    raise RuntimeError("No tool_use block")


def main():
    results = []
    for i, fname in enumerate(CORPUS):
        path = VN / fname
        if not path.exists():
            print(f"[{i}] MISSING: {fname[:60]}")
            continue
        print(f"[{i}] {fname[:60]}...")
        try:
            source = load_obsidian_voicenote(path)
            env = classify(source)
            score = judge(source.transcript, env)
            results.append({"file": fname, "n_items": len(env.items),
                            "score": score, "envelope": env.model_dump(mode="json")})
            mean = sum(score[k] for k in DIMS) / len(DIMS)
            print(f"     items={len(env.items)} mean={mean:.2f}")
        except Exception as e:
            print(f"     ERROR: {type(e).__name__}: {str(e)[:120]}")
    _report(results)


DIMS = ["category_accuracy", "destination_correctness", "completeness",
        "confidence_calibration", "privacy_handling"]


def _report(results):
    if not results:
        print("NO RESULTS"); return
    print("\n=== AGGREGATE ===")
    for d in DIMS:
        avg = sum(r["score"][d] for r in results) / len(results)
        print(f"  {d:25s} {avg:.2f}")
    overall = sum(sum(r["score"][k] for k in DIMS)/len(DIMS) for r in results)/len(results)
    print(f"  {'OVERALL':25s} {overall:.2f}")

    print("\n=== PER-FILE ===")
    for r in results:
        m = sum(r["score"][k] for k in DIMS) / len(DIMS)
        print(f"  {m:.2f} | items={r['n_items']} | {r['file'][:55]}")
        print(f"       failure: {r['score']['failure_mode'][:200]}")
    out = Path("/tmp/eval_results.json")
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nFull results -> {out}")


if __name__ == "__main__":
    main()
