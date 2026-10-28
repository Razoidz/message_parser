import pytest

from step4_prepare_text import make_chunks


def msgs(n):
    return [{"ref": f"msg_{i}"} for i in range(1, n + 1)]


def refs(chunks):
    return [[m["ref"] for m in chunk] for chunk in chunks]


def test_overlap_repeats_messages_between_chunks():
    assert refs(make_chunks(msgs(6), size=4, overlap=1)) == [
        ["msg_1", "msg_2", "msg_3", "msg_4"],
        ["msg_4", "msg_5", "msg_6"],
    ]


def test_short_chat_is_one_chunk():
    assert len(make_chunks(msgs(3), size=4, overlap=1)) == 1


def test_empty_chat_has_no_chunks():
    assert make_chunks([], size=4, overlap=1) == []


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        make_chunks(msgs(5), size=4, overlap=4)


@pytest.mark.parametrize("n, size, overlap", [
    (1, 4, 1), (7, 3, 1), (10, 4, 2), (150, 150, 10), (151, 150, 10), (300, 150, 10),
])
def test_every_message_is_covered_and_no_chunk_is_too_big(n, size, overlap):
    chunks = make_chunks(msgs(n), size, overlap)
    seen = {m["ref"] for chunk in chunks for m in chunk}
    assert seen == {f"msg_{i}" for i in range(1, n + 1)}
    assert all(len(chunk) <= size for chunk in chunks)
