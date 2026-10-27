import re
from pprint import pprint

from step1_parse_line import parse_line

# A line that starts with a timestamp, whether or not it is a normal message
STARTS_WITH_TIMESTAMP = re.compile(r"^\[?\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}")


def parse_file(path):
    messages = []
    current = None  # the message we are currently building

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            parsed = parse_line(line)
            if parsed:
                messages.append(parsed)
                current = parsed
            elif STARTS_WITH_TIMESTAMP.match(line):
                current = None  # system line: stop attaching text to the last message
            elif current:
                current["text"] += "\n" + line  # continuation line

    return messages


if __name__ == "__main__":
    pprint(parse_file("sample_chat.txt"))