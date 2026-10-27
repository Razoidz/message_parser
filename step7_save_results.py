import sqlite3
from datetime import datetime

from step4_prepare_text import load_messages, make_chunks
from step5_extract import extract_chunk, fake_model


def create_analysis_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id         INTEGER PRIMARY KEY,
            chat_id    INTEGER NOT NULL REFERENCES chats(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id      INTEGER PRIMARY KEY,
            run_id  INTEGER NOT NULL REFERENCES analysis_runs(id),
            summary TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS actions (
            id             INTEGER PRIMARY KEY,
            run_id         INTEGER NOT NULL REFERENCES analysis_runs(id),
            participant_id INTEGER NOT NULL REFERENCES participants(id),
            type           TEXT NOT NULL,
            summary        TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id         INTEGER PRIMARY KEY,
            run_id     INTEGER NOT NULL REFERENCES analysis_runs(id),
            claim_type TEXT NOT NULL,
            claim_id   INTEGER NOT NULL,
            message_id INTEGER NOT NULL REFERENCES messages(id)
        );
    """)


def create_run(conn, chat_id):
    cur = conn.execute(
        "INSERT INTO analysis_runs (chat_id, created_at) VALUES (?, ?)",
        (chat_id, datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def lookup_ids(conn, chat_id):
    """Dictionaries that translate 'msg_3' -> database id, and 'Alice' -> database id."""
    ref_to_message = {
        f"msg_{seq}": mid
        for seq, mid in conn.execute("SELECT seq, id FROM messages WHERE chat_id = ?", (chat_id,))
    }
    name_to_participant = {
        name: pid
        for name, pid in conn.execute("SELECT name, id FROM participants WHERE chat_id = ?", (chat_id,))
    }
    return ref_to_message, name_to_participant


def save_evidence(conn, run_id, claim_type, claim_id, refs, ref_to_message):
    for ref in refs:
        conn.execute(
            "INSERT INTO evidence (run_id, claim_type, claim_id, message_id) VALUES (?, ?, ?, ?)",
            (run_id, claim_type, claim_id, ref_to_message[ref]),
        )


def save_results(conn, chat_id, run_id, results):
    ref_to_message, name_to_pid = lookup_ids(conn, chat_id)
    for result in results:
        for ev in result["events"]:
            cur = conn.execute(
                "INSERT INTO events (run_id, summary) VALUES (?, ?)",
                (run_id, ev["summary"]),
            )
            save_evidence(conn, run_id, "event", cur.lastrowid, ev["evidence"], ref_to_message)
        for ac in result["actions"]:
            cur = conn.execute(
                "INSERT INTO actions (run_id, participant_id, type, summary) VALUES (?, ?, ?, ?)",
                (run_id, name_to_pid[ac["person"]], ac["type"], ac["summary"]),
            )
            save_evidence(conn, run_id, "action", cur.lastrowid, ac["evidence"], ref_to_message)
    conn.commit()


def get_evidence(conn, claim_type, claim_id):
    return conn.execute("""
        SELECT m.seq, p.name, m.text
        FROM evidence ev
        JOIN messages m ON m.id = ev.message_id
        JOIN participants p ON p.id = m.participant_id
        WHERE ev.claim_type = ? AND ev.claim_id = ?
        ORDER BY m.seq
    """, (claim_type, claim_id)).fetchall()


def print_evidence(conn, claim_type, claim_id):
    for seq, name, text in get_evidence(conn, claim_type, claim_id):
        print(f"      msg_{seq} {name}: {text.replace(chr(10), ' / ')}")


def show_results(conn, run_id):
    print("EVENTS")
    for eid, summary in conn.execute("SELECT id, summary FROM events WHERE run_id = ?", (run_id,)):
        print(f"  - {summary}")
        print_evidence(conn, "event", eid)

    print("\nACTIONS")
    rows = conn.execute("""
        SELECT a.id, p.name, a.type, a.summary
        FROM actions a
        JOIN participants p ON p.id = a.participant_id
        WHERE a.run_id = ?
    """, (run_id,)).fetchall()
    for aid, name, atype, summary in rows:
        print(f"  - {name} [{atype}]: {summary}")
        print_evidence(conn, "action", aid)


if __name__ == "__main__":
    conn = sqlite3.connect("chat.db")
    create_analysis_tables(conn)

    chat_id = 1
    messages = load_messages(conn, chat_id)
    people = sorted({m["sender"] for m in messages})
    chunk = make_chunks(messages, size=4, overlap=1)[0]

    result, problems = extract_chunk(fake_model, people, chunk)
    run_id = create_run(conn, chat_id)
    save_results(conn, chat_id, run_id, [result])

    print(f"Saved as analysis run {run_id}\n")
    show_results(conn, run_id)

    print("\nRAW EVIDENCE SHEET (claim_type, claim_id, message_id)")
    for row in conn.execute("SELECT claim_type, claim_id, message_id FROM evidence WHERE run_id = ?", (run_id,)):
        print("  ", row)
