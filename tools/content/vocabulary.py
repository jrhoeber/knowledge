"""Vocabulary word list and definitions.

Sources
-------
* Definitions: English Wiktionary, via the kaikki.org machine-readable extract
  (https://kaikki.org/dictionary/English/). CC BY-SA 4.0 / GFDL.
* Written usage: Google Books Ngram v3 (https://books.google.com/ngrams), English
  Fiction and all English books, reduced by `google_books.py` to the share of each
  year's books that use a word, 1920-2019 and 2000-2019. CC BY 3.0.
* Contemporary usage: the `wordfreq` package (https://github.com/rspeer/wordfreq),
  which blends news, books, Wikipedia, subtitles and web text. Data CC BY-SA 4.0.

Selection
---------
1. Every lowercase, purely alphabetic Wiktionary headword in a regular part of
   speech is a candidate if it has at least one usable definition (not obsolete,
   archaic, rare, dialectal, vulgar, offensive, a misspelling, an inflected
   "form of" another word, and so on). `blocklist.txt` removes words that are not
   family friendly and spellings whose counts measure something else (der, tion).
2. Each source scores the candidates. Inflected forms (went, dogs, running when it
   is only a verb form) add their score to their base word, so the list counts base
   words rather than spellings. A form with a meaning of its own keeps a share in
   proportion to that meaning's translations (building keeps about half; came, a
   lead rod in stained glass, almost none).
   * Books: how often an average book uses the word, estimated from the share of
     books that use it (`uses_per_book`), over 1920-2019 or 2000-2019, whichever
     is higher: a word counts if it has been common for a century or is common
     now. Counting books rather than occurrences keeps a term that one technical
     book repeats from looking common. Google Books is case-sensitive, so
     sentence-initial "However" counts toward "however", but for words with a
     capitalized Wiktionary entry (Bill, Kate) only lowercase uses count, and not
     even those when the capitalized spelling dominates (`NAME_DOMINANCE`).
   * wordfreq: frequency. wordfreq folds case, so for words with a capitalized
     entry it keeps the lowercase share of the word's uses in Google Books.
3. Candidates are ranked by the weighted geometric mean of their rank in each
   source (`SOURCE_WEIGHTS`): fiction stands for literature, all books for
   nonfiction, wordfreq for news and current usage. A word has to be common in all
   three to rank high, which pushes out encyclopedic jargon (rare in fiction) and
   internet slang (rare in books). Hyphenated words and contraction pieces are
   split by the Google Books tokenizer, so they are ranked by wordfreq alone.
4. The top `WORD_COUNT` candidates become the word list, and rank sets difficulty.
   Words with no testable definition need to be more common to get in
   (`UNTESTABLE_RANK_PENALTY`), and very short words far down the list need some
   sign that their meaning is in use (`SHORT_WORD_MAX_RANK`).

Definitions
-----------
Wiktionary orders senses by etymology and history, not by how common they are, so
senses are ranked by how many translations editors attached to them: translation
tables are written for the meanings people actually look up. A word keeps every
sense with at least `COMMON_SHARE` of its top sense's translations (at most six).
Words with too few translations to judge keep their first few senses in
dictionary order. Senses that sound regional or slangy are kept only if the word
has nothing else. Words whose every definition contains the word itself ("the
quality of being assertive") are skipped, since the answer would be obvious.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import orjson
from wordfreq import top_n_list, word_frequency

WORD_COUNT = 40_000
# Upper rank (inclusive) of each difficulty level.
DIFFICULTY_BANDS = ((1, 3_000), (2, 8_000), (3, 15_000), (4, 25_000), (5, WORD_COUNT))
# Weights of each source in the blended rank (a weighted geometric mean of ranks).
SOURCE_WEIGHTS = {"fiction": 0.4, "books": 0.3, "wordfreq": 0.3}
BOOK_SOURCES = ("fiction", "books")
# In Google Books, a word with a capitalized Wiktionary entry whose Titlecase
# spelling is this many times more common than its lowercase one is mostly a name
# (Kate, Geneva; compare bill, smith, jean), so its lowercase count is mostly noise.
NAME_DOMINANCE = 20
# Words with no testable definition compete for a place in the list as if they were
# this many times rarer, but keep their real rank for difficulty.
UNTESTABLE_RANK_PENALTY = 2.0
# Google Books splits contractions ("wo n't", "ca n't"), which inflates these
# spellings; like hyphenated words, they are ranked by wordfreq alone.
CONTRACTION_FRAGMENTS = {"ai", "ca", "sha", "wo"}
# Shares this close to 1 (the, and) carry no information about uses per book.
MAX_BOOK_SHARE = 0.9999
# Past this rank, words of `SHORT_WORD_LENGTH` letters or fewer are mostly
# clippings, interjections, letters of other alphabets and foreign units whose
# counts come from other uses of the same letters (tse, kan, sei). They stay only
# if their meaning has `SHORT_WORD_TRANSLATIONS` translations (elk, oar).
SHORT_WORD_MAX_RANK = 20_000
SHORT_WORD_LENGTH = 3
SHORT_WORD_TRANSLATIONS = 3

MAX_SENSES = 6
COMMON_SHARE = 0.08
MIN_COMMON_TRANSLATIONS = 3
# Below this many translations on its top sense, a word's senses are taken in
# dictionary order instead.
RANKABLE_TRANSLATIONS = 10
FIRST_ENTRY_SENSES = 3
OTHER_ENTRY_SENSES = 1
FALLBACK_SENSES = 4
MAX_GLOSS_LENGTH = 220
MAX_QUIZ_GLOSS_LENGTH = 150
MAX_EXAMPLE_LENGTH = 150
PLURAL_OWN_MEANING_TRANSLATIONS = 10
PLURAL_FREQUENCY_SHARE = 0.35
HYPHENATED_MIN_TRANSLATIONS = 2
MAX_RELATED = 40

WORD_RE = re.compile(r"[a-z]+")
# Hyphenated headwords (t-shirt, x-ray, well-known). wordfreq estimates them from
# their parts, which wildly overrates compounds of common words ("to-do" would
# rank with "house"), so each extra part costs HYPHEN_PENALTY_ZIPF and the
# estimate is capped at HYPHEN_MAX_ZIPF.
HYPHENATED_RE = re.compile(r"[a-z]+(?:-[a-z]+)+")
HYPHEN_PENALTY_ZIPF = 1.2
HYPHEN_MAX_ZIPF = 3.8
POS_CODES = {"noun", "verb", "adj", "adv", "pron", "prep", "conj", "det", "intj", "num", "article", "particle"}

EXCLUDED_TAGS = {
    "form-of", "alt-of", "alternative", "obsolete", "misspelling",
    "abbreviation", "initialism", "acronym", "contraction",
    "pronunciation-spelling", "eye-dialect", "no-gloss", "proscribed", "nonce-word",
    "misconstruction", "vulgar", "offensive", "derogatory", "slur", "ethnic", "euphemistic",
    "obsolete-sense", "historical-sense",
}
# Kept only when a word has no other usable sense.
SECONDARY_TAGS = {
    "slang", "Internet", "dated", "uncommon", "poetic", "archaic", "rare", "dialectal", "nonstandard",
    "clipping", "regional",
}
# Regional senses are secondary unless they are also marked for a major variety.
MINOR_REGION_TAGS = {
    "Scotland", "Northern-England", "Geordie", "Yorkshire", "Cornwall", "Multicultural-London-English",
    "Singlish", "Singapore", "Malaysia", "Philippines", "Jamaica", "Caribbean", "South-Asia", "India",
    "South-Africa", "New-Zealand", "Ireland", "Southern-US", "England", "Wales", "Hawaii", "Appalachia",
    "AAVE",
}
MAJOR_REGION_TAGS = {"US", "UK", "British", "American", "Canada", "Australia", "Commonwealth", "North-America"}
EXCLUDED_TOPICS = {"sexuality", "BDSM", "pornography", "sex", "sexology", "drugs"}
EXCLUDED_CATEGORY_RE = re.compile(
    r"slur|swear|vulgar|offensive|derogatory|insult|BDSM|prostitution|pornograph|erotic|"
    r"sex positions|recreational drugs|^sex$|^sexuality$",
    re.I,
)
EXPLICIT_GLOSS_RE = re.compile(
    r"\b(penis|penises|vagina|vulva|genital|genitals|genitalia|testicle|testicles|scrotum|clitoris|"
    r"anus|anal|copulat\w*|masturbat\w*|orgasm\w*|ejaculat\w*|semen|erotic\w*|porn\w*|prostitut\w*|"
    r"brothel|fellatio|cunnilingus|sodom\w*|fornicat\w*|rape|raped|rapist|molest\w*|pedophil\w*|"
    r"paedophil\w*|incest\w*|bestiality|intercourse|fuck\w*|shit\w*|cunt|whore|slut)\b"
    r"|\bsexual(ly)? (activity|act|acts|partner|arous\w*|desire|pleasure|gratification|stimulat\w*|"
    r"excit\w*|climax|fetish\w*|innuendo|favou?rs|encounter)"
    r"|\b(have|having|has|had) sex\b|\bsex (act|acts|with|toy|toys|worker|workers)\b",
    re.I,
)
SKIPPED_GLOSS_RE = re.compile(
    r"^(synonym of|alternative|obsolete|archaic|abbreviation of|initialism of|acronym of|"
    r"misspelling of|clipping of|ellipsis of|short for|plural of|eye dialect|nonstandard|"
    r"used other than|see |only used in|in the phrase|used in the phrase|the name of the .*letter|agent noun of|"
    r"\(?\w+ form of )",
    re.I,
)
# Usage notes rather than definitions ("Often followed by from").
USAGE_NOTE_RE = re.compile(
    r"^((often|usually|sometimes|chiefly|generally|especially|normally) )?(followed|preceded) by\b"
    r"|^(often|usually|chiefly|generally) (in|with|plural|negative|used)\b",
    re.I,
)
# Glosses that only point at another spelling, wherever the phrase appears.
SPELLING_NOTE_RE = re.compile(r"\bspelling of\b|\bform of [a-z]+$", re.I)

WEAK_LINK_TAGS = {
    "obsolete", "archaic", "dated", "rare", "uncommon", "misspelling", "abbreviation", "initialism", "acronym",
    "eye-dialect", "pronunciation-spelling", "nonstandard", "dialectal", "slang", "Internet", "clipping",
}
ANAPHORIC_GLOSS_RE = re.compile(
    r"\bsuch an?\b|\bthe above\b|\bthis (sense|manner|way)\b|^(any|a|an|some) similar\b", re.I
)
NOT_AN_EXAMPLE_RE = re.compile(
    r"^(near-)?(synonyms?|antonyms?|hypernyms?|hyponyms?|meronyms?|holonyms?|coordinate terms?|see also)\b", re.I
)

STOP_WORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had", "her", "was", "one",
    "our", "out", "has", "him", "his", "how", "its", "may", "new", "now", "old", "see", "two", "way",
    "who", "did", "get", "let", "say", "she", "too", "use", "used", "using", "uses", "that", "this",
    "with", "from", "they", "them", "then", "than", "their", "there", "these", "those", "what", "when",
    "where", "which", "while", "whom", "whose", "will", "would", "could", "should", "been", "being",
    "have", "having", "into", "onto", "upon", "over", "under", "about", "above", "after", "again",
    "also", "because", "before", "below", "between", "both", "down", "during", "each", "even", "ever",
    "every", "here", "just", "more", "most", "much", "must", "only", "other", "others", "same", "some",
    "such", "very", "through", "until", "within", "without", "your", "something", "someone", "person",
    "people", "thing", "things",
}
SUFFIXES = ("ingly", "edly", "ness", "ment", "ings", "ing", "ied", "ies", "ers", "est", "ed", "er", "es", "ly", "s")


def stem(token: str) -> str:
    """Python port of `GlossTokenizer.stem` in the app."""
    for suffix in SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def stems_match(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and long.startswith(short)


def is_relative(a: str, b: str) -> bool:
    """Stricter than `stems_match`: a shared prefix only counts when it covers most
    of both words, so "assertive"/"assertiveness" match but "water"/"waterway"
    and "part"/"particular" do not."""
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and long.startswith(short) and len(short) >= 0.7 * len(long)


def mentions_word(gloss: str, word: str) -> bool:
    """True if a definition uses the word itself (or an obvious relative), which
    would give the answer away."""
    target = stem(word)
    for token in re.split(r"[^a-z]+", gloss.lower()):
        if len(token) >= 3 and token not in STOP_WORDS and is_relative(stem(token), target):
            return True
    return False


def clean_gloss(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^\([^)]*\)\s*", "", text)  # leading qualifier such as "(transitive)"
    # Long glosses often add usage notes after the definition; keep the first sentence.
    first, _, rest = text.partition(". ")
    if rest and len(text) > 100 and len(first) >= 20:
        text = first
    # Parenthetical asides ("(often geographical points)") make options long without
    # changing the meaning.
    without_asides = re.sub(r"\s*\([^()]*\)", "", text).strip()
    if len(without_asides) >= 15:
        text = re.sub(r"\s+([,;:.])", r"\1", without_asides)
    text = text.rstrip(" .;,")
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


@dataclass
class Sense:
    pos: str
    gloss: str
    example: str | None
    secondary: bool
    entry_index: int
    order: int
    translations: int = 0


@dataclass
class Candidate:
    word: str
    senses: list[Sense]
    related: set[str] = field(default_factory=set)
    flagged: bool = False  # first sense of the first entry is vulgar or offensive
    has_name_entry: bool = False


@dataclass(frozen=True)
class VocabSense:
    pos: str
    gloss: str
    example: str | None
    quizzable: bool


@dataclass(frozen=True)
class VocabWord:
    word: str
    rank: int
    difficulty: int
    related: tuple[str, ...]
    senses: tuple[VocabSense, ...]


def load_blocklist(path: Path) -> set[str]:
    words = set()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            words.add(line)
    return words


def sense_flags(sense: dict) -> tuple[bool, bool]:
    """Returns (excluded, secondary) for a raw Wiktionary sense."""
    tags = set(sense.get("tags", ())) | set(sense.get("raw_tags", ()))
    if sense.get("form_of") or sense.get("alt_of") or tags & EXCLUDED_TAGS:
        return True, False
    if set(sense.get("topics", ())) & EXCLUDED_TOPICS:
        return True, False
    for category in sense.get("categories", ()):
        name = category.get("name", "") if isinstance(category, dict) else str(category)
        if EXCLUDED_CATEGORY_RE.search(name):
            return True, False
    regional = bool(tags & MINOR_REGION_TAGS) and not tags & MAJOR_REGION_TAGS
    return False, bool(tags & SECONDARY_TAGS) or regional


def pick_example(sense: dict, word: str) -> str | None:
    for example in sense.get("examples", ()):
        if example.get("type") not in ("example", None):
            continue
        text = re.sub(r"\s+", " ", example.get("text", "")).strip()
        if not text or len(text) > MAX_EXAMPLE_LENGTH or word not in text.lower():
            continue
        if EXPLICIT_GLOSS_RE.search(text) or "\n" in text or NOT_AN_EXAMPLE_RE.match(text):
            continue
        if example.get("type") is None and re.match(r"^\d{3,4}", text):
            continue  # citation line rather than a usage example
        return text
    return None


def related_terms(entry: dict, sense: dict | None) -> set[str]:
    terms = set()
    sources = []
    if sense is not None:
        sources += sense.get("synonyms", []) + sense.get("hypernyms", [])
    else:
        sources += entry.get("synonyms", []) + entry.get("hypernyms", [])
    for item in sources:
        for token in re.split(r"[^a-z]+", str(item.get("word", "")).lower()):
            if len(token) >= 3 and token not in STOP_WORDS:
                terms.add(token)
    return terms


def read_candidates(
    path: Path, vocabulary: set[str]
) -> tuple[dict[str, Candidate], dict[str, set[tuple[str, str]]]]:
    """Streams the Wiktionary extract once.

    Returns candidate base words and a map from a spelling to the words it is an
    inflection ("form_of") or alternative spelling ("alt_of") of.
    """
    candidates: dict[str, Candidate] = {}
    inflection_of: dict[str, set[tuple[str, str]]] = defaultdict(set)
    names: set[str] = set()
    entry_counts: dict[str, int] = defaultdict(int)

    with path.open("rb") as handle:
        for line in handle:
            entry = orjson.loads(line)
            if entry.get("lang_code") != "en":
                continue
            word = entry.get("word", "")
            pos = entry.get("pos")
            if word[:1].isupper():
                # Proper nouns and capitalized words (Paris, Methodist, English) share
                # wordfreq's lowercase counts with any lowercase homograph.
                if word[1:].islower() and word.lower() in vocabulary:
                    names.add(word.lower())
                continue
            if pos not in POS_CODES:
                continue
            if not (WORD_RE.fullmatch(word) and word in vocabulary) and not HYPHENATED_RE.fullmatch(word):
                continue

            index = entry_counts[word]
            entry_counts[word] += 1
            candidate = candidates.setdefault(word, Candidate(word=word, senses=[]))
            candidate.related |= related_terms(entry, None)
            by_gloss = {s.gloss.lower(): s for s in candidate.senses}
            entry_translations = len(entry.get("translations", ()))
            first_kept: Sense | None = None

            for raw_index, sense in enumerate(entry.get("senses", ())):
                # Inflections and alternative spellings pass their frequency to the main
                # word, but only through current, standard links ("went" -> "go", not
                # the obsolete "red" -> "rede").
                if not set(sense.get("tags", ())) & WEAK_LINK_TAGS:
                    for kind in ("form_of", "alt_of"):
                        for form in sense.get(kind, ()):
                            base = form.get("word", "")
                            if base != word and (WORD_RE.fullmatch(base or "") or HYPHENATED_RE.fullmatch(base or "")):
                                inflection_of[word].add((base, kind))
                excluded, secondary = sense_flags(sense)
                glosses = sense.get("glosses") or []
                if index == 0 and raw_index == 0 and excluded and set(sense.get("tags", ())) & {
                    "vulgar", "offensive", "derogatory", "slur", "ethnic"
                }:
                    candidate.flagged = True
                if excluded or not glosses or any(EXPLICIT_GLOSS_RE.search(g) for g in glosses):
                    continue
                # Sub-senses repeat their parent's gloss first. They are merged into the
                # parent, which collects their translations, unless the parent is only a
                # heading such as "Of a person or an animal:".
                parent = glosses[0].strip()
                gloss = clean_gloss(glosses[-1] if parent.endswith(":") and len(glosses) > 1 else parent)
                if (
                    len(gloss) < 3
                    or len(gloss) > MAX_GLOSS_LENGTH
                    or gloss.endswith(":")
                    or SKIPPED_GLOSS_RE.match(gloss)
                    or SPELLING_NOTE_RE.search(gloss)
                    or USAGE_NOTE_RE.match(gloss)
                    or "{{" in gloss
                ):
                    continue
                translations = len(sense.get("translations", ()))
                candidate.related |= related_terms(entry, sense)
                if ANAPHORIC_GLOSS_RE.search(gloss):
                    # "A branch office of such an institution" only makes sense after the
                    # sense it refers to; credit that sense instead.
                    if first_kept is not None:
                        candidate.senses[-1].translations += translations
                    continue
                existing = by_gloss.get(gloss.lower())
                if existing is not None:
                    existing.translations += translations
                    existing.secondary = existing.secondary and secondary
                    if existing.example is None:
                        existing.example = pick_example(sense, word)
                    continue
                kept = Sense(
                    pos=pos, gloss=gloss, example=pick_example(sense, word), secondary=secondary,
                    entry_index=index, order=len(candidate.senses), translations=translations,
                )
                candidate.senses.append(kept)
                by_gloss[gloss.lower()] = kept
                if first_kept is None:
                    first_kept = kept
            # Translation tables not tied to a sense almost always belong to the first one.
            if first_kept is not None:
                first_kept.translations += entry_translations

    for word in names:
        if word in candidates:
            candidates[word].has_name_entry = True
    return candidates, inflection_of


def choose_senses(candidate: Candidate) -> list[Sense]:
    """The word's common senses, most common first."""
    primary = [s for s in candidate.senses if not s.secondary]
    pool = primary if primary else candidate.senses
    if not pool:
        return []
    top = max(s.translations for s in pool)
    if top >= RANKABLE_TRANSLATIONS:
        threshold = max(MIN_COMMON_TRANSLATIONS, COMMON_SHARE * top)
        common = [s for s in pool if s.translations >= threshold]
        return sorted(common, key=lambda s: (-s.translations, s.order))[:MAX_SENSES]

    chosen: list[Sense] = []
    per_entry: dict[int, int] = defaultdict(int)
    first_entry = pool[0].entry_index
    for sense in sorted(pool, key=lambda s: s.order):
        cap = FIRST_ENTRY_SENSES if sense.entry_index == first_entry else OTHER_ENTRY_SENSES
        if per_entry[sense.entry_index] >= cap:
            continue
        per_entry[sense.entry_index] += 1
        chosen.append(sense)
        if len(chosen) == FALLBACK_SENSES:
            break
    # Within the fallback, still let translations break ties toward common senses.
    return sorted(chosen, key=lambda s: (-s.translations, s.order))


