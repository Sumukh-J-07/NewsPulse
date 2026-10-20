"""Transparent financial-headline sentiment scorer (FR-06).

Method ``newspulse-fin-lexicon`` v1.0.0: a VADER-style rule-based scorer using a
small, hand-curated financial lexicon written for this project (inspired by the
positive/negative categories used in finance text research; it is NOT the
Loughran-McDonald dictionary and NOT FinBERT).

Algorithm
---------
1. Lower-case, split hyphens, tokenize into ``[a-z0-9']+``.
2. Match multi-word phrases first (e.g. "beats estimates", "52 week low"), then unigrams.
   Matched phrase tokens are not re-counted as unigrams.
3. A term is negated (polarity flipped) if one of the negators appears within the
   three preceding tokens ("not", "no", "never", "fails to", ...).
4. Each term has weight 1.0; intensifiers ("sharply", "record") in the preceding two
   tokens add 0.5.
5. ``score = (pos - neg) / (pos + neg)`` in [-1, 1]; label = positive if score > 0,
   negative if score < 0, neutral otherwise.
6. ``confidence = min(1, (pos + neg) / 2)``. Headlines with no matched terms are
   deterministically ``neutral`` with score 0.0 and confidence 0.0 and flagged
   ``no_lexicon_match``. Empty/missing headlines return ``None`` (not scored, not
   eligible for aggregation).

Limitations: no context, sarcasm or entity-specific polarity; small vocabulary; a
headline's sentiment is not evidence that a price will move in that direction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MODEL_NAME = "newspulse-fin-lexicon"
MODEL_VERSION = "1.0.0"

POSITIVE_TERMS = {
    "gain", "gains", "gained", "rise", "rises", "rose", "rising", "jump", "jumps", "jumped", "surge", "surges",
    "surged", "soar", "soars", "soared", "rally", "rallies", "rallied", "climb", "climbs", "climbed", "advance",
    "advances", "rebound", "rebounds", "rebounded", "recover", "recovers", "recovery", "beat", "beats", "outperform",
    "outperforms", "outperformed", "upgrade", "upgrades", "upgraded", "profit", "profits", "profitable", "growth",
    "grows", "grew", "expand", "expands", "expanded", "expansion", "strong", "stronger", "strength", "robust",
    "record", "boost", "boosts", "boosted", "win", "wins", "won", "award", "awarded", "approval", "approves",
    "approved", "launch", "launches", "launched", "partnership", "partners", "deal", "acquire", "acquires",
    "dividend", "buyback", "upbeat", "optimistic", "optimism", "bullish", "positive", "improve", "improves",
    "improved", "improvement", "exceed", "exceeds", "exceeded", "accelerate", "accelerates", "momentum",
    "breakthrough", "milestone", "resilient", "higher", "highs", "upside", "raises", "raised", "secures",
    "secured", "contract", "orders", "inflows", "lifts", "lifted", "tops", "topped", "healthy", "solid",
}
NEGATIVE_TERMS = {
    "loss", "losses", "lose", "loses", "lost", "fall", "falls", "fell", "falling", "drop", "drops", "dropped",
    "decline", "declines", "declined", "slump", "slumps", "slumped", "plunge", "plunges", "plunged", "tumble",
    "tumbles", "tumbled", "sink", "sinks", "sank", "slide", "slides", "slid", "crash", "crashes", "miss", "misses",
    "missed", "downgrade", "downgrades", "downgraded", "underperform", "underperforms", "weak", "weaker",
    "weakness", "slowdown", "slows", "slowed", "cut", "cuts", "layoff", "layoffs", "lawsuit", "probe",
    "investigation", "fraud", "penalty", "fine", "fined", "default", "defaults", "debt", "warning", "warns",
    "warned", "concern", "concerns", "risk", "risks", "risky", "bearish", "negative", "pessimistic", "uncertainty",
    "uncertain", "volatile", "volatility", "selloff", "sell", "outflows", "delay", "delays", "delayed", "halt",
    "halts", "halted", "recall", "recalls", "shortfall", "deficit", "lower", "lows", "downside", "pressure",
    "pressured", "disappoint", "disappoints", "disappointing", "disappointed", "fears", "fear", "resign",
    "resigns", "exit", "strike", "outage", "breach", "inflation", "headwinds", "struggles", "struggling",
    "revises", "erodes", "eroded", "drag", "drags", "dragged", "slips", "slipped", "sheds",
}
POSITIVE_PHRASES = {
    "beats estimates", "beat estimates", "above estimates", "record high", "all time high", "52 week high",
    "price target raised", "raises guidance", "raised guidance", "raises outlook", "better than expected",
    "strong demand", "order win", "market share gains",
}
NEGATIVE_PHRASES = {
    "misses estimates", "missed estimates", "below estimates", "52 week low", "price target cut",
    "cuts guidance", "cut guidance", "lowers guidance", "lowered guidance", "worse than expected",
    "weak demand", "profit warning", "profit falls", "under pressure", "rating cut",
}
NEGATORS = {"not", "no", "never", "without", "neither", "nor", "isn't", "wasn't", "doesn't", "didn't",
            "won't", "can't", "cannot", "fails", "failed", "unlikely"}
INTENSIFIERS = {"sharply", "strongly", "significantly", "steeply", "record", "massive", "huge", "big", "heavy"}

_TOKEN_RX = re.compile(r"[a-z0-9']+")
_PHRASES = sorted(
    [(tuple(p.split()), 1) for p in POSITIVE_PHRASES] + [(tuple(p.split()), -1) for p in NEGATIVE_PHRASES],
    key=lambda item: -len(item[0]),
)


@dataclass(frozen=True)
class SentimentResult:
    label: str
    score: float
    confidence: float
    positive_hits: tuple[str, ...]
    negative_hits: tuple[str, ...]
    flags: tuple[str, ...]
    model: str = MODEL_NAME
    version: str = MODEL_VERSION


def tokenize(text: str) -> list[str]:
    return _TOKEN_RX.findall(text.lower().replace("-", " ").replace("’", "'"))


def score_headline(headline: str | None) -> SentimentResult | None:
    if headline is None or not headline.strip():
        return None
    tokens = tokenize(headline)
    if not tokens:
        return None
    used = [False] * len(tokens)
    hits: list[tuple[int, int, str]] = []  # (position, polarity, term)
    for phrase, polarity in _PHRASES:
        n = len(phrase)
        for i in range(len(tokens) - n + 1):
            if tuple(tokens[i:i + n]) == phrase and not any(used[i:i + n]):
                for j in range(i, i + n):
                    used[j] = True
                hits.append((i, polarity, " ".join(phrase)))
    for i, tok in enumerate(tokens):
        if used[i]:
            continue
        if tok in POSITIVE_TERMS:
            hits.append((i, 1, tok))
        elif tok in NEGATIVE_TERMS:
            hits.append((i, -1, tok))

    pos = neg = 0.0
    pos_terms: list[str] = []
    neg_terms: list[str] = []
    flags: list[str] = []
    for i, polarity, term in hits:
        window = tokens[max(0, i - 3):i]
        if any(w in NEGATORS or w.endswith("n't") for w in window):
            polarity = -polarity
            flags.append(f"negated:{term}")
        weight = 1.0 + (0.5 if any(w in INTENSIFIERS for w in tokens[max(0, i - 2):i]) else 0.0)
        if polarity > 0:
            pos += weight
            pos_terms.append(term)
        else:
            neg += weight
            neg_terms.append(term)

    total = pos + neg
    if total == 0:
        return SentimentResult("neutral", 0.0, 0.0, (), (), ("no_lexicon_match",))
    score = (pos - neg) / total
    label = "positive" if score > 0 else "negative" if score < 0 else "neutral"
    if label == "neutral":
        flags.append("balanced_terms")
    return SentimentResult(label, round(score, 6), round(min(1.0, total / 2.0), 6),
                           tuple(pos_terms), tuple(neg_terms), tuple(flags))
