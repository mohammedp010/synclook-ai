"""Accessory limits used by ``tools.accessory_rules``."""

from __future__ import annotations

__all__ = ["MAX_ACCESSORIES_PER_LOOK"]

MAX_ACCESSORIES_PER_LOOK = 2
"""Accessories per outfit, counted apart from the garment cap.

Two is the smallest number where coordination means anything: with one
accessory, "metals agree" and "one statement piece" are true by default."""
