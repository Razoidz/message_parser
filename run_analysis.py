"""Run the whole pipeline on one chat file.

Usage:
  python3 run_analysis.py sample_chat.txt --title "Cabin trip" --i-have-consent --fake
  python3 run_analysis.py my_chat.txt --title "Project chat" --i-have-consent   (real model)
"""
import argparse
import json
import os
import sqlite3
import sys

from step2_parse_file import parse_file
from step3_database import create_chat, create_tables, save_messages, to_iso
from step4_prepare_text import load_messages, make_chunks
from step5_extract import fake_model
from step6_real_model import claude_model, extract_all
from step7_save_results import create_analysis_tables, save_results
from step8_synthesize import fake_synth_model, synthesize
from step9_save_analysis import add_supports_column, create_synthesis_tables, save_analysis
from step11_run_status import add_status_columns, friendly_error, set_status, start_run


class InputError(Exception):
    """The file or settings are unusable. The message is safe to show to the user."""


class AnalysisFailed(Exception):
    """The model pipeline failed. Carries a friendly message and the run's id."""

    def __init__(self, message, run_id):
        super().__init__(message)
        self.run_id = run_id


def choose_models(use_fake):
    if use_fake:
        return fake_model, fake_synth_model
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("No ANTHROPIC_API_KEY found. Set it, or add --fake to test with canned replies.")
    return claude_model, claude_model  # the same function serves both passes


def synthesize_with_retry(model_fn, people, results, known_refs, tries=2):
    for attempt in range(1, tries + 1):
        try:
            return synthesize(model_fn, people, results, known_refs)
        except json.JSONDecodeError:
            print(f"  synthesis attempt {attempt}: reply was not valid JSON, retrying...")
    raise ValueError(f"Synthesis gave invalid JSON {tries} times")


def run_pipeline(conn, chat_id, run_id, extract_fn, synth_fn, chunk_size, overlap):
    """The slow, failure-prone part: the model calls and everything after them."""
    messages = load_messages(conn, chat_id)
    people = sorted({m["sender"] for m in messages})
    known_refs = {m["ref"] for m in messages}

    print("[3/6] Extracting events and actions")
    chunks = make_chunks(messages, chunk_size, overlap)
    results = extract_all(extract_fn, people, chunks)

    print("[4/6] Saving extraction results")
    save_results(conn, chat_id, run_id, results)

    print("[5/6] Synthesizing roles and timeline")
    analysis, problems = synthesize_with_retry(synth_fn, people, results, known_refs)
    for p in problems:
        print("      problem:", p)

    print("[6/6] Saving the analysis")
    save_analysis(conn, chat_id, run_id, analysis)


def check_dates(parsed, monthfirst):
    """Make sure every date can be read BEFORE anything is saved."""
    try:
        for m in parsed:
            to_iso(m["date"], m["time"], not monthfirst)
    except ValueError:
        order = "month/day/year" if monthfirst else "day/month/year"
        hint = "remove --monthfirst" if monthfirst else "add --monthfirst"
        raise InputError(
            f"Could not read a date in the file as {order}. "
            f"If your export uses the other order, {hint}."
        )


def analyze_file(path, title, extract_fn, synth_fn, monthfirst=False, chunk_size=150, overlap=10):
    """Parse, save and analyze one chat file. Returns (chat_id, run_id).

    Raises InputError for a bad file, and AnalysisFailed if the model pipeline breaks.
    It never calls sys.exit, so the command line and the web app can both use it.
    """
    if not os.path.exists(path):
        raise InputError(f"File not found: {path}")

    print("[1/6] Parsing the file")
    parsed = parse_file(path)
    if not parsed:
        raise InputError("No messages found. Check the file format.")
    print(f"      {len(parsed)} messages")
    check_dates(parsed, monthfirst)

    conn = sqlite3.connect("chat.db")
    create_tables(conn)
    create_analysis_tables(conn)
    add_supports_column(conn)
    add_status_columns(conn)
    create_synthesis_tables(conn)

    print("[2/6] Saving messages")
    chat_id = create_chat(conn, title)
    save_messages(conn, chat_id, parsed, dayfirst=not monthfirst)
    run_id = start_run(conn, chat_id)  # status: running

    try:
        run_pipeline(conn, chat_id, run_id, extract_fn, synth_fn, chunk_size, overlap)
    except KeyboardInterrupt:
        set_status(conn, run_id, "failed", "Cancelled by user")
        raise
    except Exception as e:
        message = friendly_error(e)
        set_status(conn, run_id, "failed", message)
        raise AnalysisFailed(message, run_id) from e

    set_status(conn, run_id, "done")
    return chat_id, run_id


def main(argv=None, models=None):
    ap = argparse.ArgumentParser(description="Analyze a WhatsApp chat export.")
    ap.add_argument("file", help="path to the exported chat .txt file")
    ap.add_argument("--title", default=None)
    ap.add_argument("--chunk-size", type=int, default=150)
    ap.add_argument("--overlap", type=int, default=10)
    ap.add_argument("--monthfirst", action="store_true",
                    help="dates in the file are MM/DD/YYYY (default is DD/MM/YYYY)")
    ap.add_argument("--fake", action="store_true", help="use canned replies instead of the real model")
    ap.add_argument("--i-have-consent", action="store_true", dest="consent",
                    help="confirm you have the right to analyze this chat")
    args = ap.parse_args(argv)

    if not args.consent:
        sys.exit("Refusing to run: confirm you have the right to analyze this chat with --i-have-consent")
    extract_fn, synth_fn = models or choose_models(args.fake)

    try:
        chat_id, run_id = analyze_file(
            args.file, args.title, extract_fn, synth_fn,
            monthfirst=args.monthfirst, chunk_size=args.chunk_size, overlap=args.overlap,
        )
    except InputError as e:
        sys.exit(str(e))
    except AnalysisFailed as e:
        sys.exit(f"\nAnalysis failed: {e}\n(Run {e.run_id} was marked as failed.)")
    except KeyboardInterrupt:
        sys.exit("\nCancelled. The run was marked as failed.")

    print(f"\nDone. Chat {chat_id}, analysis run {run_id}.")
    print("Run  python3 step10_web.py  and open http://127.0.0.1:5000 to view it.")


if __name__ == "__main__":
    main()