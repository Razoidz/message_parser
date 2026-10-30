import sqlite3

from step3_database import create_chat, create_tables, save_messages, to_iso
from step4_prepare_text import load_messages
from step7_save_results import create_analysis_tables, create_run, get_evidence, save_results
from step9_save_analysis import add_supports_column, create_synthesis_tables, save_analysis
PARSED = [
    {"date": "12/03/2024", "time": "14:05", "sender": "Alice", "text": "hi"},
    {"date": "12/03/2024", "time": "14:05", "sender": "Bob", "text": "hello"},
    {"date": "12/03/2024", "time": "14:06", "sender": "Alice", "text": "ready?"},
]


def fresh_db():
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    create_analysis_tables(conn)
    return conn


def test_to_iso_day_first():
    assert to_iso("12/03/2024", "14:05") == "2024-03-12T14:05:00"


def test_to_iso_month_first():
    assert to_iso("12/03/2024", "14:05", dayfirst=False) == "2024-12-03T14:05:00"


def test_messages_keep_their_order_even_with_equal_timestamps():
    conn = fresh_db()
    chat = create_chat(conn, "t")
    save_messages(conn, chat, PARSED)
    loaded = load_messages(conn, chat)
    assert [m["text"] for m in loaded] == ["hi", "hello", "ready?"]
    assert [m["seq"] for m in loaded] == [1, 2, 3]


def test_importing_twice_makes_two_separate_chats():
    conn = fresh_db()
    first = create_chat(conn, "a")
    save_messages(conn, first, PARSED)
    second = create_chat(conn, "b")
    save_messages(conn, second, PARSED)
    assert [m["seq"] for m in load_messages(conn, first)] == [1, 2, 3]
    assert [m["seq"] for m in load_messages(conn, second)] == [1, 2, 3]


def test_same_name_in_two_chats_is_two_participants():
    conn = fresh_db()
    for title in ("a", "b"):
        save_messages(conn, create_chat(conn, title), PARSED)
    assert conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0] == 4


def test_saved_evidence_points_at_the_right_messages():
    conn = fresh_db()
    chat = create_chat(conn, "t")
    save_messages(conn, chat, PARSED)
    run_id = create_run(conn, chat)
    result = {
        "events": [{"summary": "greeting", "participants": ["Alice"], "evidence": ["msg_1", "msg_2"]}],
        "actions": [{"person": "Bob", "type": "answered", "summary": "replied", "evidence": ["msg_2"]}],
        "unclear": [],
    }
    save_results(conn, chat, run_id, [result])

    event_id = conn.execute("SELECT id FROM events").fetchone()[0]
    action_id = conn.execute("SELECT id FROM actions").fetchone()[0]
    assert [row[0] for row in get_evidence(conn, "event", event_id)] == [1, 2]
    assert [(row[0], row[1]) for row in get_evidence(conn, "action", action_id)] == [(2, "Bob")]
def test_month_first_dates_are_saved_correctly():
    conn = fresh_db()
    chat = create_chat(conn, "t")
    parsed = [{"date": "03/25/2024", "time": "14:05", "sender": "Alice", "text": "hi"}]
    save_messages(conn, chat, parsed, dayfirst=False)
    assert load_messages(conn, chat)[0]["sent_at"] == "2024-03-25T14:05:00"
def test_saving_a_narrative_that_cites_a_missing_message_does_not_crash():
    conn = fresh_db()
    add_supports_column(conn)
    create_synthesis_tables(conn)
    chat = create_chat(conn, "t")
    save_messages(conn, chat, PARSED)
    run_id = create_run(conn, chat)
    analysis = {"timeline": [], "roles": [], "limitations": [],
                "how_it_unfolded": "Alice spoke [msg_1], then [msg_42]."}

    save_analysis(conn, chat, run_id, analysis)

    rows = conn.execute("SELECT message_id FROM evidence WHERE claim_type = 'narrative'").fetchall()
    assert len(rows) == 1  # only the real citation was stored