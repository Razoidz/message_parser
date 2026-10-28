from step7_save_results import create_run


def add_status_columns(conn):
    """Migration: give analysis_runs a status ('running', 'done', 'failed') and an error message."""
    columns = [row[1] for row in conn.execute("PRAGMA table_info(analysis_runs)")]
    if not columns:
        return  # the table does not exist yet, nothing to change
    if "status" not in columns:
        # Runs saved before this change finished successfully, so they default to 'done'
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN status TEXT NOT NULL DEFAULT 'done'")
    if "error" not in columns:
        conn.execute("ALTER TABLE analysis_runs ADD COLUMN error TEXT")
    conn.commit()


def set_status(conn, run_id, status, error=None):
    conn.execute(
        "UPDATE analysis_runs SET status = ?, error = ? WHERE id = ?",
        (status, error, run_id),
    )
    conn.commit()


def start_run(conn, chat_id):
    run_id = create_run(conn, chat_id)
    set_status(conn, run_id, "running")
    return run_id


def friendly_error(exc):
    """Turn an exception into a message a person can act on."""
    name = type(exc).__name__
    text = str(exc)
    lowered = text.lower()
    if "credit balance" in lowered:
        return ("Your Anthropic API credit balance is too low. "
                "Add credits under Plans & Billing, then run again.")
    if name == "AuthenticationError" or "invalid x-api-key" in lowered:
        return "The API key was rejected. Check that ANTHROPIC_API_KEY is set correctly."
    if name == "RateLimitError":
        return "Rate limit reached. Wait a minute and run again."
    if name in ("APIConnectionError", "APITimeoutError"):
        return "Could not reach the Anthropic API. Check your internet connection."
    return f"{name}: {text[:300]}"
