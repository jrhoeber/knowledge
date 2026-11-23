"""American spelling for the vocabulary bank.

Wiktionary has entries for both spellings of many words, but which one holds the
definitions varies (color but plough, theater but jewellery), and definitions are
written in either. The bank uses American spelling throughout: headwords, definitions,
examples and related words.

Source
------
VarCon (Variant Conversion Info) by Kevin Atkinson and Benjamin Titze, part of SCOWL,
http://wordlist.aspell.net/varcon/ (downloaded once into `.cache/spelling/`; the
copyright notice is in the README next to it). Each line lists the spellings of one
word with where each is used, checked against Merriam-Webster and Oxford dictionaries:

    A Cv: theater / B C: theatre               (A: American, B: British, v: variant)
    A C: tire / B: tyre | wheel                (tire is also "exhausted" everywhere)

Rules
-----
* A spelling is replaced if VarCon never lists it as a preferred American spelling
  (A, or A. for an equal variant) and pairs it with exactly one that is. So theatre
  becomes theater and storey becomes story, but axe (equal to ax), dialogue (dialog
  is a variant) and disc (preferred for some meanings) stay.
* Clusters VarCon marks as verified are used as they are. The others, mostly rare
  words with some mechanical errors (ret/ert, dure/duer), count only when Wiktionary
  links the two spellings too (`vocabulary.use_american_spelling`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import norms

CACHE = Path(__file__).resolve().parent / ".cache" / "spelling"
# Pinned so the build is reproducible: the v1 branch of en-wl/wordlist, which still
# ships varcon.txt.
SOURCES = {
    "varcon.txt": "https://raw.githubusercontent.com/en-wl/wordlist/b22230cc5250887737fdefe9ca4c9d9d01230eaa"
    "/varcon/varcon.txt",
    "README": "https://raw.githubusercontent.com/en-wl/wordlist/b22230cc5250887737fdefe9ca4c9d9d01230eaa"
    "/varcon/README",
}
AMERICAN_TAGS = {"A", "A."}
SPELLING_RE = re.compile(r"[a-z]+(?:-[a-z]+)*")
TOKEN_RE = re.compile(r"[A-Za-z]+")


def ensure_downloaded() -> None:
    norms.download(SOURCES, CACHE)


@dataclass(frozen=True)
class Variants:
    """Non-American spelling -> its preferred American spelling."""

    verified: dict[str, str]
    unverified: dict[str, str]
    _others: dict[str, set[str]] = field(init=False, repr=False, compare=False)

    def others(self, word: str) -> set[str]:
        """Every spelling VarCon pairs with `word`, in either direction."""
        return self._others.get(word, set())

    def __post_init__(self) -> None:
        others: dict[str, set[str]] = {}
        for table in (self.verified, self.unverified):
            for spelling, american in table.items():
                others.setdefault(spelling, set()).add(american)
                others.setdefault(american, set()).add(spelling)
        object.__setattr__(self, "_others", others)


def load_variants(path: Path = CACHE / "varcon.txt") -> Variants:
    american: set[str] = set()
    targets: dict[str, set[str]] = {}
    verified: set[str] = set()
    cluster_verified = False
    for raw in path.read_text(encoding="latin-1").splitlines():
        if raw.startswith("# "):
            cluster_verified = "<verified>" in raw
            continue
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        spellings = []
        for part in line.split(" | ", 1)[0].split(" / "):
            tags, _, word = part.partition(": ")
            spellings.append(({t for t in tags.split() if not t.isdigit()}, word.strip()))
        preferred = [w for tags, w in spellings if tags & AMERICAN_TAGS]
        for tags, word in spellings:
            if tags & AMERICAN_TAGS:
                american.add(word)
            elif len(preferred) == 1:
                targets.setdefault(word, set()).add(preferred[0])
                if cluster_verified:
                    verified.add(word)
    table = {
        word: next(iter(found))
        for word, found in targets.items()
        if word not in american and len(found) == 1
        and SPELLING_RE.fullmatch(word) and SPELLING_RE.fullmatch(next(iter(found)))
    }
    return Variants(
        verified={w: a for w, a in table.items() if w in verified},
        unverified={w: a for w, a in table.items() if w not in verified},
    )


class Americanizer:
    """Rewrites words and text in American spelling. `names` are spellings with a
    capitalized Wiktionary entry (Chile, Matt, Louvre): capitalized, they are left alone."""

    def __init__(self, spellings: dict[str, str], names: set[str]):
        self.spellings = spellings
        self.names = names

    def word(self, word: str) -> str:
        return self.spellings.get(word, word)

    def text(self, text: str | None) -> str | None:
        if not text:
            return text

        def replace(match: re.Match) -> str:
            token = match.group()
            lower = token.lower()
            american = self.spellings.get(lower)
            if american is None:
                return token
            if token == lower:
                return american
            if token == token.upper() and len(token) > 1:
                return american.upper()
            if token[0].isupper() and token[1:] == lower[1:] and lower not in self.names:
                return american[0].upper() + american[1:]
            return token

        return TOKEN_RE.sub(replace, text)
