"""Entity linking (FR-05): associate headlines with watchlist assets.

Precedence per asset: provider tag > ticker symbol > strong alias > weak alias.

* Strong aliases (full company names) and exact upper-case ticker symbols link directly.
* Weak aliases (short names such as "Reliance" or "HDFC") link only when no configured
  conflicting entity ("Reliance Power", "HDFC Life") appears in the headline. If a
  conflict appears and no strong evidence exists, the link is stored as ``ambiguous``
  and is excluded from per-asset aggregation (kept for review).
* Provider tags are trusted unless the headline names a conflicting entity without any
  strong alias for the tagged asset, in which case the link is ``ambiguous``.
* Unknown provider tags are reported, never forced onto an asset.

Links are many-to-many: one headline can link to several assets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..settings import AssetConfig


@dataclass(frozen=True)
class LinkResult:
    asset_id: str
    method: str  # provider_tag | ticker | strong_alias | weak_alias
    status: str  # linked | ambiguous
    matched_text: str | None
    reason: str


def _phrase_regex(phrase: str, case_sensitive: bool = False) -> re.Pattern:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", flags)


def _symbol(ticker: str) -> str:
    return ticker.split(".")[0].lstrip("^").upper()


class EntityLinker:
    def __init__(self, assets: Sequence[AssetConfig]):
        self.assets = list(assets)
        self._tag_map: dict[str, str] = {}
        self._compiled = {}
        for a in self.assets:
            for tag in {a.asset_id.upper(), a.ticker.upper(), _symbol(a.ticker)}:
                self._tag_map[tag] = a.asset_id
            symbol = _symbol(a.ticker) if len(_symbol(a.ticker)) >= 3 else None
            self._compiled[a.asset_id] = {
                "ticker": _phrase_regex(symbol, case_sensitive=True) if symbol and symbol.isalpha() else None,
                "strong": [(s, _phrase_regex(s)) for s in a.strong_aliases],
                "weak": [(w, _phrase_regex(w)) for w in a.weak_aliases],
                "conflicts": [(c, _phrase_regex(c)) for c in a.conflicts],
            }

    def resolve_tag(self, tag: str) -> str | None:
        t = str(tag).strip().upper()
        return self._tag_map.get(t) or self._tag_map.get(_symbol(t))

    def link(self, headline: str | None, provider_tags: Iterable[str] = ()) -> tuple[list[LinkResult], list[str]]:
        text = headline or ""
        notes: list[str] = []
        tagged: set[str] = set()
        for tag in provider_tags or ():
            resolved = self.resolve_tag(tag)
            if resolved:
                tagged.add(resolved)
            else:
                notes.append(f"unknown_provider_tag:{tag}")

        results: list[LinkResult] = []
        for a in self.assets:
            c = self._compiled[a.asset_id]
            conflict = next((name for name, rx in c["conflicts"] if rx.search(text)), None)
            ticker_hit = c["ticker"].search(text).group(0) if c["ticker"] and c["ticker"].search(text) else None
            strong_hit = next((m.group(0) for _, rx in c["strong"] if (m := rx.search(text))), None)
            # A weak alias that is merely part of a conflicting entity name does not count by itself.
            weak_hit = None
            for name, rx in c["weak"]:
                for m in rx.finditer(text):
                    covered = any(
                        cm.start() <= m.start() and m.end() <= cm.end()
                        for _, crx in c["conflicts"] for cm in crx.finditer(text)
                    )
                    if not covered:
                        weak_hit = m.group(0)
                        break
                if weak_hit:
                    break
            weak_in_conflict = conflict is not None and any(rx.search(text) for _, rx in c["weak"])

            if a.asset_id in tagged:
                if conflict and not (strong_hit or ticker_hit):
                    results.append(LinkResult(a.asset_id, "provider_tag", "ambiguous", conflict,
                                              f"provider tag but headline names conflicting entity '{conflict}'"))
                else:
                    results.append(LinkResult(a.asset_id, "provider_tag", "linked", None, "trusted provider tag"))
            elif ticker_hit:
                results.append(LinkResult(a.asset_id, "ticker", "linked", ticker_hit, "exact ticker symbol"))
            elif strong_hit:
                results.append(LinkResult(a.asset_id, "strong_alias", "linked", strong_hit, "full company name"))
            elif weak_hit and not conflict:
                results.append(LinkResult(a.asset_id, "weak_alias", "linked", weak_hit, "short name, no conflicting entity"))
            elif weak_hit or weak_in_conflict:
                results.append(LinkResult(a.asset_id, "weak_alias", "ambiguous", weak_hit or conflict,
                                          f"short name appears with conflicting entity '{conflict}'"))
        return results, notes
