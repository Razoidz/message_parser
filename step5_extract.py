import json
import sqlite3

from step4_prepare_text import build_prompt, load_messages, make_chunks

ACTION_TYPES = {
    "proposed", "decided", "agreed", "disagreed", "asked", "answered",
    "committed", "deflected", "escalated", "went_quiet", "other",
}

EXTRACT_SYSTEM = """You analyze a chunk of a chat transcript. Each line is: [message_id] timestamp sender: text.
Extract only what the messages directly show. Do not infer motives or assign roles.

Return only JSON:
{
  "events": [{"summary": "...", "participants": ["..."], "evidence": ["msg_12"]}],
  "actions": [{"person": "...", "type": "proposed|decided|agreed|disagreed|asked|answered|committed|deflected|escalated|went_quiet|other", "summary": "...", "evidence": ["msg_14"]}],
  "unclear": ["anything ambiguous, sarcastic, or referring to things outside the chat"]
}

Rules:
- Every event and action needs at least one message ID in evidence.
- Describe what was said or done, not what it means about the person.
- If a message is ambiguous, put it in "unclear" instead of guessing.
- Names must match the participant list exactly."""

# A pretend model reply. It contains two realistic flaws on purpose:
# 1) it is wrapped in ```json fences, 2) one event cites a message and a person that do not exist.
FAKE_REPLY = """```json
{
  "events": [
    {"summary": "The group discussed booking a cabin", "participants": ["Alice", "Bob"], "evidence": ["msg_1", "msg_2"]},
    {"summary": "Someone paid a deposit", "participants": ["Dave"], "evidence": ["msg_99"]}
  ],
  "actions": [
    {"person": "Alice", "type": "proposed", "summary": "Proposed booking the cabin and suggested Friday", "evidence": ["msg_1"]},
    {"person": "Carol", "type": "agreed", "summary": "Agreed to go ahead", "evidence": ["msg_3"]}
  ],
  "unclear": []
}
```"""


def fake_model(system, user):
    return FAKE_REPLY


def parse_json(text):
    """Turn the model's reply into Python data, removing ``` fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]    # drop the first line (```json)
        text = text.rsplit("```", 1)[0]  # drop the closing fence
    return json.loads(text)


def validate(data, known_refs, people):
    """Keep only items that cite real messages and real people. Report what was dropped."""
    clean = {"events": [], "actions": [], "unclear": data.get("unclear", [])}
    problems = []

    for ev in data.get("events", []):
        refs = [r for r in ev.get("evidence", []) if r in known_refs]
        if not refs:
            problems.append(f"Dropped event with no valid evidence: {ev.get('summary')!r}")
            continue
        ev["evidence"] = refs
        ev["participants"] = [p for p in ev.get("participants", []) if p in people]
        clean["events"].append(ev)

    for ac in data.get("actions", []):
        refs = [r for r in ac.get("evidence", []) if r in known_refs]
        if ac.get("person") not in people or not refs:
            problems.append(f"Dropped action: {ac.get('summary')!r}")
            continue
        if ac.get("type") not in ACTION_TYPES:
            ac["type"] = "other"
        ac["evidence"] = refs
        clean["actions"].append(ac)

    return clean, problems


def extract_chunk(model_fn, people, chunk):
    prompt = build_prompt(people, chunk)
    reply = model_fn(EXTRACT_SYSTEM, prompt)
    data = parse_json(reply)
    known_refs = {m["ref"] for m in chunk}
    return validate(data, known_refs, people)


if __name__ == "__main__":
    conn = sqlite3.connect("chat.db")
    messages = load_messages(conn, chat_id=1)
    people = sorted({m["sender"] for m in messages})
    chunk = make_chunks(messages, size=4, overlap=1)[0]

    result, problems = extract_chunk(fake_model, people, chunk)

    print("CLEAN RESULT")
    print(json.dumps(result, indent=2))
    print("\nPROBLEMS FOUND")
    for p in problems:
        print(" -", p)
