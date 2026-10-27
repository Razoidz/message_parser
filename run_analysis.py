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
from step3_database import create_chat, create_tables, save_messages
from step4_prepare_text import load_messages, make_chunks
from step5_extract import fake_model
from step6_real_model import claude_model, extract_all
from step7_save_results import create_analysis_tables, save_results
from step8_synthesize import fake_synth_model, synthesize
from step9_save_analysis import add_supports_column, create_synthesis_tables, save_analysis
from step11_run_status import add_status_columns, friendly_error, set_status, start_run


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


def main(argv=None, models=None):
    ap = argparse.ArgumentParser(description="Analyze a WhatsApp chat export.")
    ap.add_argument("file", help="path to the exported chat .txt file")
    ap.add_argument("--title", default=None)
    ap.add_argument("--chunk-size", type=int, default=150)
    ap.add_argument("--overlap", type=int, default=10)
    ap.add_argument("--fake", action="store_true", help="use canned replies instead of the real model")
    ap.add_argument("--i-have-consent", action="store_true", dest="consent",
                    help="confirm you have the right to analyze this chat")
    args = ap.parse_args(argv)

    # Checks that must pass BEFORE we touch the database
    if not args.consent:
        sys.exit("Refusing to run: confirm you have the right to analyze this chat with --i-have-consent")
    if not os.path.exists(args.file):
        sys.exit(f"File not found: {args.file}")
    extract_fn, synth_fn = models or choose_models(args.fake)

    print("[1/6] Parsing the file")
    parsed = parse_file(args.file)
    if not parsed:
        sys.exit("No messages found. Check the file format.")
    print(f"      {len(parsed)} messages")

    conn = sqlite3.connect("chat.db")
    create_tables(conn)
    create_analysis_tables(conn)
    add_supports_column(conn)
    add_status_columns(conn)
    create_synthesis_tables(conn)

    print("[2/6] Saving messages")
    chat_id = create_chat(conn, args.title)
    save_messages(conn, chat_id, parsed)
    run_id = start_run(conn, chat_id)  # status: running

    try:
        run_pipeline(conn, chat_id, run_id, extract_fn, synth_fn, args.chunk_size, args.overlap)
    except KeyboardInterrupt:
        set_status(conn, run_id, "failed", "Cancelled by user")
        sys.exit(f"\nCancelled. Run {run_id} was marked as failed.")
    except Exception as e:
        message = friendly_error(e)
        set_status(conn, run_id, "failed", message)
        sys.exit(f"\nAnalysis failed: {message}\n(Run {run_id} was marked as failed.)")

    set_status(conn, run_id, "done")
    print(f"\nDone. Chat {chat_id}, analysis run {run_id}.")
    print("Run  python3 step10_web.py  and open http://127.0.0.1:5000 to view it.")


if __name__ == "__main__":
    main()