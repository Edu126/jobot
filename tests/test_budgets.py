"""App-wide budgets (REQ-059): voice sessions and Tavily searches.

Locks down: the day and month limits stop charging, env overrides apply,
the kill switch reads as "disabled", and a voice reconnect in the same
practice session is not charged twice (`mark_voice_charged`).

Runs without pytest:
    .venv/bin/python tests/test_budgets.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.llm import usage as llm_usage  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "budgets.db"
        db.init_db(db_path)
        _orig_tx, _orig_connect = db.tx, db.connect
        db.tx = lambda path=db_path: _orig_tx(path)
        db.connect = lambda path=db_path: _orig_connect(path)
        try:
            # Day limit: 3 voice sessions, the 4th is refused, nothing extra charged.
            for _ in range(3):
                _assert(llm_usage.try_charge_budget("voice") is None, "first 3 should pass")
            _assert(llm_usage.try_charge_budget("voice") == "day", "4th should hit the day cap")
            _assert(llm_usage.budget_used("voice") == {"day": 3, "month": 3}, "refusal must not charge")

            # Env override raises the day limit; the month limit then wins.
            os.environ["JOBOT_CAP_VOICE_DAY"] = "50"
            os.environ["JOBOT_CAP_VOICE_MONTH"] = "4"
            _assert(llm_usage.budget_limits("voice") == {"day": 50, "month": 4}, "env override")
            _assert(llm_usage.try_charge_budget("voice") is None, "4th unit fits the month cap")
            _assert(llm_usage.try_charge_budget("voice") == "month", "5th unit hits the month cap")
            del os.environ["JOBOT_CAP_VOICE_DAY"], os.environ["JOBOT_CAP_VOICE_MONTH"]

            # Budgets are separate per kind.
            _assert(llm_usage.try_charge_budget("tavily") is None, "tavily has its own budget")
            kinds = {b["kind"]: b for b in llm_usage.budgets_snapshot()}
            _assert(kinds["tavily"]["used"]["day"] == 1, "snapshot shows tavily use")

            # Kill switch.
            os.environ["LLM_DISABLED"] = "1"
            _assert(llm_usage.try_charge_budget("tavily") == "disabled", "kill switch")
            del os.environ["LLM_DISABLED"]

            # A practice session is charged once, even across reconnects.
            with db.tx(db_path) as conn:
                conn.execute("INSERT INTO interviews (id, resume_hash, company, source, created_at) VALUES (1, 'h', 'Acme', 'pasted_text', 'x')")
                conn.execute("INSERT INTO practice_sessions (id, interview_id, created_at) VALUES (1, 1, 'x')")
            _assert(db.mark_voice_charged(1, db_path) is True, "first connect marks")
            _assert(db.mark_voice_charged(1, db_path) is False, "reconnect does not mark again")
        finally:
            db.tx, db.connect = _orig_tx, _orig_connect
    print("OK — budgets: day/month caps, env override, kill switch, once per session")
    return 0


if __name__ == "__main__":
    sys.exit(main())