def difficulty_for_rank(rank: int) -> int:
    for level, upper in DIFFICULTY_BANDS:
        if rank <= upper:
            return level
    return DIFFICULTY_BANDS[-1][0]


@dataclass
class Prepared:
    """Candidates that passed the definition filters, ready to be ranked."""

    vocabulary: set[str]
    usable: dict[str, Candidate]
    chosen: dict[str, list[VocabSense]]
    inflection_of: dict[str, set[tuple[str, str]]]


def prepare(wiktionary_path: Path, blocklist_path: Path) -> Prepared:
    frequency_list = top_n_list("en", 1_000_000)
    vocabulary = {w for w in frequency_list if WORD_RE.fullmatch(w)}
    candidates, inflection_of = read_candidates(wiktionary_path, vocabulary)
    blocked = load_blocklist(blocklist_path)

    usable: dict[str, Candidate] = {}
    chosen: dict[str, list[VocabSense]] = {}
    for word, candidate in candidates.items():
        if word in blocked or candidate.flagged or (len(word) < 2 and word != "a"):
            continue
        def quizzable(sense: Sense) -> bool:
            return len(sense.gloss) <= MAX_QUIZ_GLOSS_LENGTH and not mentions_word(sense.gloss, word)

        picked = choose_senses(candidate)
        if not any(quizzable(s) for s in picked):
            # A testable sense that missed the commonness cut is better than none.
            rescue = sorted(
                (s for s in candidate.senses if quizzable(s)), key=lambda s: (s.secondary, -s.translations, s.order)
            )
            if rescue:
                picked = (picked + rescue[:1])[-MAX_SENSES:]
        senses = [VocabSense(s.pos, s.gloss, s.example, quizzable(s)) for s in picked]
        if not senses:
            continue
        usable[word] = candidate
        chosen[word] = senses

    # Inflected forms with a niche meaning of their own (doors: "opening time",
    # twilights: "WAAF underwear") are not base words. Keep them only when their
    # own meaning is in wide use (interesting, glasses, data).
    for word in list(usable):
        inflects = any(kind == "form_of" and base in usable for base, kind in inflection_of.get(word, ()))
        if not inflects:
            continue
        translations = max(s.translations for s in usable[word].senses)
        # Plurals need a widely used meaning of their own, or to be used nearly as
        # often as the singular (data, glasses). Participles (terrified, amused)
        # need at least some sign of independent use.
        if word.endswith("s"):
            bases = [b for b, kind in inflection_of[word] if kind == "form_of" and b in usable]
            base_frequency = max(word_frequency(b, "en") for b in bases)
            keep = (
                translations >= PLURAL_OWN_MEANING_TRANSLATIONS
                or word_frequency(word, "en") >= PLURAL_FREQUENCY_SHARE * base_frequency
            )
        else:
            keep = translations >= 1
        if not keep:
            del usable[word]
            del chosen[word]

    # Hyphenated entries are only real words when they are lexicalized compounds,
    # which Wiktionary editors translate (t-shirt, mother-in-law). Phrases such as
    # "two-level" are not.
    for word in [w for w in usable if "-" in w]:
        if max(s.translations for s in usable[word].senses) < HYPHENATED_MIN_TRANSLATIONS:
            del usable[word]
            del chosen[word]

    return Prepared(vocabulary, usable, chosen, inflection_of)


