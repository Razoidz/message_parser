import sqlite3
import os

def load_messages(conn, chat_id):
    """Read one chat from the database as a list of plain dictionaries."""
    rows = conn.execute("""
        SELECT m.seq, m.sent_at, p.name, m.text
        FROM messages m
        JOIN participants p ON p.id = m.participant_id
        WHERE m.chat_id = ?
        ORDER BY m.seq
    """, (chat_id,)).fetchall()
    return [
        {"ref": f"msg_{seq}", "seq": seq, "sent_at": sent_at, "sender": name, "text": text}
        for seq, sent_at, name, text in rows
    ]


def format_message(m):
    """One line for the model: [msg_1] 2024-03-12 14:05 Alice: text"""
    when = m["sent_at"][:16].replace("T", " ")
    return f"[{m['ref']}] {when} {m['sender']}: {m['text']}"


def make_chunks(messages, size, overlap):
    """Split the list into pieces of `size` messages, repeating `overlap` messages between pieces."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    step = size - overlap
    chunks = []
    for start in range(0, len(messages), step):
        chunks.append(messages[start:start + size])
        if start + size >= len(messages):
            break  # this chunk already reaches the end
    return chunks


def build_prompt(participants, chunk):
    lines = "\n".join(format_message(m) for m in chunk)
    return f"Participants: {', '.join(participants)}\n\nTranscript:\n{lines}"


if __name__ == "__main__":
    conn = sqlite3.connect("chat.db")
    messages = load_messages(conn, chat_id=1)
    people = sorted({m["sender"] for m in messages})
    if not os.path.exists("chat.db"):
        raise SystemExit("chat.db not found. Run step3_database.py first.")
    chunks = make_chunks(messages, size=4, overlap=1)
    print(f"{len(messages)} messages -> {len(chunks)} chunks")
    for i, chunk in enumerate(chunks, start=1):
        print(f"\n--- chunk {i}: {chunk[0]['ref']} to {chunk[-1]['ref']} ---")
    print("\n=== What the model would receive for chunk 2 ===")
    print(build_prompt(people, chunks[-1]))
    
