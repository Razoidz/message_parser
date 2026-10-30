import io

import pytest

import step10_web
from step10_web import app

SAMPLE = (
    b"12/03/2024, 14:05 - Alice: Should we book the cabin?\n"
    b"12/03/2024, 14:06 - Bob: Fine by me\n"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # every test gets its own empty chat.db
    monkeypatch.setattr(step10_web, "launch", lambda job: job())  # run background jobs inline
    return app.test_client()
def post(client, data=SAMPLE, **fields):
    form = {
        "chat_file": (io.BytesIO(data), "whatever-name.txt"),
        "title": "Test chat",
        "date_order": "dayfirst",
        "consent": "yes",
        "fake": "yes",
    }
    form.update(fields)
    return client.post("/upload", data=form, content_type="multipart/form-data")


def text(response):
    return response.get_data(as_text=True)


def test_upload_page_loads_and_asks_for_consent(client):
    response = client.get("/upload")
    assert response.status_code == 200
    assert 'name="consent"' in text(response)


def test_successful_upload_redirects_to_the_run_page(client):
    response = post(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/run/1")
    page = client.get("/run/1")
    assert page.status_code == 200
    assert "Test chat" in text(page)


def test_upload_without_consent_is_refused_and_saves_nothing(client, tmp_path):
    response = post(client, consent="no")
    assert response.status_code == 400
    assert "right to analyze" in text(response)
    assert not (tmp_path / "chat.db").exists()


def test_upload_without_a_file_is_refused(client):
    response = client.post("/upload", data={"consent": "yes"}, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "choose a chat file" in text(response)


def test_wrong_date_order_shows_a_message_and_saves_nothing(client, tmp_path):
    response = post(client, data=b"03/25/2024, 14:05 - Alice: hi\n")
    assert response.status_code == 400
    assert "Could not read a date" in text(response)
    assert not (tmp_path / "chat.db").exists()


def test_month_first_file_works_with_the_month_first_option(client):
    response = post(client, data=b"03/25/2024, 14:05 - Alice: hi\n", date_order="monthfirst")
    assert response.status_code == 302


def test_file_that_is_not_text_gives_a_message(client):
    response = post(client, data=b"\xff\xfe\x00\x01 this is not utf-8 text")
    assert response.status_code == 400
    assert "plain .txt" in text(response)


def test_file_with_no_messages_gives_a_message(client):
    response = post(client, data=b"just some words, no chat\n")
    assert response.status_code == 400
    assert "No messages found" in text(response)


def test_too_large_upload_is_rejected(client):
    response = post(client, data=b"x" * (5 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert "too large" in text(response)


def test_real_mode_without_an_api_key_shows_a_message_and_does_not_crash(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = post(client, fake="no")
    assert response.status_code == 400
    assert "ANTHROPIC_API_KEY" in text(response)


def test_pipeline_failure_redirects_to_a_page_that_explains_it(client, monkeypatch):
    class BadRequestError(Exception):
        pass

    def broken(system, user):
        raise BadRequestError("Your credit balance is too low to access the Anthropic API.")

    monkeypatch.setattr(step10_web, "choose_models", lambda fake: (broken, broken))
    response = post(client)
    assert response.status_code == 302
    page = text(client.get(response.headers["Location"]))
    assert "This analysis failed" in page
    assert "credit balance" in page


def test_uploaded_filename_is_never_used(client, tmp_path):
    post(client)
    assert not list(tmp_path.glob("*whatever*"))
def test_upload_redirects_at_once_and_the_page_shows_running_until_the_job_finishes(client, monkeypatch):
    jobs = []
    monkeypatch.setattr(step10_web, "launch", jobs.append)  # collect the job instead of running it

    response = post(client)
    assert response.status_code == 302
    assert len(jobs) == 1

    page = text(client.get("/run/1"))
    assert "still running" in page
    assert "location.reload" in page  # the page refreshes itself

    jobs[0]()  # now let the analysis run

    page = text(client.get("/run/1"))
    assert "still running" not in page
    assert "location.reload" not in page
    assert "initiator" in page  # the finished results are shown