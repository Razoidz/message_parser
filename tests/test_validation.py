import json

import pytest

from step5_extract import parse_json, validate
from step8_synthesize import validate_synthesis

KNOWN = {"msg_1", "msg_2", "msg_3"}
PEOPLE = ["Alice", "Bob", "Carol"]


# ---------- parse_json ----------

def test_parse_json_strips_markdown_fences():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_accepts_plain_json():
    assert parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_rejects_chatty_text():
    with pytest.raises(json.JSONDecodeError):
        parse_json("Sure! Here is the analysis you asked for")


# ---------- extraction validation ----------

def test_event_with_only_invented_evidence_is_dropped():
    data = {"events": [{"summary": "x", "participants": ["Alice"], "evidence": ["msg_99"]}]}
    clean, problems = validate(data, KNOWN, PEOPLE)
    assert clean["events"] == []
    assert len(problems) == 1


def test_invented_evidence_is_removed_but_real_evidence_is_kept():
    data = {"events": [{"summary": "x", "participants": ["Alice"], "evidence": ["msg_1", "msg_99"]}]}
    clean, _ = validate(data, KNOWN, PEOPLE)
    assert clean["events"][0]["evidence"] == ["msg_1"]


def test_unknown_participant_is_removed_from_an_event():
    data = {"events": [{"summary": "x", "participants": ["Alice", "Dave"], "evidence": ["msg_1"]}]}
    clean, _ = validate(data, KNOWN, PEOPLE)
    assert clean["events"][0]["participants"] == ["Alice"]


def test_action_by_unknown_person_is_dropped():
    data = {"actions": [{"person": "Dave", "type": "agreed", "summary": "x", "evidence": ["msg_1"]}]}
    clean, problems = validate(data, KNOWN, PEOPLE)
    assert clean["actions"] == []
    assert len(problems) == 1


def test_unknown_action_type_becomes_other():
    data = {"actions": [{"person": "Alice", "type": "schemed", "summary": "x", "evidence": ["msg_1"]}]}
    clean, _ = validate(data, KNOWN, PEOPLE)
    assert clean["actions"][0]["type"] == "other"


def test_empty_reply_is_fine():
    clean, problems = validate({}, KNOWN, PEOPLE)
    assert clean == {"events": [], "actions": [], "unclear": []}
    assert problems == []


# ---------- synthesis validation ----------

def role(person="Alice", confidence="high", evidence=("msg_1", "msg_2"), counter=()):
    return {"person": person, "role": "initiator", "confidence": confidence,
            "reasoning": "r", "evidence": list(evidence), "counter_evidence": list(counter)}


def test_high_confidence_needs_two_supporting_messages():
    clean, problems = validate_synthesis({"roles": [role(evidence=["msg_1"])]}, KNOWN, PEOPLE)
    assert clean["roles"][0]["confidence"] == "low"
    assert len(problems) == 1


def test_confidence_is_kept_with_two_supporting_messages():
    clean, problems = validate_synthesis({"roles": [role(confidence="medium")]}, KNOWN, PEOPLE)
    assert clean["roles"][0]["confidence"] == "medium"
    assert problems == []


def test_made_up_confidence_value_becomes_low():
    clean, _ = validate_synthesis({"roles": [role(confidence="certain")]}, KNOWN, PEOPLE)
    assert clean["roles"][0]["confidence"] == "low"


def test_role_for_unknown_person_is_dropped():
    clean, problems = validate_synthesis({"roles": [role(person="Dave")]}, KNOWN, PEOPLE)
    assert clean["roles"] == []
    assert len(problems) == 1


def test_invented_counter_evidence_is_removed():
    clean, _ = validate_synthesis({"roles": [role(counter=["msg_3", "msg_99"])]}, KNOWN, PEOPLE)
    assert clean["roles"][0]["counter_evidence"] == ["msg_3"]


def test_timeline_entry_without_valid_evidence_is_dropped():
    data = {"timeline": [{"when": "x", "what": "y", "evidence": ["msg_99"]}]}
    clean, problems = validate_synthesis(data, KNOWN, PEOPLE)
    assert clean["timeline"] == []
    assert len(problems) == 1


def test_narrative_citing_a_missing_message_is_reported():
    data = {"how_it_unfolded": "Alice spoke [msg_1] then [msg_42]."}
    _, problems = validate_synthesis(data, KNOWN, PEOPLE)
    assert any("msg_42" in p for p in problems)
