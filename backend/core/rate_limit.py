"""Per-visitor rate limits, by client IP.

Every route gets ``settings.rate_limit`` (``SlowAPIMiddleware`` in ``create_app``); the paid routes add a
tighter limit with ``@limiter.limit``. The MCP endpoint is a plain ASGI mount that slowapi cannot see, so it
checks ``mcp_allowed`` itself. The client IP is the real visitor's only when uvicorn trusts the host's proxy
headers (``--forwarded-allow-ips``, set in the Dockerfile).

shortcut: counters live in this process's memory, so a restart (or the free host's sleep) resets them and two
workers count apart. The money is held by the daily caps in Postgres (``core/budget.py``), not by these.
"""

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.config import get_settings

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])

_mcp = FixedWindowRateLimiter(MemoryStorage())


def mcp_allowed(client_ip: str) -> bool:
    """Count one MCP request for this IP; False once it is over ``settings.rate_limit``."""
    return _mcp.hit(parse(settings.rate_limit), "mcp", client_ip)
