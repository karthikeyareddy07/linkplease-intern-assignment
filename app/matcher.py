"""Keyword Matcher for matching comment text against configured rules."""
import re
from typing import Optional


def matches_keyword(keyword: str, text: Optional[str]) -> bool:
    """
    Checks if a keyword is present in the comment text.
    - Case-insensitive.
    - Matches anywhere in the text.
    - Uses sensible word/token boundary matching to avoid accidental false positives
      (e.g., 'PRICE' matches 'price please 🙏' and 'Can I get the price?' but not 'priceless').
    """
    if not keyword or not text:
        return False

    clean_keyword = keyword.strip()
    if not clean_keyword:
        return False

    # (?<!\w) means not preceded by a word character (a-z, 0-9, _)
    # (?!\w) means not followed by a word character
    # This correctly handles punctuation, emojis, whitespace, start/end of string.
    pattern = rf"(?i)(?<!\w){re.escape(clean_keyword)}(?!\w)"
    return bool(re.search(pattern, text))
