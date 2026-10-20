"""Fixed-taxonomy expense categorization for line items (docs/06_schema_api.md §6.1.3).

The taxonomy is deliberately small and closed: it is a demo feature, not a
general-purpose merchant classifier. Unknown descriptions fall back to
``OTHER`` so every row has a stable, queryable category.
"""

from __future__ import annotations

from typing import Final

EXPENSE_CATEGORIES: Final = ("F&B", "HARDWARE", "WORKSHOP", "RETAIL", "OTHER")
DEFAULT_CATEGORY: Final = "OTHER"

CATEGORY_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "F&B": (
        "kopi",
        "teh",
        "makan",
        "nasi",
        "roti",
        "cafe",
        "restoran",
        "food",
        "drink",
        "ayam",
        "mee",
        "minum",
    ),
    "HARDWARE": (
        "pipe",
        "pvc",
        "screw",
        "bolt",
        "nail",
        "hardware",
        "paint",
        "wire",
        "cable",
        "tool",
        "spark plug",
        "spark",
    ),
    "WORKSHOP": (
        "oil",
        "minyak",
        "tyre",
        "tayar",
        "servis",
        "service",
        "repair",
        "labour",
        "labor",
        "upah",
        "workshop",
        "bengkel",
        "spare",
        "gear",
    ),
    "RETAIL": (
        "baju",
        "shirt",
        "shoe",
        "kasut",
        "retail",
        "store",
        "kedai",
        "supermarket",
        "grocer",
    ),
}


def classify_expense(description: str | None) -> str:
    """Map a line description onto a category, defaulting to ``OTHER``.

    Keywords are matched as substrings on a case-folded description. The dict
    order above decides ties deterministically (F&B first), so the same input
    always produces the same category.
    """
    text = (description or "").casefold()
    for category, words in CATEGORY_KEYWORDS.items():
        if any(word in text for word in words):
            return category
    return DEFAULT_CATEGORY


__all__ = [
    "CATEGORY_KEYWORDS",
    "DEFAULT_CATEGORY",
    "EXPENSE_CATEGORIES",
    "classify_expense",
]
