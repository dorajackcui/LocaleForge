from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .config.tasks import STATUS_EMPTY, STATUS_SUSPECT, TaskConfig

FRENCH_MARKERS = {
    "alors",
    "au",
    "aucun",
    "aucune",
    "aux",
    "avec",
    "ce",
    "cet",
    "cette",
    "comme",
    "dans",
    "de",
    "des",
    "du",
    "elle",
    "en",
    "entre",
    "est",
    "et",
    "fait",
    "il",
    "ils",
    "je",
    "la",
    "le",
    "les",
    "leur",
    "lui",
    "mais",
    "mon",
    "ne",
    "ou",
    "par",
    "pas",
    "plus",
    "pour",
    "que",
    "qui",
    "sa",
    "sans",
    "se",
    "ses",
    "son",
    "sont",
    "sur",
    "te",
    "toi",
    "tres",
    "une",
    "un",
    "vers",
    "votre",
    "vos",
}

ENGLISH_MARKERS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "there",
    "these",
    "this",
    "to",
    "was",
    "were",
    "with",
}

FRENCH_PREFIXES = ("l'", "d'", "j'", "n'", "c'", "s'", "m'", "t'", "qu'")
TOKEN_RE = re.compile(r"[A-Za-z\u00C0-\u00FF]+(?:'[A-Za-z\u00C0-\u00FF]+)?")
ASCII_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
ACCENT_RE = re.compile(
    r"[\u00E0\u00E2\u00E4\u00E6\u00E7\u00E9\u00E8\u00EA\u00EB\u00EE\u00EF\u00F4\u0153\u00F9\u00FB\u00FC\u00FF]",
    re.IGNORECASE,
)


@dataclass
class RuleDecision:
    status: Optional[str]
    reason: str


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def analyze_text(text: str) -> RuleDecision:
    if not text:
        return RuleDecision(STATUS_EMPTY, "empty cell")

    tokens = TOKEN_RE.findall(text)
    if not tokens:
        return RuleDecision(None, "non-empty text without latin tokens")

    lowered_tokens = [token.lower() for token in tokens]
    stripped_tokens = [token.strip("'") for token in lowered_tokens]

    english_hits = sum(1 for token in stripped_tokens if token in ENGLISH_MARKERS)
    french_hits = sum(1 for token in stripped_tokens if token in FRENCH_MARKERS)
    french_prefix_hits = sum(1 for token in lowered_tokens if token.startswith(FRENCH_PREFIXES))
    accented_hits = len(ACCENT_RE.findall(text))
    ascii_words = ASCII_WORD_RE.findall(text)
    ascii_ratio = len(ascii_words) / max(len(tokens), 1)
    token_count = len(tokens)

    if english_hits >= 2 and french_hits == 0 and french_prefix_hits == 0:
        return RuleDecision(STATUS_SUSPECT, "multiple english markers")

    if (
        english_hits >= 1
        and token_count >= 5
        and french_hits == 0
        and french_prefix_hits == 0
        and accented_hits == 0
        and ascii_ratio > 0.8
    ):
        return RuleDecision(STATUS_SUSPECT, "english-heavy sentence")

    if french_hits >= 1 or french_prefix_hits >= 1 or accented_hits >= 1:
        return RuleDecision(None, "french-looking text requires model review")

    return RuleDecision(None, "fallback to model review")


def get_rule_decision(task_config: TaskConfig, text: str) -> RuleDecision:
    if not text:
        return RuleDecision(STATUS_EMPTY, "empty cell")
    if task_config.use_rule_precheck:
        return analyze_text(text)
    return RuleDecision(None, "non-empty text requires model review")
