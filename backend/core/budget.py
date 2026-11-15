"""Daily caps on paid calls, counted in ``kv_cache`` (one row per name per UTC day).

Every paid entry point spends one unit first: product searches (``toolkit.search_products`` and
``POST /shop/search``), photo uploads, chat turns and outfit explanations. The caps are in
``Settings`` (``*_daily_cap``). Over a cap the app answers 429 "demo budget used for today";
the rule-only parts (outfits, gaps, the closet) keep working.
"""

from __future__ import annotations

import datetime as dt

from backend.core.exceptions import SynclookError
from backend.services.cache import KvCache

_KEEP_SECONDS = 2 * 24 * 3600  # a day's counter is useless after that day


class BudgetExceededError(SynclookError):
    pass


def seconds_to_reset() -> int:
    """Seconds until the next UTC midnight, when every cap starts again (the 429's Retry-After)."""
    now = dt.datetime.now(dt.UTC)
    return int((dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(), dt.UTC) - now).total_seconds())


async def spend(cache: KvCache, name: str, daily_limit: int, today: dt.date | None = None) -> int:
    """Count one paid call against today's cap and return how many are left today.

    Raises ``BudgetExceededError`` (and counts nothing) once *daily_limit* calls were made today.
    """
    day = today or dt.datetime.now(dt.UTC).date()
    key = f"budget:{name}:{day.isoformat()}"
    # shortcut: read-then-write, so two requests at the same instant can both take the last slot;
    # use one UPDATE ... RETURNING if the cap must be exact under concurrent traffic.
    used = int(await cache.get(key) or 0)
    if used >= daily_limit:
        raise BudgetExceededError(
            f"Demo budget used for today: all {daily_limit} {name.replace('_', ' ')} for today are spent "
            "(it resets at 00:00 UTC). Outfits from the closet (POST /outfits with an exact occasion) and "
            "gap suggestions (POST /shop/gaps) still work."
        )
    await cache.set(key, used + 1, _KEEP_SECONDS)
    return daily_limit - used - 1
