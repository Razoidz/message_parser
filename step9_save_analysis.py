import json
import re
import sqlite3

from step4_prepare_text import load_messages, make_chunks
from step5_extract import extract_chunk, fake_model
from step7_save_results import create_analysis_tables, create_run, lookup_ids, save_results
from step8_synthesize import FAKE_SYNTH_REPLY, synthesize


def add_supports_column(conn):
    """Change an existing sheet: add a 'supports' column to evidence (1 = supports, 0 = contradicts)."""
    columns = [row[1] for row in conn.execute("PRAGMA table_info(evidence)")]
    if "supports" not in columns:
        conn.execute("ALTER TABLE evidence ADD COLUMN supports INTEGER NOT NULL DEFAULT 1")
        conn.commit()


def create_synthesis_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS timeline_entries (
            id        INTEGER PRIMARY KEY,
            run_id    INTEGER NOT NULL REFERENCES analysis_runs(id),
            position  INTEGER NOT NULL,
            when_text TEXT,
            what      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS role_findings (
            id             INTEGER PRIMARY KEY,
            run_id         INTEGER NOT NULL REFERENCES analysis_runs(id),
            participant_id INTEGER NOT NULL REFERENCES participants(id),
            role           TEXT NOT NULL,
            confidence     TEXT NOT NULL,
            reasoning      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS summaries (
            run_id      INTEGER PRIMARY KEY REFERENCES analysis_runs(id),
            narrative   TEXT NOT NULL,
            limitations TEXT NOT NULL
        );
    """)


def link_evidence(conn, run_id, claim_type, claim_id, refs, ref_to_message, supports=True):
    for ref in refs:
        conn.execute(
            "INSERT INTO evidence (run_id, claim_type, claim_id, message_id, supports) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, claim_type, claim_id, ref_to_message[ref], 1 if supports else 0),
        )


def save_analysis(conn, chat_id, run_id, analysis):
    ref_to_message, name_to_pid = lookup_ids(conn, chat_id)

    for position, t in enumerate(analysis["timeline"], start=1):
        cur = conn.execute(
            "INSERT INTO timeline_entries (run_id, position, when_text, what) VALUES (?, ?, ?, ?)",
            (run_id, position, t.get("when"), t["what"]),
        )
        link_evidence(conn, run_id, "timeline", cur.lastrowid, t["evidence"], ref_to_message)

    for r in analysis["roles"]:
        cur = conn.execute(
            "INSERT INTO role_findings (run_id, participant_id, role, confidence, reasoning) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, name_to_pid[r["person"]], r["role"], r["confidence"], r["reasoning"]),
        )
        link_evidence(conn, run_id, "role", cur.lastrowid, r["evidence"], ref_to_message, supports=True)
        link_evidence(conn, run_id, "role", cur.lastrowid, r["counter_evidence"], ref_to_message, supports=False)

    narrative = analysis["how_it_unfolded"]
    conn.execute(
        "INSERT INTO summaries (run_id, narrative, limitations) VALUES (?, ?, ?)",
        (run_id, narrative, json.dumps(analysis["limitations"])),
    )
    cited = sorted(set(re.findall(r"msg_\d+", narrative)))
    link_evidence(conn, run_id, "narrative", run_id, cited, ref_to_message)
    conn.commit()


def get_evidence(conn, claim_type, claim_id, supports):
    return conn.execute("""
        SELECT m.seq, p.name, m.text
        FROM evidence ev
        JOIN messages m ON m.id = ev.message_id
        JOIN participants p ON p.id = m.participant_id
        WHERE ev.claim_type = ? AND ev.claim_id = ? AND ev.supports = ?
        ORDER BY m.seq
    """, (claim_type, claim_id, 1 if supports else 0)).fetchall()


def print_evidence(conn, claim_type, claim_id, supports=True, label=None):
    rows = get_evidence(conn, claim_type, claim_id, supports)
    if label:
        print(f"    {label}" + ("" if rows else " none"))
    for seq, name, text in rows:
        print(f"      msg_{seq} {name}: {text.replace(chr(10), ' / ')}")


def show_analysis(conn, run_id):
    print("TIMELINE")
    for tid, when, what in conn.execute(
        "SELECT id, when_text, what FROM timeline_entries WHERE run_id = ? ORDER BY position", (run_id,)
    ):
        print(f"  {when}: {what}")
        print_evidence(conn, "timeline", tid)

    print("\nROLES")
    rows = conn.execute("""
        SELECT r.id, p.name, r.role, r.confidence, r.reasoning
        FROM role_findings r JOIN participants p ON p.id = r.participant_id
        WHERE r.run_id = ?
    """, (run_id,)).fetchall()
    for rid, name, role, confidence, reasoning in rows:
        print(f"  {name}: {role} ({confidence} confidence)")
        print(f"    {reasoning}")
        print_evidence(conn, "role", rid, True, "supporting messages:")
        print_evidence(conn, "role", rid, False, "counter-evidence:")

    narrative, limitations = conn.execute(
        "SELECT narrative, limitations FROM summaries WHERE run_id = ?", (run_id,)
    ).fetchone()
    print("\nNARRATIVE\n ", narrative)
    print("\nLIMITATIONS")
    for item in json.loads(limitations):
        print("  -", item)


def fake_synth_with_counter(system, user):
    """Same as step 8's fake, but pretend the model also found counter-evidence for Carol."""
    data = json.loads(FAKE_SYNTH_REPLY)
    for r in data["roles"]:
        if r["person"] == "Carol":
            r["counter_evidence"] = ["msg_1"]
    return json.dumps(data)


if __name__ == "__main__":
    conn = sqlite3.connect("chat.db")
    create_analysis_tables(conn)
    add_supports_column(conn)
    create_synthesis_tables(conn)

    chat_id = 1
    messages = load_messages(conn, chat_id)
    people = sorted({m["sender"] for m in messages})
    known_refs = {m["ref"] for m in messages}
    chunk = make_chunks(messages, size=4, overlap=1)[0]

    extraction, _ = extract_chunk(fake_model, people, chunk)
    analysis, _ = synthesize(fake_synth_with_counter, people, [extraction], known_refs)

    run_id = create_run(conn, chat_id)
    save_results(conn, chat_id, run_id, [extraction])
    save_analysis(conn, chat_id, run_id, analysis)

    print(f"Saved as analysis run {run_id}\n")
    show_analysis(conn, run_id)
