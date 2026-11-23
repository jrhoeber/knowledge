"""Finds meanings that are obvious from a more common word they are built on.

A meaning is *transparent* when the word is a regular derivative of a more common
base word (un-, non-, re-, -ness, -ly, -less, -able, -er and so on, or a hyphenated
compound) and its definition just restates the base: "unmusical: Not musical",
"believably: In a believable way", "dreariness: The characteristic of being dreary",
"stabber: One who stabs", "rootless: Having no roots". Anyone who knows the base
knows these, and the correct option gives itself away by repeating the prompt.

Both parts are required. "unprecedented" is built on "precedent", but its definition
("Never before seen, done, or experienced; without precedent") says something new
first, so it stays; "temperance" looks like "temper" + "-ance", but its definition
does not restate "temper". Borderline cases go the other way too: "disinterested:
Having no interest or stake in the outcome" is dropped.
"""

from __future__ import annotations

import re
from os.path import commonprefix

PREFIXES = (
    "counter", "hyper", "inter", "micro", "multi", "pseudo", "super", "trans", "ultra", "extra",
    "anti", "auto", "fore", "mega", "mini", "over", "post", "self", "semi", "under", "dis", "mis",
    "mid", "non", "out", "pre", "sub", "tri", "co", "de", "il", "im", "in", "ir", "re", "un", "up",
)
# Suffix -> endings to put back to rebuild the base ("happiness" -> "happi" -> "happy").
SUFFIXES = {
    "ization": ("ize",), "isation": ("ise",), "ability": ("able",), "ibility": ("ible",),
    "ically": ("ic", "ical"), "ation": ("ate", "e", "", "ize"), "ness": ("", "y"), "less": ("", "y"),
    "ment": ("",), "ship": ("",), "hood": ("",), "like": ("",), "wise": ("",), "wards": ("",),
    "ward": ("",), "able": ("", "e", "ate"), "ible": ("", "e"), "ical": ("ic", "y", ""),
    "ally": ("al", ""), "ful": ("", "y"), "osity": ("ous",), "ility": ("le",), "ity": ("", "e", "ous"),
    "ancy": ("ant",), "ency": ("ent",), "ance": ("ant",), "ence": ("ent",),
    "ism": ("", "e", "y"), "ist": ("", "e", "y"), "ish": ("", "e"), "ize": ("", "e", "y"), "ise": ("", "e"), "ive": ("e", ""), "ous": ("", "e"),
    "ery": ("", "e"), "dom": ("",), "ing": ("", "e"), "ily": ("y",), "ly": ("", "le"), "ic": ("", "y"),
    "al": ("", "e"), "er": ("", "e"), "ed": ("", "e"), "en": ("",), "y": ("", "e"),
}
MIN_BASE_LENGTH = 3
INFLECTIONS = {"ed": ("", "e"), "ing": ("", "e"), "es": ("",), "s": ("",)}
NUMBER_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand",
}

# Openers of a definition that restates its base: the next content word must be the base.
_OPENERS = [
    r"not(?: being| having)?",
    r"(?:in|with) an?(?=(?: [a-z-]+){1,4} (?:manner|way|fashion|style)\b)",
    r"in (?:the )?(?:manner|way|style|fashion) of",
    r"(?:the )?(?:[a-z]+ (?:or|and) )?(?:state|quality|condition|fact|property|characteristic|practice|result|"
    r"degree|act|process|action|instance|habit|ability|capacity|position|status|office|rank|period|feeling|"
    r"trait|tendency|extent|study|science|theory|doctrine|belief) (?:or [a-z]+ )?of(?: being| having)?",
    r"(?:an? |the |one )?(?:person|one|someone|somebody|something|thing|device|machine|tool|instrument|agent|"
    r"member|follower|adherent|supporter|practitioner|specialist|expert|player|worker|maker|user)"
    r"(?: or [a-z]+)? (?:who|that|which)(?: is| are)?",
    r"without", r"lacking(?: in)?", r"having no", r"with no", r"free (?:of|from)", r"devoid of",
    r"(?:somewhat|rather|slightly|fairly|quite|very|excessively|overly|too|extremely|highly)",
    r"(?:able|capable|possible|easy|liable|fit|suitable) (?:to be|of being)", r"that (?:can|may|could) be",
    r"(?:of,? (?:or )?)?(?:relating|pertaining|related|belonging|referring) to,?(?: or (?:characteristic|typical) of,?)?",
    r"(?:characteri[sz]ed by|characteristic of|typical of|full of|resembling|like|similar to|containing|"
    r"covered (?:with|in)|made (?:of|from)|consisting of|suffering from)",
    r"(?:having|showing|displaying|possessing)",
    r"to (?:make|render|become|cause to be|cause to become|turn into)(?: or become)?",
]
_OPENER = "(?:" + "|".join(f"(?:{o})" for o in _OPENERS) + ")"
# Openers can be chained: "Consisting of or containing chalk".
OPENER_RE = re.compile(rf"^{_OPENER}(?:,? (?:or|and) {_OPENER})*\b")
# "To screen in advance", "To line again", "to protect excessively".
MODIFIED_VERB_RE = re.compile(
    r"^(?:to )?([a-z]+) (?:again|anew|once more|beforehand|in advance|ahead of time|too much|excessively|"
    r"badly|wrongly|incorrectly|insufficiently|inadequately|too little)\b"
)
FILLER = {
    "a", "an", "the", "or", "and", "of", "being", "been", "be", "one's", "its", "their", "his", "her", "very",
    "more", "much", "many", "some", "any", "quite", "rather", "somewhat", "highly", "overly", "too", "just",
    "especially", "particularly", "typically", "usually", "often", "two", "three", "great", "something",
    "that", "which", "who",
}
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")