def load_book_shares(path: Path) -> dict[str, tuple[float, float, float, float]]:
    """Rows written by `google_books.py`: lower and Titlecase book shares over the
    century and over recent years."""
    shares = {}
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            continue
        word, lower_century, title_century, lower_recent, title_recent = line.split("\t")
        shares[word] = (float(lower_century), float(title_century), float(lower_recent), float(title_recent))
    return shares


def uses_per_book(share: float) -> float:
    """Average uses per book implied by the share of books that use a spelling.

    If uses fall at random (a Poisson process), a spelling used `r` times per book on
    average appears in `1 - exp(-r)` of books. Unlike shares, rates add up across
    spellings and inflections ("take" and "took" each appear in most books). For rare
    words the rate is about the share, so a term that a few books repeat still counts
    as rare."""
    return -math.log(1 - min(share, MAX_BOOK_SHARE))


def book_rates(row: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return tuple(uses_per_book(share) for share in row)  # type: ignore[return-value]


def book_frequency(row: tuple[float, float, float, float] | None, lowercase_only: bool) -> float:
    """Uses per book of a word's lowercase and Titlecase spellings, over the century
    or over recent years, whichever is higher."""
    if row is None:
        return 0.0
    lower_century, title_century, lower_recent, title_recent = book_rates(row)
    if lowercase_only:
        return max(lower_century, lower_recent)
    return max(lower_century + title_century, lower_recent + title_recent)


def wordfreq_frequency(word: str) -> float:
    frequency = word_frequency(word, "en")
    if "-" in word:
        frequency *= 10 ** (-HYPHEN_PENALTY_ZIPF * word.count("-"))
        frequency = min(frequency, 10 ** HYPHEN_MAX_ZIPF / 1e9)
    return frequency


def top_translations(candidate: Candidate) -> int:
    return max(s.translations for s in candidate.senses)


def own_meaning_share(candidate: Candidate, bases: list[Candidate]) -> float:
    """How much of an inflected spelling's count belongs to its own meaning.

    Translation counts show how much each meaning is looked up: "building" and
    "glasses" keep about half, "came" (a lead rod in stained glass) almost none of
    the count it shares with "come"."""
    own = top_translations(candidate)
    base = max(top_translations(b) for b in bases)
    return (own + 1) / (own + base + 2)


def name_discount(candidate: Candidate) -> float:
    """Share of a name-like word's count to keep when nothing better is known:
    translation counts show whether the lowercase word is in everyday use."""
    translations = top_translations(candidate)
    if translations >= 50:
        return 0.3
    if translations >= 10:
        return 0.05
    return 0.005


def fold(prepared: Prepared, frequency_of, own_fraction) -> dict[str, float]:
    """Scores candidates by one source, adding inflected spellings to base words.

    `own_fraction(candidate)` is the share of the source's count that belongs to the
    lowercase word rather than a proper noun or capitalized word (1 for most words)."""
    usable, inflection_of = prepared.usable, prepared.inflection_of
    scores: dict[str, float] = defaultdict(float)
    hyphenated = [w for w in usable if "-" in w]
    for word in sorted(prepared.vocabulary) + hyphenated:
        frequency = frequency_of(word)
        if frequency <= 0:
            continue
        links = inflection_of.get(word, ())
        if word not in usable:
            bases = sorted({b for b, _ in links if b in usable})
            for base in bases:
                scores[base] += frequency / len(bases)
            continue
        candidate = usable[word]
        # A word with meanings of its own only shares frequency with words it inflects
        # ("saw" -> "see"), not with spellings it happens to be an alternative of.
        bases = sorted({b for b, kind in links if kind == "form_of" and b in usable})
        own_share = 1.0
        if bases:
            # Also an inflected form (doors, declared): most of its frequency is the
            # inflection, unless its own meaning is common too (interesting, building).
            own_share = own_meaning_share(candidate, [usable[b] for b in bases])
            for base in bases:
                scores[base] += frequency * (1 - own_share) / len(bases)
        # Much of the count may be the proper noun or capitalized word (John, English).
        own_share *= own_fraction(candidate)
        if all(s.secondary for s in candidate.senses):
            # Only archaic, dialectal or slang meanings: probably not what the counts measure.
            own_share *= 0.1
        scores[word] += frequency * own_share
    return scores


def rank_positions(scores: dict[str, float]) -> dict[str, float]:
    """1-based rank of every positively scored word. Tied words share their average
    rank, so ties do not turn into alphabetical order."""
    ordered = sorted((w for w, score in scores.items() if score > 0), key=lambda w: -scores[w])
    ranks: dict[str, float] = {}
    start = 0
    while start < len(ordered):
        end = start
        while end + 1 < len(ordered) and scores[ordered[end + 1]] == scores[ordered[start]]:
            end += 1
        for word in ordered[start : end + 1]:
            ranks[word] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def source_ranks(prepared: Prepared, books: dict[str, Path]) -> dict[str, dict[str, float]]:
    """Each source's rank for every candidate it has seen."""
    names = {w for w, c in prepared.usable.items() if c.has_name_entry}
    shares = {source: load_book_shares(books[source]) for source in BOOK_SOURCES}

    def lower_and_title(row: tuple[float, float, float, float]) -> tuple[float, float]:
        lower_century, title_century, lower_recent, title_recent = book_rates(row)
        return max(lower_century, lower_recent), max(title_century, title_recent)

    def wordfreq_fraction(candidate: Candidate) -> float:
        # wordfreq folds case, so "bill" also counts "Bill". Google Books does not:
        # the lowercase share of a word's book usage says how much of the count is
        # the everyday word.
        if not candidate.has_name_entry:
            return 1.0
        row = shares["books"].get(candidate.word)
        if row is None:
            return name_discount(candidate)
        lower, title = lower_and_title(row)
        return lower / (lower + title) if lower + title > 0 else name_discount(candidate)

    ranks = {"wordfreq": rank_positions(fold(prepared, wordfreq_frequency, wordfreq_fraction))}
    for source in BOOK_SOURCES:
        source_shares = shares[source]

        def frequency_of(word: str, source_shares=source_shares) -> float:
            if word in CONTRACTION_FRAGMENTS:
                return 0.0
            return book_frequency(source_shares.get(word), lowercase_only=word in names)

        def books_fraction(candidate: Candidate, source_shares=source_shares) -> float:
            # Only lowercase spellings count for name-like words, but when the
            # capitalized spelling dominates, even those are mostly typos and OCR noise.
            row = source_shares.get(candidate.word)
            if not candidate.has_name_entry or row is None:
                return 1.0
            lower, title = lower_and_title(row)
            return name_discount(candidate) if title > NAME_DOMINANCE * lower else 1.0

        ranks[source] = rank_positions(fold(prepared, frequency_of, books_fraction))
    return ranks


def blended_rank(ranks: dict[str, dict[str, float]]) -> dict[str, float]:
    """Weighted geometric mean of each source's rank (lower is more common).

    A word a source never saw ranks just past that source's last word. Hyphenated
    words are absent from Google Books by tokenization, not rarity, so they are
    ranked by wordfreq alone."""
    words = set().union(*ranks.values())
    blended = {}
    for word in words:
        total = weight_sum = 0.0
        for source, weight in SOURCE_WEIGHTS.items():
            if source in BOOK_SOURCES and ("-" in word or word in CONTRACTION_FRAGMENTS):
                continue
            position = ranks[source].get(word, len(ranks[source]) + 1)
            total += weight * math.log(position)
            weight_sum += weight
        blended[word] = math.exp(total / weight_sum)
    return blended


def rank(prepared: Prepared, books: dict[str, Path], ranks: dict[str, dict[str, float]] | None = None) -> list[VocabWord]:
    usable, chosen = prepared.usable, prepared.chosen
    ranks = ranks if ranks is not None else source_ranks(prepared, books)
    scores = blended_rank(ranks)
    if len(scores) < WORD_COUNT:
        raise SystemExit(f"Only {len(scores)} usable words; need {WORD_COUNT}.")
    # Prefer words with a testable definition: words whose definitions all lean on
    # the word itself ("in a grateful manner") need to be more common to get in, but
    # common ones (suddenly, university) stay, at their real rank.
    def selection_rank(word: str) -> float:
        testable = any(s.quizzable for s in chosen[word])
        return scores[word] * (1 if testable else UNTESTABLE_RANK_PENALTY)

    def doubtful(word: str) -> bool:
        return (
            len(word) <= SHORT_WORD_LENGTH
            and scores[word] > SHORT_WORD_MAX_RANK
            and top_translations(usable[word]) < SHORT_WORD_TRANSLATIONS
        )

    eligible = [w for w in scores if not doubtful(w)]
    if len(eligible) < WORD_COUNT:
        raise SystemExit(f"Only {len(eligible)} usable words; need {WORD_COUNT}.")
    selected = sorted(eligible, key=lambda w: (selection_rank(w), w))[:WORD_COUNT]
    ranked = sorted(selected, key=lambda w: (scores[w], w))

    words: list[VocabWord] = []
    for position, word in enumerate(ranked[:WORD_COUNT], start=1):
        candidate = usable[word]
        related = sorted(t for t in candidate.related if t != word)[:MAX_RELATED]
        words.append(VocabWord(word, position, difficulty_for_rank(position), tuple(related), tuple(chosen[word])))
    return words


def build(wiktionary_path: Path, blocklist_path: Path, books: dict[str, Path]) -> list[VocabWord]:
    """`books` maps each of `BOOK_SOURCES` to a `google_books.py` output file."""
    return rank(prepare(wiktionary_path, blocklist_path), books)


PROBE_WORDS = (
    "however", "meanwhile", "bill", "may", "email", "website", "smartphone", "pestilence", "panacea",
    "importunately", "somnambulant", "inapposite", "hypogammaglobulinemia", "immunoperoxidase",
    "hexapeptide", "ragequit", "autosave", "vaporwave",
)


def report(prepared: Prepared, books: dict[str, Path], seed: int) -> None:
    """Prints what a build would produce, for tuning by eye."""
    import random

    ranks = source_ranks(prepared, books)
    bank = rank(prepared, books, ranks)
    by_word = {w.word: w for w in bank}
    print(len(bank), "words;", sum(len(w.senses) for w in bank), "senses;",
          sum(1 for w in bank if not any(s.quizzable for s in w.senses)), "words with no quizzable sense")
    print("boundaries:", [(upper, bank[upper - 1].word) for _, upper in DIFFICULTY_BANDS])

    rng = random.Random(seed)
    for level, upper in DIFFICULTY_BANDS:
        band = [w for w in bank if w.difficulty == level]
        print(f"\n== level {level}: {len(band)} words, e.g.")
        print("  " + ", ".join(w.word for w in sorted(rng.sample(band, 24), key=lambda w: w.rank)))
    for position in (15_000, 25_000, 30_000, 35_000, WORD_COUNT - 20):
        print(f"\n== from rank {position}:", ", ".join(w.word for w in bank[position - 1 : position + 19]))

    def source_rank(source: str, word: str) -> str:
        value = ranks[source].get(word)
        return f"{value:>9.0f}" if value else "        -"

    print(f"\n{'probe':<22}{'final':>9}" + "".join(f"{s:>10}" for s in SOURCE_WEIGHTS))
    for word in PROBE_WORDS:
        final = by_word[word].rank if word in by_word else "-"
        print(f"{word:<22}{final:>9}" + "".join(f" {source_rank(s, word)}" for s in SOURCE_WEIGHTS))

    wordfreq_order = sorted(ranks["wordfreq"], key=lambda w: ranks["wordfreq"][w])
    old_top = [w for w in wordfreq_order if w in prepared.chosen][:WORD_COUNT]
    dropped = [w for w in old_top if w not in by_word]
    added = [w.word for w in bank if ranks["wordfreq"].get(w.word, 1e9) > WORD_COUNT]
    print(f"\n{len(dropped)} of wordfreq's top {WORD_COUNT} dropped; most common:", ", ".join(dropped[:60]))
    print(f"\n{len(added)} added from beyond wordfreq's top {WORD_COUNT}; most common:", ", ".join(added[:60]))


if __name__ == "__main__":
    import pickle
    import sys

    here = Path(__file__).parent
    books = {"fiction": here / ".cache" / "google-books" / "eng-fiction.tsv",
             "books": here / ".cache" / "google-books" / "eng.tsv"}
    # --reuse keeps the parsed Wiktionary candidates between runs (parsing takes minutes).
    cached = here / ".cache" / "vocabulary-prepared.pickle"
    if "--reuse" in sys.argv and cached.exists():
        prepared = pickle.loads(cached.read_bytes())
    else:
        prepared = prepare(here / ".cache" / "kaikki-english.jsonl", here / "blocklist.txt")
        cached.write_bytes(pickle.dumps(prepared))
    seeds = [int(a) for a in sys.argv[1:] if a.isdigit()]
    report(prepared, books, seeds[0] if seeds else 7)
