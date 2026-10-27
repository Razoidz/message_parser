import json
import sqlite3

from flask import Flask, abort, render_template_string

from step9_save_analysis import get_evidence
from step11_run_status import add_status_columns

app = Flask(__name__)


def db():
    conn = sqlite3.connect("chat.db")
    add_status_columns(conn)  # make sure old databases get the new columns
    return conn


def as_messages(rows):
    return [{"ref": f"msg_{seq}", "name": name, "text": text} for seq, name, text in rows]


def load_run(conn, run_id):
    """Gather everything the page needs for one analysis run, or None if it doesn't exist."""
    run = conn.execute("""
        SELECT r.id, c.title, r.created_at, r.status, r.error
        FROM analysis_runs r JOIN chats c ON c.id = r.chat_id
        WHERE r.id = ?
    """, (run_id,)).fetchone()
    if run is None:
        return None

    timeline = []
    for tid, when, what in conn.execute(
        "SELECT id, when_text, what FROM timeline_entries WHERE run_id = ? ORDER BY position", (run_id,)
    ):
        timeline.append({"when": when, "what": what,
                         "evidence": as_messages(get_evidence(conn, "timeline", tid, True))})

    roles = []
    role_rows = conn.execute("""
        SELECT r.id, p.name, r.role, r.confidence, r.reasoning
        FROM role_findings r JOIN participants p ON p.id = r.participant_id
        WHERE r.run_id = ?
    """, (run_id,)).fetchall()
    for rid, name, role, confidence, reasoning in role_rows:
        roles.append({
            "name": name, "role": role, "confidence": confidence, "reasoning": reasoning,
            "support": as_messages(get_evidence(conn, "role", rid, True)),
            "counter": as_messages(get_evidence(conn, "role", rid, False)),
        })

    summary = conn.execute(
        "SELECT narrative, limitations FROM summaries WHERE run_id = ?", (run_id,)
    ).fetchone()

    return {
        "id": run[0], "title": run[1], "created_at": run[2], "status": run[3], "error": run[4],
        "timeline": timeline, "roles": roles,
        "narrative": summary[0] if summary else None,
        "limitations": json.loads(summary[1]) if summary else [],
    }


STYLE = """
<style>
  body { font-family: system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #222; }
  h1, h2 { line-height: 1.2; }
  .card { border: 1px solid #ddd; border-radius: 10px; padding: 1rem; margin: 1rem 0; }
  .badge { font-size: .8rem; padding: .1rem .6rem; border-radius: 99px; background: #eee; }
  .high { background: #cfe9cf; } .medium { background: #fbe9b7; } .low { background: #f4cccc; }
  .msg { white-space: pre-wrap; margin: .3rem 0; padding: .4rem .6rem; background: #f6f6f6; border-radius: 6px; font-size: .9rem; }
  .counter .msg { background: #fdeeee; }
  .done { background: #cfe9cf; } .running { background: #fbe9b7; } .failed { background: #f4cccc; }
  .note { color: #666; font-size: .9rem; }
  summary { cursor: pointer; color: #345; }
</style>
"""

HOME = STYLE + """
<h1>Chat analyses</h1>
{% if runs %}
  {% for id, title, created, status in runs %}
    <div class="card"><a href="/run/{{ id }}">Run {{ id }}: {{ title or "Untitled chat" }}</a>
    <span class="badge {{ status }}">{{ status }}</span>
    <div class="note">{{ created }}</div></div>
  {% endfor %}
{% else %}
  <p>No analyses yet. Run step9_save_analysis.py first.</p>
{% endif %}
"""

RUN = STYLE + """
<p><a href="/">&larr; All analyses</a></p>
<h1>{{ run.title or "Untitled chat" }}</h1>
<p class="note">Findings are what the messages suggest, not verdicts. Open any claim to check the messages behind it.</p>

{% if run.status == "failed" %}
  <div class="card failed"><strong>This analysis failed.</strong> {{ run.error }}</div>
{% elif run.status == "running" %}
  <div class="card running">This analysis is still running, or was interrupted.</div>
{% endif %}

<h2>Roles</h2>
{% for r in run.roles %}
  <div class="card">
    <strong>{{ r.name }}</strong>: {{ r.role }}
    <span class="badge {{ r.confidence }}">{{ r.confidence }} confidence</span>
    <p>{{ r.reasoning }}</p>
    <details><summary>Supporting messages ({{ r.support|length }})</summary>
      {% for m in r.support %}<div class="msg">{{ m.ref }} &middot; {{ m.name }}: {{ m.text }}</div>{% endfor %}
    </details>
    <details class="counter"><summary>Counter-evidence ({{ r.counter|length }})</summary>
      {% for m in r.counter %}<div class="msg">{{ m.ref }} &middot; {{ m.name }}: {{ m.text }}</div>{% endfor %}
    </details>
  </div>
{% else %}
  <p>No role findings for this run.</p>
{% endfor %}

<h2>Timeline</h2>
{% for t in run.timeline %}
  <div class="card">
    <strong>{{ t.when }}</strong>: {{ t.what }}
    <details><summary>Evidence ({{ t.evidence|length }})</summary>
      {% for m in t.evidence %}<div class="msg">{{ m.ref }} &middot; {{ m.name }}: {{ m.text }}</div>{% endfor %}
    </details>
  </div>
{% endfor %}

<h2>How it unfolded</h2>
{% if run.narrative %}<p>{{ run.narrative }}</p>{% else %}<p>No narrative for this run.</p>{% endif %}

<h2>Limitations</h2>
<ul>{% for item in run.limitations %}<li>{{ item }}</li>{% endfor %}</ul>
"""


@app.route("/")
def home():
    conn = db()
    runs = conn.execute("""
        SELECT r.id, c.title, r.created_at, r.status
        FROM analysis_runs r JOIN chats c ON c.id = r.chat_id
        ORDER BY r.id DESC
    """).fetchall()
    return render_template_string(HOME, runs=runs)


@app.route("/run/<int:run_id>")
def run_page(run_id):
    run = load_run(db(), run_id)
    if run is None:
        abort(404)
    return render_template_string(RUN, run=run)


if __name__ == "__main__":
    app.run(debug=True)