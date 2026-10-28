import re
from datetime import datetime
# Matches Android: 12/03/2024, 14:05 - Alice: hi
# and iPhone:      [12/03/2024, 14:05:22] Alice: hi
LINE = re.compile(
    r"^\[?(\d{1,2}/\d{1,2}/\d{4}), (\d{1,2}:\d{2})(?::\d{2})?(?:\s?([AaPp][Mm]))?\]? ?-? ?([^:]+): (.*)$"
)

def parse_line(line):
    match = LINE.match(line)
    if match is None:
        return None
    date, time, ampm, sender, text = match.groups()
    if ampm:  # convert 2:08 PM into 14:08 so the rest of the program only sees 24-hour times
        time = datetime.strptime(f"{time} {ampm.upper()}", "%I:%M %p").strftime("%H:%M")
    return {"date": date, "time": time, "sender": sender, "text": text}

if __name__ == "__main__":
    tests = [
        "12/03/2024, 14:05 - Alice: Should we book the cabin?",
        "12/03/2024, 14:06 - Bob: Meet at 5:30: bring snacks",
        "12/03/2024, 14:07 - Carol added Dan",
        "I think Friday works",
        "[12/03/2024, 14:08:10] Carol: Let's do it",
        "1/3/2024, 9:05 - Al: hi",
    ]
    for t in tests:
        print(repr(t), "->", parse_line(t))