def relates(token: str, base: str) -> bool:
    """True if `token` is `base` or an inflection of it ("stabs", "roots", "mobilization")."""
    shared = len(commonprefix([token, base]))
    return shared >= min(len(base), 4) and shared >= len(base) - 2


def possible_bases(word: str) -> list[str]:
    """Spellings `word` could be a regular derivative of, longest affix first."""
    bases: list[str] = []
    if "-" in word:
        for part in word.split("-"):
            if len(part) >= MIN_BASE_LENGTH:
                bases += [part] + possible_bases(part)  # two-sided -> side
    for prefix in PREFIXES:
        if word.startswith(prefix):
            rest = word[len(prefix):].lstrip("-")
            if len(rest) >= MIN_BASE_LENGTH:
                bases.append(rest)
                bases += uninflected(rest)  # unmarred -> marred -> mar
    for suffix, endings in SUFFIXES.items():
        if not word.endswith(suffix) or len(word) - len(suffix) < MIN_BASE_LENGTH:
            continue
        stem = word[: -len(suffix)]
        options = [stem + ending for ending in endings]
        if stem.endswith("i"):
            options.append(stem[:-1] + "y")
        if len(stem) >= 4 and stem[-1] == stem[-2]:
            options.append(stem[:-1])  # stabber -> stab, zippy -> zip
        bases += [b for b in options if len(b) >= MIN_BASE_LENGTH]
    seen: set[str] = set()
    return [b for b in bases if b != word and not (b in seen or seen.add(b))]


def uninflected(word: str) -> list[str]:
    """Spellings `word` could be a regular inflection of ("marred" -> "mar")."""
    bases = []
    for suffix, endings in INFLECTIONS.items():
        if word.endswith(suffix) and len(word) - len(suffix) >= MIN_BASE_LENGTH:
            stem = word[: -len(suffix)]
            bases += [stem + ending for ending in endings]
            if len(stem) >= 4 and stem[-1] == stem[-2]:
                bases.append(stem[:-1])
    return bases


def is_number_compound(word: str) -> bool:
    """ninety-five, twenty-one: the meaning is the parts."""
    return "-" in word and all(part in NUMBER_WORDS for part in word.split("-"))


def wraps(clause: str, base: str) -> bool:
    """True if `clause` (or a comma-separated piece of it) is a template around `base`."""
    pieces = [clause] + [p.strip(" ,.") for p in clause.split(",")[1:]]
    for piece in pieces:
        verb = MODIFIED_VERB_RE.match(piece)
        if verb and relates(verb.group(1), base):
            return True
        opener = OPENER_RE.match(piece)
        if not opener:
            continue
        for token in TOKEN_RE.findall(piece[opener.end():]):
            if token in FILLER:
                continue
            if relates(token, base):
                return True
            break
    return False


def restates(gloss: str, base: str) -> bool:
    """True if the definition is a template wrapped around `base`.

    The main (first) clause has to be the restatement. A later one only counts after
    a one-word synonym ("Undamaged; not marred"): "unprecedented: Never before seen,
    done, or experienced; without precedent" says something of its own first."""
    parts = [c.strip(" ,.") for c in re.split(r"[;:]", gloss.lower())]
    parts = [c for c in parts if c]
    if not parts:
        return False
    tokens = TOKEN_RE.findall(gloss.lower())
    if len(tokens) == 1 and relates(tokens[0], base):
        return True  # the definition is the base itself ("geological: Geologic")
    if wraps(parts[0], base):
        return True
    return len(TOKEN_RE.findall(parts[0])) == 1 and any(wraps(c, base) for c in parts[1:])


def transparent_base(word: str, gloss: str, is_more_common) -> str | None:
    """The base that makes this meaning of `word` obvious, if any. `is_more_common(base)`
    says whether a spelling is a vocabulary word more common than `word`."""
    if is_number_compound(word):
        return word.split("-")[0]
    for base in possible_bases(word):
        if is_more_common(base) and restates(gloss, base):
            return base
    return None
