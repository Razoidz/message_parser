import json
import os
import sqlite3

from step4_prepare_text import load_messages, make_chunks
from step5_extract import FAKE_REPLY, extract_chunk

MODEL = "claude-sonnet-5-5"


def claude_model(system, user):
    """The real model call. Same inputs and output as fake_model."""
    import anthropic  # imported here so the fake test works without the library

    client = anthropic.Anthropic()  # reads your key from the ANTHROPIC_API_KEY setting
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def extract_with_retry(model_fn, people, chunk, tries=2):
    """If the reply is not valid JSON, ask again instead of crashing."""
    last_error = None
    for attempt in range(1, tries + 1):
        try:
            return extract_chunk(model_fn, people, chunk)
        except json.JSONDecodeError as e:
            last_error = e
            print(f"  attempt {attempt}: reply was not valid JSON, retrying...")
    raise ValueError(f"Model gave invalid JSON {tries} times: {last_error}")


def extract_all(model_fn, people, chunks):
    """Run extraction on every chunk and collect the results."""
    results = []
    for i, chunk in enumerate(chunks, start=1):
        print(f"Chunk {i} of {len(chunks)} ({chunk[0]['ref']} to {chunk[-1]['ref']})")
        clean, problems = extract_with_retry(model_fn, people, chunk)
        for p in problems:
            print("  problem:", p)
        results.append(clean)
    return results


def make_flaky_model():
    """Test helper: fails the first time, works the second."""
    calls = {"n": 0}

    def flaky(system, user):
        calls["n"] += 1
        if calls["n"] == 1:
            return "Sure! Here is the analysis you asked for: ..."  # not JSON
        return FAKE_REPLY

    return flaky


if __name__ == "__main__":
    conn = sqlite3.connect("chat.db")
    messages = load_messages(conn, chat_id=1)
    people = sorted({m["sender"] for m in messages})
    chunks = make_chunks(messages, size=4, overlap=1)

    if os.environ.get("ANTHROPIC_API_KEY"):
        print("Using the REAL model\n")
        results = extract_all(claude_model, people, chunks)
        print(json.dumps(results, indent=2))
    else:
        print("No API key found, testing the retry logic with a flaky fake model\n")
        results = extract_all(make_flaky_model(), people, chunks[:1])
        print("\nActions found:", [(a["person"], a["type"]) for a in results[0]["actions"]])
