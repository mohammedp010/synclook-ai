"""Product-relevance thresholds — where Jev's product nouls become keep or drop.

Same contract as ``occasion_policy``: the questions live in
``services.product_judge``, and every number that turns a probability into a
decision lives here, tied to the model it was set against.
"""

from __future__ import annotations

from backend.core.occasion_policy import CALIBRATED_FOR

__all__ = ["CALIBRATED_FOR", "PRODUCT_THRESHOLD"]

PRODUCT_THRESHOLD = 0.5
"""Bar each of the three atomic nouls (item, colour, buyer) must clear.

A product is kept only when all three do, and survivors are ranked by the
product of the three probabilities (reference §7.9: sort by the raw
probability). 0.5 is the noul's midpoint, chosen before any result was seen;
``evaluation/product_relevance.py`` prints a sweep."""
