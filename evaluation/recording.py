"""Persisting evaluation results — one history table, one code path.

Every suite answers the same question in a different way: did this commit make
the system better or worse? Keeping them in one table with a ``suite`` label
means the trend for any of them is a single query, and the admin dashboard does
not need to learn a new shape each time a suite is added.

Recording is always best effort. An eval that fails because the database is
down would be an eval that reports on the database rather than on the model, so
failures here are warned about and swallowed — the metrics have already been
printed by the time this runs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def git_sha() -> str | None:
    """The commit these numbers describe, or None outside a git checkout."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=5,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


async def record_run(suite: str, *, num_cases: int, metrics: dict[str, Any]) -> None:
    """Persist one suite's summary as an ``EvaluationRun`` row."""
    from backend.db.base import Base
    from backend.db.session import async_session_factory, engine
    from backend.models.records import EvaluationRun

    # Evals are run against throwaway databases as often as against the real
    # one, so the tables are created if absent rather than assumed.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        run = EvaluationRun(suite=suite, git_sha=git_sha(), num_cases=num_cases, metrics=metrics)
        session.add(run)
        await session.commit()
    print(f"recorded EvaluationRun (suite={suite}, git_sha={run.git_sha}, id={run.id})")


async def record_if_asked(enabled: bool, suite: str, *, num_cases: int, metrics: dict[str, Any]) -> None:
    """``record_run`` behind the ``--record`` flag, never fatal."""
    if not enabled:
        return
    try:
        await record_run(suite, num_cases=num_cases, metrics=metrics)
    except Exception as exc:
        print(f"warning: could not record {suite} run: {exc}", file=sys.stderr)
