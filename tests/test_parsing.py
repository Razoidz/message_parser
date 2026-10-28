import pytest

from step1_parse_line import parse_line
from step2_parse_file import parse_file


def write_chat(tmp_path, text):
    path = tmp_path / "chat.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


# ---------- parse_line ----------

def test_android_line():
    assert parse_line("12/03/2024, 14:05 - Alice: Should we book it?") == {
        "date": "12/03/2024", "time": "14:05", "sender": "Alice", "text": "Should we book it?",
    }


def test_colon_inside_the_text_is_kept():
    m = parse_line("12/03/2024, 14:06 - Bob: Meet at 5:30: bring snacks")
    assert m["sender"] == "Bob"
    assert m["text"] == "Meet at 5:30: bring snacks"


@pytest.mark.parametrize("line", [
    "12/03/2024, 14:07 - Carol added Dan",   # system line
    "I think Friday works",                   # continuation line
    "",                                       # blank line
])
def test_lines_that_are_not_messages_return_none(line):
    assert parse_line(line) is None


def test_single_digit_day_and_hour():
    m = parse_line("1/3/2024, 9:05 - Al: hi")
    assert (m["date"], m["time"], m["sender"]) == ("1/3/2024", "9:05", "Al")


def test_iphone_brackets_and_seconds():
    m = parse_line("[12/03/2024, 14:08:10] Carol: Let's do it")
    assert m["sender"] == "Carol"
    assert m["time"] == "14:08"


@pytest.mark.parametrize("line, expected_time", [
    ("[12/03/2024, 2:08:10 PM] Carol: hi", "14:08"),
    ("[12/03/2024, 12:05:00 AM] Carol: hi", "00:05"),      # midnight
    ("[12/03/2024, 12:05:00 PM] Carol: hi", "12:05"),      # noon
    ("12/03/2024, 2:08 pm - Carol: hi", "14:08"),          # Android, lowercase
    ("[12/03/2024, 2:08:10\u202fPM] Carol: hi", "14:08"),  # iPhone narrow no-break space
])
def test_twelve_hour_clock_is_converted_to_24_hour(line, expected_time):
    m = parse_line(line)
    assert m["sender"] == "Carol"
    assert m["time"] == expected_time


# ---------- parse_file ----------

def test_multiline_message_is_joined(tmp_path):
    path = write_chat(tmp_path, "12/03/2024, 14:05 - Alice: First line\nsecond line\n")
    msgs = parse_file(path)
    assert len(msgs) == 1
    assert msgs[0]["text"] == "First line\nsecond line"


def test_system_line_does_not_leak_into_previous_message(tmp_path):
    path = write_chat(tmp_path, (
        "12/03/2024, 14:06 - Bob: Fine by me\n"
        "12/03/2024, 14:07 - Carol added Dan\n"
        "12/03/2024, 14:08 - Carol: Let's do it\n"
    ))
    msgs = parse_file(path)
    assert [m["sender"] for m in msgs] == ["Bob", "Carol"]
    assert msgs[0]["text"] == "Fine by me"


def test_lines_before_the_first_message_are_ignored(tmp_path):
    path = write_chat(tmp_path, "some stray text\n12/03/2024, 14:05 - Alice: hi\n")
    assert len(parse_file(path)) == 1


def test_invisible_left_to_right_mark_is_ignored(tmp_path):
    # iPhone exports often start lines with an invisible character
    path = write_chat(tmp_path, "\u200e[12/03/2024, 14:05:22] Alice: hi\n")
    msgs = parse_file(path)
    assert len(msgs) == 1
    assert msgs[0]["sender"] == "Alice"
