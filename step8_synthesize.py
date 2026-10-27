import json
import re
import sqlite3

from step4_prepare_text import load_messages, make_chunks
from step5_extract import extract_chunk, fake_model, parse_json

SYNTH_SYSTEM = """You receive structured extractions from a full chat: events, actions, and unclear items, each with message IDs.
Chunks overlap at their edges, so merge duplicate items. Write a cautious analysis based only on this material.

Return only JSON:
{
  "timeline": [{"when": "...", "what": "...", "evidence": ["msg_3"]}],
  "roles": [{
    "person": "...",
    "role": "e.g. initiator, decision-maker, mediator, objector, passive participant",
    "confidence": "low|medium|high",
    "reasoning": "...",
    "evidence": ["msg_5", "msg_9"],
    "counter_evidence": ["msg_20"]
  }],
  "how_it_unfolded": "short narrative, with message IDs in brackets like [msg_5]",
  "limitations": ["what this chat cannot tell us"]
}

Rules:
- Word findings as "the messages suggest...", never as verdicts.
- Do not assign blame or judge who was right.
- A role needs at least two supporting actions to be rated above low.
- Always look for counter-evidence and report it.
- Do not treat message volume as influence.
- Note gaps: missing time periods, offline conversations, unclear items.
- Cite message IDs for every claim."""

# Pretend synthesis reply, flawed on purpose:
# - a timeline entry citing a message that does not exist
# - a role for a person who is not in the chat
# - a "high" confidence role backed by only one message
FAKE_SYNTH_REPLY = """{
  "timeline": [
    {"when": "14:05", "what": "Alice raised the idea of booking the cabin", "evidence": ["msg_1"]},
    {"when": "later", "what": "A deposit was paid", "evidence": ["msg_99"]}
  ],
  "roles": [
    {"person": "Alice", "role": "initiator", "confidence": "high",
     "reasoning": "The messages suggest Alice started the discussion.",
     "evidence": ["msg_1"], "counter_evidence": []},
    {"person": "Carol", "role": "decision-maker", "confidence": "medium",
     "reasoning": "The messages suggest Carol gave the final go-ahead after Bob agreed.",
     "evidence": ["msg_2", "msg_3"], "counter_evidence": []},
    {"person": "Dave", "role": "mediator", "confidence": "low",
     "reasoning": "Appears to mediate.", "evidence": ["msg_1"], "counter_evidence": []}
  ],
  "how_it_unfolded": "The messages suggest Alice raised the idea [msg_1], Bob agreed [msg_2], and Carol gave the go-ahead [msg_3].",
  "limitations": ["Only a few messages are available.", "Offline conversations are not visible."]
}"""


def fake_synth_model(system, user):
    return FAKE_SYNTH_REPLY


def merge_results(results):
    """Combine per-chunk results into one, dropping duplicates caused by chunk overlap."""
    events, actions, unclear = {}, {}, []
    for r in results:
        for ev in r["events"]:
            events.setdefault(ev["summary"], ev)  # keep the first one with this summary
        for ac in r["actions"]:
            actions.setdefault((ac["person"], ac["summary"]), ac)
        unclear.extend(r["unclear"])
    return {"events": list(events.values()), "actions": list(actions.values()), "unclear": unclear}


def build_synthesis_prompt(people, merged):
    return f"Participants: {', '.join(people)}\n\nExtractions:\n{json.dumps(merged, ensure_ascii=False)}"


def validate_synthesis(data, known_refs, people):
    problems = []

    timeline = []
    for t in data.get("timeline", []):
        refs = [r for r in t.get("evidence", []) if r in known_refs]
        if not refs:
            problems.append(f"Dropped timeline entry with no valid evidence: {t.get('what')!r}")
            continue
        t["evidence"] = refs
        timeline.append(t)

    roles = []
    for r in data.get("roles", []):
        if r.get("person") not in people:
            problems.append(f"Dropped role for someone not in the chat: {r.get('person')!r}")
            continue
        support = [x for x in r.get("evidence", []) if x in known_refs]
        counter = [x for x in r.get("counter_evidence", []) if x in known_refs]
        confidence = r.get("confidence")
        if confidence not in ("low", "medium", "high"):
            confidence = "low"
        if len(support) < 2 and confidence != "low":
            problems.append(
                f"Lowered {r['person']}'s confidence from {confidence} to low "
                f"(only {len(support)} supporting message)"
            )
            confidence = "low"
        roles.append({
            "person": r["person"], "role": r.get("role", "unknown"),
            "confidence": confidence, "reasoning": r.get("reasoning", ""),
            "evidence": support, "counter_evidence": counter,
        })

    narrative = data.get("how_it_unfolded", "")
    bad = sorted(set(re.findall(r"msg_\d+", narrative)) - known_refs)
    if bad:
        problems.append(f"Narrative cites messages that do not exist: {bad}")

    clean = {
        "timeline": timeline, "roles": roles, "how_it_unfolded": narrative,
        "limitations": data.get("limitations", []),
    }
    return clean, problems


def synthesize(model_fn, people, results, known_refs):
    merged = merge_results(results)
    reply = model_fn(SYNTH_SYSTEM, build_synthesis_prompt(people, merged))
    return validate_synthesis(parse_json(reply), known_refs, people)


if __name__ == "__main__":
    conn = sqlite3.connect("chat.db")
    messages = load_messages(conn, chat_id=1)
    people = sorted({m["sender"] for m in messages})
    known_refs = {m["ref"] for m in messages}

    chunk = make_chunks(messages, size=4, overlap=1)[0]
    extraction, _ = extract_chunk(fake_model, people, chunk)

    analysis, problems = synthesize(fake_synth_model, people, [extraction], known_refs)

    print("TIMELINE")
    for t in analysis["timeline"]:
        print(f"  {t['when']}: {t['what']}  {t['evidence']}")
    print("\nROLES")
    for r in analysis["roles"]:
        print(f"  {r['person']}: {r['role']} ({r['confidence']} confidence)  evidence={r['evidence']}")
    print("\nNARRATIVE\n ", analysis["how_it_unfolded"])
    print("\nLIMITATIONS")
    for l in analysis["limitations"]:
        print("  -", l)
    print("\nPROBLEMS FOUND")
    for p in problems:
        print("  -", p)
