import sqlite3

import pytest

import run_analysis

SAMPLE = (
    "12/03/2024, 14:05 - Alice: Should we book the cabin?\n"
    "12/03/2024, 14:06 - Bob: Fine by me\n"
    "12/03/2024, 14:08 - Carol: Let's do it\n"
)


def statuses():
    conn = sqlite3.connect("chat.db")
    return conn.execute("SELECT status, error FROM analysis_runs ORDER BY id").fetchall()


@pytest.fixture
def chat_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # each test gets its own empty folder, so its own chat.db
    (tmp_path / "chat.txt").write_text(SAMPLE, encoding="utf-8")
    return "chat.txt"


def test_successful_run_is_marked_done(chat_file):
    run_analysis.main([chat_file, "--fake", "--i-have-consent"])
    assert statuses() == [("done", None)]


def test_failed_run_is_marked_failed_with_a_friendly_message(chat_file):
    class BadRequestError(Exception):
        pass

    def broken(system, user):
        raise BadRequestError("Your credit balance is too low to access the Anthropic API.")

    with pytest.raises(SystemExit):
        run_analysis.main([chat_file, "--i-have-consent"], models=(broken, broken))

    [(status, error)] = statuses()
    assert status == "failed"
    assert "credit" in error.lower()
    assert "BadRequestError" not in error  # the friendly message, not the raw one


def test_refuses_to_run_without_consent_and_creates_no_database(chat_file, tmp_path):
    with pytest.raises(SystemExit):
        run_analysis.main([chat_file, "--fake"])
    assert not (tmp_path / "chat.db").exists()


def test_missing_file_stops_before_touching_the_database(chat_file, tmp_path):
    with pytest.raises(SystemExit):
        run_analysis.main(["nope.txt", "--fake", "--i-have-consent"])
    assert not (tmp_path / "chat.db").exists()
def test_month_first_export_needs_the_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "chat.txt").write_text("03/25/2024, 14:05 - Alice: hi\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        run_analysis.main(["chat.txt", "--fake", "--i-have-consent"])
    assert "--monthfirst" in str(exc.value)
    assert not (tmp_path / "chat.db").exists()  # stopped before touching the database

    run_analysis.main(["chat.txt", "--fake", "--i-have-consent", "--monthfirst"])
    assert statuses() == [("done", None)]
def test_real_mode_without_an_api_key_stops_with_a_message(chat_file, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        run_analysis.main([chat_file, "--i-have-consent"])
    assert "ANTHROPIC_API_KEY" in str(exc.value)
def test_prepare_then_execute_runs_in_two_phases(chat_file):
    chat_id, run_id = run_analysis.prepare_analysis(chat_file, "t")
    assert statuses() == [("running", None)]

    run_analysis.execute_analysis(chat_id, run_id, run_analysis.fake_model, run_analysis.fake_synth_model)
    assert statuses() == [("done", None)]