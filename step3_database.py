import os
import sqlite3
from datetime import datetime

from step2_parse_file import parse_file


def to_iso(date, time, dayfirst=True):
    """Turn '12/03/2024' + '14:05' into '2024-03-12T14:05:00'."""
    fmt = "%d/%m/%Y %H:%M" if dayfirst else "%m/%d/%Y %H:%M"
    return datetime.strptime(f"{date} {time}", fmt).isoformat()


def create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chats (
            id          INTEGER PRIMARY KEY,
            title       TEXT,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS participants (
            id      INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL REFERENCES chats(id),
            name    TEXT NOT NULL,
            UNIQUE (chat_id, name)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id             INTEGER PRIMARY KEY,
            chat_id        INTEGER NOT NULL REFERENCES chats(id),
            seq            INTEGER NOT NULL,
            sent_at        TEXT NOT NULL,
            participant_id INTEGER NOT NULL REFERENCES participants(id),
            text           TEXT NOT NULL
        );
    """)


def create_chat(conn, title):
    cur = conn.execute(
        "INSERT INTO chats (title, imported_at) VALUES (?, ?)",
        (title, datetime.now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid  # the new chat's id number


def get_or_create_participant(conn, chat_id, name):
    conn.execute(
        "INSERT OR IGNORE INTO participants (chat_id, name) VALUES (?, ?)",
        (chat_id, name),
    )
    row = conn.execute(
        "SELECT id FROM participants WHERE chat_id = ? AND name = ?",
        (chat_id, name),
    ).fetchone()
    return row[0]


def save_messages(conn, chat_id, messages):
    for seq, m in enumerate(messages, start=1):
        pid = get_or_create_participant(conn, chat_id, m["sender"])
        conn.execute(
            "INSERT INTO messages (chat_id, seq, sent_at, participant_id, text) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, seq, to_iso(m["date"], m["time"]), pid, m["text"]),
        )
    conn.commit()


def show_chat(conn, chat_id):
    rows = conn.execute("""
        SELECT m.seq, m.sent_at, p.name, m.text
        FROM messages m
        JOIN participants p ON p.id = m.participant_id
        WHERE m.chat_id = ?
        ORDER BY m.seq
    """, (chat_id,)).fetchall()
    for r in rows:
        print(r)


def count_by_sender(conn, chat_id):
    return conn.execute("""
        SELECT p.name, COUNT(*)
        FROM messages m
        JOIN participants p ON p.id = m.participant_id
        WHERE m.chat_id = ?
        GROUP BY p.name
    """, (chat_id,)).fetchall()


if __name__ == "__main__":
    if os.path.exists("chat.db"):
        os.remove("chat.db")  # development only: start fresh each run
    conn = sqlite3.connect("chat.db")
    create_tables(conn)

    msgs = parse_file("sample_chat.txt")
    first = create_chat(conn, "Cabin trip")
    save_messages(conn, first, msgs)
    second = create_chat(conn, "Cabin trip (imported again)")
    save_messages(conn, second, msgs)

    print("Messages per chat:",
          conn.execute("SELECT chat_id, COUNT(*) FROM messages GROUP BY chat_id").fetchall())
    print("\nChat 2:")
    show_chat(conn, second)
    print("\nCounts in chat 2:", count_by_sender(conn, second))
