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
* How many people know each word and when each meaning is learned, plus school and
  work word lists: see `norms.py`.
* American spelling: VarCon, see `spelling.py`.

Selection
---------
1. Every lowercase, purely alphabetic Wiktionary headword in a regular part of
   speech is a candidate if it has at least one usable definition (not obsolete,
   archaic, rare, dialectal, vulgar, offensive, a misspelling, an inflected
   "form of" another word, and so on). Derogatory meanings are usable (idiot,
   philistine) unless they insult a group, are sexual or are untranslated slang
   (`GROUP_INSULT_RE`). `blocklist.txt` removes words that are not family friendly
   and spellings whose counts measure something else (der, tion). A word whose
   definitions Wiktionary keeps under a phrase or accented spelling gets those
   (healthcare: "health care", cliche: "cliché"; `rescue_from_phrases`).
   British spellings are merged into the American word, definitions and examples
   are respelled, and the British spelling's frequency counts toward the American
   one (plough -> plow; `use_american_spelling`).
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
   nonfiction, wordfreq for news and current usage. Fiction has the smallest
   weight so that news and workplace words (stakeholder, bipartisan) are not held
   back by being rare in novels. A word has to be common in all three to rank high,
   which still pushes out encyclopedic jargon and internet slang. Hyphenated words
   and contraction pieces are split by the Google Books tokenizer, so they are
   ranked by wordfreq alone.
4. The top `WORD_POOL` candidates are considered. Words on the school and work
   lists (NAWL, BSL) compete as if they were `SCHOOL_AND_WORK_BOOST` times more
   common, which also brings them up sooner within a level. Words with no testable
   definition need to be more common to get in (`UNTESTABLE_RANK_PENALTY`), and very
   short words far down the list need some sign that their meaning is in use
   (`SHORT_WORD_MAX_RANK`).
5. The `REMOVED_COMMON_WORDS` most common words (be, have, house) are never asked on
   their main meaning, which nearly every adult knows. They are asked on later
   meanings that fewer than `COMMON_WORD_MAX_KNOWN` of adults are estimated to know
   (table: to postpone; bill: a proposed law; minute: very small); see
   `common_word_meanings`. A common word with none is left out.
6. Meanings that merely restate a more common word ("unmusical: Not musical") are
   not asked (`derivatives.py`); a word with no other meaning is left out.

Quiz items and difficulty
-------------------------
Each quiz item is one meaning of a word, so a word with two common meanings can be
asked twice, at different difficulties. A word's most translated testable meaning is
always an item. Its other testable meanings are items if they appear in the age of
acquisition norms, or have `MIN_ITEM_TRANSLATIONS` translations and at least
`MIN_ITEM_SHARE` of the top meaning's, and are common enough on their own (the
word's rank divided by that share is within the pool). A word with no testable
meaning keeps its main meaning as its item, as before.

Difficulty comes from how many people know the meaning, not from frequency
(`difficulty.py`). Items are split into five levels of equal size, from the most to
the least widely known; within a level, items are ordered by how often a reader
meets them, which `CommonFirstSampler` in the app leans toward.

Definitions
-----------
Wiktionary orders senses by etymology and history, not by how common they are, so
senses are ranked by how many translations editors attached to them: translation
tables are written for the meanings people actually look up. A word keeps every
sense with at least `COMMON_SHARE` of its top sense's translations (at most six).
Words with too few translations to judge keep their first few senses in
dictionary order. Senses that sound regional or slangy, or only name a synonym
("mariner: Synonym of sailor"), are kept only if the word has nothing else. Long
definitions are cut at a clause boundary to fit a quiz option (`shorten`), and a
genus named after the word is dropped ("bison: A large, wild bovid of the genus
Bison"). Words whose every definition contains the word itself ("the quality of
being assertive") are skipped, since the answer would be obvious.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import orjson
from wordfreq import top_n_list, word_frequency

import derivatives
import difficulty
import norms
import spelling

# How many of the most common candidates are considered for the bank.
WORD_POOL = 40_000
# The most common words in the pool. Nearly every adult knows their main meaning, so
# they are asked only on later meanings that fewer than `COMMON_WORD_MAX_KNOWN` of
# adults are estimated to know (bill: a proposed law; table: to postpone).
REMOVED_COMMON_WORDS = 3_000
COMMON_WORD_MAX_KNOWN = 0.98
# Later meanings of common words are considered if they appear in the age-of-acquisition
# norms, or have this many translations and a different part of speech from the main
# meaning (table: to postpone; will: a legal document). Unmatched meanings of the same
# part of speech are mostly restatements of the main one (pace: a way of stepping) ...
COMMON_WORD_MIN_TRANSLATIONS = 10
# ... and are not matched to a meaning learned within this many years of the word's
# first (bill: the beak of a bird).
COMMON_WORD_MIN_AGE_GAP = 2.0
# At most this many later meanings per common word, so the meanings card still has
# room for the everyday ones (bank: the edge of a river).
COMMON_WORD_MAX_LATER = 3
# School and work words compete for a place, and for an early turn within their
# level, as if they were this many times more common.
SCHOOL_AND_WORK_BOOST = 2.0
# A word's other meanings become quiz items only if they are this well established.
MIN_ITEM_TRANSLATIONS = 3
MIN_ITEM_SHARE = 0.25
# Weights of each source in the blended rank (a weighted geometric mean of ranks).
SOURCE_WEIGHTS = {"fiction": 0.2, "books": 0.4, "wordfreq": 0.4}
BOOK_SOURCES = ("fiction", "books")
# In Google Books, a word with a capitalized Wiktionary entry whose Titlecase
# spelling is this many times more common than its lowercase one is mostly a name
# (Kate, Geneva; compare bill, smith, jean), so its lowercase count is mostly noise.
NAME_DOMINANCE = 20
# Words with no testable definition compete for a place in the list as if they were
# this many times rarer.
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
# Longer definitions are cut at a clause boundary (`shorten`) to fit a quiz option.
MIN_SHORTENED_LENGTH = 30
MIN_LAST_CLAUSE_WORDS = 3
TRAILING_CONJUNCTIONS = {"and", "or", "but"}
DANGLING_WORDS = {
    "a", "an", "the", "of", "to", "for", "in", "on", "at", "by", "with", "from", "as", "if", "than", "that",
    "which", "who", "whose", "into", "its", "their", "his", "her", "such", "especially", "usually", "often",
    "typically", "possibly", "mainly", "either", "both", "not", "nor", "also", "e.g", "i.e", "etc",
}
MAX_EXAMPLE_LENGTH = 150
PLURAL_OWN_MEANING_TRANSLATIONS = 10
PLURAL_FREQUENCY_SHARE = 0.35
HYPHENATED_MIN_TRANSLATIONS = 2
MAX_RELATED = 40
# Spelling variants (`use_american_spelling`): an entry under a British spelling with
# no link to the American one and at least this many translations is a different word.
DISTINCT_HOMOGRAPH_TRANSLATIONS = 10
# Share of content stems two definitions of the same word share when they are one
# meaning written twice.
SAME_MEANING_OVERLAP = 0.5
SPELLING_POINTER_RE = re.compile(r"\b(?:spelling|form) of ([a-z]+(?:-[a-z]+)*)")
SPELLING_REGION_TAGS = {
    "US", "UK", "British", "American", "Commonwealth", "Canada", "Australia", "New-Zealand", "Ireland",
    "South-Africa", "North-America",
}
SPELLING_REGION_RE = re.compile(
    r"\b(?:US|UK|British|American|Commonwealth|Canadian|Australian|Irish|Oxford|Britain|America)\b[^.;]*\bspelling of\b"
)

WORD_RE = re.compile(r"[a-z]+")
# Hyphenated headwords (t-shirt, x-ray, well-known). wordfreq estimates them from
# their parts, which wildly overrates compounds of common words ("to-do" would
# rank with "house"), so each extra part costs HYPHEN_PENALTY_ZIPF and the
# estimate is capped at HYPHEN_MAX_ZIPF.
HYPHENATED_RE = re.compile(r"[a-z]+(?:-[a-z]+)+")
HYPHEN_PENALTY_ZIPF = 1.2
HYPHEN_MAX_ZIPF = 3.8
POS_CODES = {"noun", "verb", "adj", "adv", "pron", "prep", "conj", "det", "intj", "num", "article", "particle"}

# "alternative" alone is not excluded: the extract tags all of "center" with it because
# "centre" is listed as an alternative form. Pointers to another spelling are caught
# by `alt_of` and `SKIPPED_GLOSS_RE` instead.
EXCLUDED_TAGS = {
    "form-of", "alt-of", "obsolete", "misspelling",
    "abbreviation", "initialism", "acronym", "contraction",
    "pronunciation-spelling", "eye-dialect", "no-gloss", "proscribed", "nonce-word",
    "misconstruction", "vulgar", "offensive", "slur", "ethnic", "euphemistic",
    "obsolete-sense", "historical-sense",
}
# Derogatory words are ordinary vocabulary (idiot, snob, philistine, petty), except
# when they insult a group of people (spinster, gringo, hick, geezer), are about sex,
# or push a political smear ("multiculturalism: the cultural Marxism conspiracy
# theory"). Those meanings are left out like slurs, and so are untranslated ones,
# which are mostly niche slang (chimp: to review photos on a camera). `blocklist.txt`
# covers the rest.
GROUP_INSULT_RE = re.compile(
    r"\b(?:wom[ae]n|girl|female|feminine|effeminate|wi(?:fe|ves)|lad(?:y|ie)|gay|homosexual\w*|lesbian|"
    r"bisexual\w*|transgender\w*|queer|black|white|asian|negro\w*|mexican|hispanic|latin[oa]|arab\w*|african|"
    r"chinese|japanese|korean|indian|pakistani|irish|scot\w*|welsh|english|british|italian|polish|french|german|"
    r"russian|race|racial\w*|ethnic\w*|descent|ancestry|stereotypical\w*|jew|jewish|catholic\w*|protestant\w*|"
    r"muslim|islam\w*|christian\w*|hindu|religio\w*|immigrant|foreign\w*|nationality|native|aborigin\w*|"
    r"countr(?:y|ies)|rural|hills|disab\w*|handicap\w*|crippl\w*|deform\w*|dwarf\w*|stature|obese|obesity|"
    r"overweight|retard\w*|damaged|elderly|old (?:person|people|man|men|woman|women)|"
    r"sex\w*|pervert\w*|kinky|abuser|offender|"
    r"communis\w*|socialis\w*|marxis\w*|globalis\w*|left-wing|right-wing|ideolog\w*|conspiracy|leftist|feminis\w*)"
    r"s?\b",
    re.I,
)
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
    r"BDSM|prostitution|pornograph|erotic|sex positions|recreational drugs|^sex$|^sexuality$", re.I
)
# Slur and swear-word categories exclude a meaning too, but the extract sometimes copies
# them to every meaning on the page ("peaceful: not at war" is filed under religious
# slurs because of a slang noun). Such a category is ignored on untagged meanings when
# it appears in more than one of the word's entries (`drop_slur_categories`).
SLUR_CATEGORY_RE = re.compile(r"slur|swear|vulgar|offensive|derogatory|insult", re.I)
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
    # "Plural form of", "Obsolete form of", but not "A form of government" (authoritarianism).
    r"\(?(?!(?:a|an|the|one|any|some|each|every)\b)\w+ form of )",
    re.I,
)
# "Synonym of somewhere else: in, at, or to some other place" and "Chiefly in the form a
# smidgen of: a very small quantity" carry a definition of their own after the colon.
DEFINITION_AFTER_COLON_RE = re.compile(
    r"^(?:synonym of [^:;()“”]+?|(?:chiefly|usually|often|mostly|generally) (?:in|with|as) [^:;()“”]+?): (?=\S)",
    re.I,
)
# Other "Synonym of sailor, particularly one on a ship" definitions name a synonym. They
# are used only for a word with nothing better (mariner, circa, penmanship).
SYNONYM_RE = re.compile(r"^synonym of (?=[a-z])", re.I)
# Usage notes rather than definitions ("Often followed by from").
USAGE_NOTE_RE = re.compile(
    r"^((often|usually|sometimes|chiefly|generally|especially|normally) )?(followed|preceded) by\b"
    r"|^(often|usually|chiefly|generally) (in|with|plural|negative|used)\b",
    re.I,
)
# Group headings written as glosses ("Senses referring to subjective quality"; "Synonym
# of pure and virtuous, particularly"); their sub-senses are the definitions.
HEADING_GLOSS_RE = re.compile(r"^senses? (?:referring|relating) to\b", re.I)
TRAILING_HEADING_RE = re.compile(r",? (?:particularly|especially|specifically|including|namely)$", re.I)
# "A large, wild bovid of the genus Bison": a taxon named after the word gives it away.
TAXON_RE = re.compile(
    r"(?:,? (?:or |and )?(?:of |in |from |within )?(?:the )?"
    r"(?:genus|subgenus|family|subfamily|order|suborder|class|tribe) [A-Z][a-z]+(?: and related genera)?)+"
)
# Glosses that only point at another spelling, wherever the phrase appears.
SPELLING_NOTE_RE = re.compile(r"\bspelling of\b|\bform of [a-z]+$", re.I)

WEAK_LINK_TAGS = {
    "obsolete", "archaic", "dated", "rare", "uncommon", "misspelling", "abbreviation", "initialism", "acronym",
    "eye-dialect", "pronunciation-spelling", "nonstandard", "dialectal", "slang", "Internet", "clipping",
}
ANAPHORIC_GLOSS_RE = re.compile(
    r"\bsuch an?\b(?! (?:way|manner|fashion|degree|extent)\b)|\bthe above\b|\bthis (sense|manner|way)\b"
    r"|^(any|a|an|some) similar\b",
    re.I,
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


def drop_own_taxon(gloss: str, word: str) -> str:
    """Removes taxa that repeat the word ("Any of several woody climbing vines, of the
    genus Wisteria, native to East Asia" for wisteria), so the definition can be tested."""
    def replace(match: re.Match) -> str:
        return "" if mentions_word(match.group(), word) else match.group()

    dropped = TAXON_RE.sub(replace, gloss).strip(" ,;")
    return dropped if len(dropped) >= 15 else gloss


def mentions_word(gloss: str, word: str) -> bool:
    """True if a definition uses the word itself (or an obvious relative), which
    would give the answer away."""
    target = stem(word)
    for token in re.split(r"[^a-z]+", gloss.lower()):
        if len(token) >= 3 and token not in STOP_WORDS and is_relative(stem(token), target):
            return True
    return False


def shorten(text: str) -> str:
    """Cuts a long definition at a clause boundary so it fits on a quiz option.

    "A distinctive member of the cat family, slightly smaller than the leopard, ...
    and a smaller head; native to Africa and southeast Asia and ..." keeps the part
    before the semicolon. Semicolons are tried first, then commas, latest first, to fit
    `MAX_QUIZ_GLOSS_LENGTH`, or failing that `MAX_GLOSS_LENGTH` (shown on the meanings
    card, not tested). The part kept must be a phrase of a few words that does not
    trail off ("for trial or" loses the "or"; "...optic nerve, possibly" is rejected).
    Returns `text` unchanged if no cut fits."""
    for limit in (MAX_QUIZ_GLOSS_LENGTH, MAX_GLOSS_LENGTH):
        if len(text) <= limit:
            return text
        cut = _cut(text, limit)
        if cut:
            return cut
    return text


def _cut(text: str, limit: int) -> str | None:
    for separator in ("; ", ", "):
        cuts = [m.start() for m in re.finditer(separator, text) if m.start() <= limit]
        for cut in reversed(cuts):
            words = text[:cut].split()
            while words and words[-1].lower() in TRAILING_CONJUNCTIONS:
                words.pop()
            kept = " ".join(words).rstrip(",;:")
            last_clause = re.split(r"[,;] ", kept)[-1]
            if (
                len(kept) >= MIN_SHORTENED_LENGTH
                and len(last_clause.split()) >= MIN_LAST_CLAUSE_WORDS
                and words[-1].lower() not in DANGLING_WORDS
            ):
                return kept
    return None


def clean_gloss(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = DEFINITION_AFTER_COLON_RE.sub("", text)
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
    # Slur or swear-word categories on an otherwise untagged meaning; see `SLUR_CATEGORY_RE`.
    slur_categories: frozenset[str] = frozenset()
    synonym: bool = False  # the definition only names a synonym; see `SYNONYM_RE`


@dataclass
class Candidate:
    word: str
    senses: list[Sense]
    related: set[str] = field(default_factory=set)
    flagged: bool = False  # first sense of the first entry is vulgar or offensive
    has_name_entry: bool = False
    # Entry index -> (part of speech, other spellings the entry links to, the subset
    # marked as regional); see `entry_links`.
    entries: dict[int, tuple[str, set[str], set[str]]] = field(default_factory=dict)
    # Slur or swear-word category -> indexes of the entries with a meaning filed under it.
    slur_categories: dict[str, set[int]] = field(default_factory=dict)


@dataclass(frozen=True)
class VocabSense:
    pos: str
    gloss: str
    example: str | None
    quizzable: bool
    translations: int = 0


@dataclass(frozen=True)
class BankSense:
    """A meaning as written to the bank."""

    pos: str
    gloss: str
    example: str | None
    quizzable: bool
    difficulty: int
    ease: float  # probit of the share of adults estimated to know this meaning
    ease_source: str  # see `difficulty.MeaningEase`
    is_item: bool
    # Order within a level: lower comes up sooner (how rare the meaning is, with
    # school and work words treated as more common).
    item_rank: float


@dataclass(frozen=True)
class VocabWord:
    word: str
    rank: int  # position in the frequency order of the pool (removed words included)
    related: tuple[str, ...]
    senses: tuple[BankSense, ...]

    @property
    def items(self) -> list[BankSense]:
        return [s for s in self.senses if s.is_item]


def load_blocklist(path: Path) -> set[str]:
    words = set()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            words.add(line)
    return words


def category_names(sense: dict) -> list[str]:
    return [c.get("name", "") if isinstance(c, dict) else str(c) for c in sense.get("categories", ())]


def slur_categories(sense: dict) -> frozenset[str]:
    return frozenset(name for name in category_names(sense) if SLUR_CATEGORY_RE.search(name))


def sense_flags(sense: dict, entry_translated: bool = False) -> tuple[bool, bool]:
    """Returns (excluded, secondary) for a raw Wiktionary sense. `entry_translated` says
    the sense is the first of an entry whose translation table belongs to no sense.
    Slur categories on an untagged sense are judged later, by `drop_slur_categories`."""
    tags = set(sense.get("tags", ())) | set(sense.get("raw_tags", ()))
    if sense.get("form_of") or sense.get("alt_of") or tags & EXCLUDED_TAGS:
        return True, False
    if "derogatory" in tags and (
        not (sense.get("translations") or entry_translated)
        or slur_categories(sense)
        or any(GROUP_INSULT_RE.search(g) for g in sense.get("glosses") or ())
    ):
        return True, False
    if set(sense.get("topics", ())) & EXCLUDED_TOPICS:
        return True, False
    if any(EXCLUDED_CATEGORY_RE.search(name) for name in category_names(sense)):
        return True, False
    regional = bool(tags & MINOR_REGION_TAGS) and not tags & MAJOR_REGION_TAGS
    return False, bool(tags & SECONDARY_TAGS) or regional


def pick_example(sense: dict, spellings: set[str]) -> str | None:
    """The first usage example that uses the word (in any of its `spellings`)."""
    for example in sense.get("examples", ()):
        if example.get("type") not in ("example", None):
            continue
        text = re.sub(r"\s+", " ", example.get("text", "")).strip()
        lowered = text.lower()
        if not text or len(text) > MAX_EXAMPLE_LENGTH or not any(s in lowered for s in spellings):
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


def entry_links(entry: dict) -> tuple[set[str], set[str]]:
    """Other spellings an entry points to (alternative forms, "alt_of" targets and
    "spelling of" pointers in its definitions, except misspellings, obsolete forms
    and the like), and the subset marked as regional ("US", "British spelling of")."""
    links: set[str] = set()
    regional: set[str] = set()

    def add(word: str, is_regional: bool) -> None:
        if word:
            links.add(word)
            if is_regional:
                regional.add(word)

    for form in entry.get("forms", ()):
        tags = set(form.get("tags") or ())
        if "alternative" in tags and not tags & WEAK_LINK_TAGS:
            add(form.get("form", ""), bool(tags & SPELLING_REGION_TAGS))
    for sense in entry.get("senses", ()):
        if set(sense.get("tags", ())) & WEAK_LINK_TAGS:
            continue  # "alot": misspelling of "a lot"
        tagged = bool(set(sense.get("tags", ())) & SPELLING_REGION_TAGS)
        glosses = sense.get("glosses") or ()
        named = any(SPELLING_REGION_RE.search(g) for g in glosses)
        for target in sense.get("alt_of", ()):
            add(target.get("word", ""), tagged or named)
        for gloss in glosses:
            for target in SPELLING_POINTER_RE.findall(gloss):
                add(target, tagged or named)
    return links, regional


def read_candidates(
    path: Path, vocabulary: set[str], variants: spelling.Variants
) -> tuple[dict[str, Candidate], dict[str, set[tuple[str, str]]], set[str]]:
    """Streams the Wiktionary extract once.

    Returns candidate base words (in the spelling of the entry, British or American),
    a map from a spelling to the words it is an inflection ("form_of") or alternative
    spelling ("alt_of") of, and the words that also have a capitalized entry.
    """
    candidates: dict[str, Candidate] = {}
    phrases: dict[str, Candidate] = {}  # see `rescue_from_phrases`
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
            # A phrase or accented spelling ("health care", "cliché") is read too when it is
            # written as a vocabulary word without spaces or accents; `rescue_from_phrases`
            # gives its definitions to that word if the word has none of its own.
            closed = None
            if not (WORD_RE.fullmatch(word) and word in vocabulary) and not HYPHENATED_RE.fullmatch(word):
                closed = fold_spelling(word)
                if closed == word or not (WORD_RE.fullmatch(closed) and closed in vocabulary):
                    continue

            index = entry_counts[word]
            entry_counts[word] += 1
            pool = phrases if closed else candidates
            candidate = pool.setdefault(word, Candidate(word=word, senses=[]))
            candidate.related |= related_terms(entry, None)
            candidate.entries[index] = (pos, *entry_links(entry))
            by_gloss = {s.gloss.lower(): s for s in candidate.senses}
            entry_translations = len(entry.get("translations", ()))
            first_kept: Sense | None = None
            # Examples may use another spelling of the word; they are respelled later.
            spellings = {closed} if closed else {word} | variants.others(word)

            for raw_index, sense in enumerate(entry.get("senses", ())):
                for category in slur_categories(sense):
                    candidate.slur_categories.setdefault(category, set()).add(index)
                # Inflections and alternative spellings pass their frequency to the main
                # word, but only through current, standard links ("went" -> "go", not
                # the obsolete "red" -> "rede").
                if closed is None and not set(sense.get("tags", ())) & WEAK_LINK_TAGS:
                    for kind in ("form_of", "alt_of"):
                        for form in sense.get(kind, ()):
                            base = form.get("word", "")
                            if base != word and (WORD_RE.fullmatch(base or "") or HYPHENATED_RE.fullmatch(base or "")):
                                inflection_of[word].add((base, kind))
                excluded, secondary = sense_flags(sense, raw_index == 0 and entry_translations > 0)
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
                heading = (
                    parent.endswith(":") or HEADING_GLOSS_RE.match(parent) or TRAILING_HEADING_RE.search(parent.rstrip(" ."))
                )
                gloss = clean_gloss(glosses[-1] if heading and len(glosses) > 1 else parent)
                gloss = drop_own_taxon(gloss, closed or word)
                synonym = SYNONYM_RE.match(gloss)
                if synonym:
                    gloss = gloss[synonym.end():]
                    gloss = gloss[:1].upper() + gloss[1:]
                    if mentions_word(gloss, closed or word):
                        continue  # "geological: Synonym of geologic"
                # The skip rules read the whole definition; a shortened one can end like
                # a spelling note ("a decarboxylated form of dopa").
                short = shorten(gloss)
                if (
                    len(gloss) < 3
                    or len(short) > MAX_GLOSS_LENGTH
                    or gloss.endswith(":")
                    or SKIPPED_GLOSS_RE.match(gloss)
                    or HEADING_GLOSS_RE.match(gloss)
                    or TRAILING_HEADING_RE.search(gloss)
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
                gloss = short
                existing = by_gloss.get(gloss.lower())
                if existing is not None:
                    existing.translations += translations
                    existing.secondary = existing.secondary and secondary
                    existing.synonym = existing.synonym and bool(synonym)
                    if existing.example is None:
                        existing.example = pick_example(sense, spellings)
                    continue
                kept = Sense(
                    pos=pos, gloss=gloss, example=pick_example(sense, spellings), secondary=secondary,
                    entry_index=index, order=len(candidate.senses), translations=translations,
                    slur_categories=slur_categories(sense), synonym=bool(synonym),
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
    for candidate in [*candidates.values(), *phrases.values()]:
        drop_slur_categories(candidate)
    rescue_from_phrases(candidates, phrases)
    return candidates, inflection_of, names


def fold_spelling(word: str) -> str:
    """"health care" -> "healthcare", "cliché" -> "cliche"."""
    decomposed = unicodedata.normalize("NFKD", word)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).replace(" ", "")


def rescue_from_phrases(candidates: dict[str, Candidate], phrases: dict[str, Candidate]) -> None:
    """Gives a word with no definitions of its own those of the phrase or accented
    spelling it is an alternative form of (healthcare: "health care", seatbelt: "seat
    belt", cliche: "cliché"), if the phrase is translated, as lexicalized compounds
    are. Links tagged as misspellings or nonstandard ("alot": "a lot") do not count."""
    for word, candidate in candidates.items():
        if candidate.senses:
            continue
        linked = sorted(set().union(*(found for _, found, _ in candidate.entries.values())))
        for phrase in linked:
            source = phrases.get(phrase)
            if source is None or fold_spelling(phrase) != word or not source.senses:
                continue
            if top_translations(source) < HYPHENATED_MIN_TRANSLATIONS:
                continue
            offset = max(candidate.entries, default=-1) + 1
            for sense in source.senses:
                sense.entry_index += offset
                sense.order = len(candidate.senses)
                candidate.senses.append(sense)
            for index, entry in source.entries.items():
                candidate.entries[offset + index] = entry
            candidate.related |= source.related
            break


def drop_slur_categories(candidate: Candidate) -> None:
    """Removes untagged meanings filed under a slur or swear-word category, unless the
    category is spread over several of the word's entries, which means the extract
    copied it from another meaning ("peaceful": adjective and noun alike)."""
    def genuine(category: str) -> bool:
        return len(candidate.slur_categories.get(category, ())) < 2

    candidate.senses = [s for s in candidate.senses if not any(genuine(c) for c in s.slur_categories)]
    for order, sense in enumerate(candidate.senses):
        sense.order = order


def content_stems(text: str) -> set[str]:
    return {stem(t) for t in re.split(r"[^a-z]+", text.lower()) if len(t) >= 3 and t not in STOP_WORDS}


def same_meaning(a: Sense, b: Sense) -> bool:
    """True for the same definition written twice, as in the British and American
    entries for one word ("The action of defending, of protecting from attack, danger
    or injury" / "The action of defending or protecting from attack, danger, or injury")."""
    if a.pos != b.pos:
        return False
    if a.gloss.lower() == b.gloss.lower():
        return True
    x, y = content_stems(a.gloss), content_stems(b.gloss)
    return bool(x and y) and len(x & y) / len(x | y) >= SAME_MEANING_OVERLAP


def use_american_spelling(
    candidates: dict[str, Candidate],
    inflection_of: dict[str, set[tuple[str, str]]],
    names: set[str],
    variants: spelling.Variants,
) -> spelling.Americanizer:
    """Respells definitions, examples and related words in American spelling, and moves
    each British spelling's entries to the American word (plough -> plow), which also
    gets the British spelling's frequency.

    An entry moves if Wiktionary links the two spellings (in either direction, for the
    same part of speech) or if it is barely translated. A well-translated entry with no
    link is a different word that happens to share the spelling (meagre: a fish) and is
    left out with the British spelling. See `spelling` for which spellings change."""

    def links(word: str, pos: str | None = None, regional: bool = False) -> set[str]:
        candidate = candidates.get(word)
        if candidate is None:
            return set()
        return set().union(
            *(r if regional else found for p, found, r in candidate.entries.values() if pos in (None, p))
        )

    table = dict(variants.verified)
    table.update({
        b: a for b, a in variants.unverified.items() if a in links(b, regional=True) or b in links(a, regional=True)
    })
    americanizer = spelling.Americanizer(table, names)

    for candidate in candidates.values():
        for sense in candidate.senses:
            sense.gloss = americanizer.text(sense.gloss)
            sense.example = americanizer.text(sense.example)
        candidate.related = {americanizer.word(t) for t in candidate.related}

    for word in sorted(w for w in candidates if w in table):
        american = table[word]
        source = candidates.pop(word)
        target = candidates.get(american)
        if target is None:
            target = candidates[american] = Candidate(
                word=american, senses=[], flagged=source.flagged, has_name_entry=american in names
            )

        def moves(index: int) -> bool:
            pos, found, _ = source.entries[index]
            if american in found or word in links(american, pos):
                return True
            translations = [s.translations for s in source.senses if s.entry_index == index]
            return max(translations, default=0) < DISTINCT_HOMOGRAPH_TRANSLATIONS

        offset = max(target.entries, default=-1) + 1
        moved = {index for index in source.entries if moves(index)}
        for index in moved:
            target.entries[offset + index] = source.entries[index]
        for category, indexes in source.slur_categories.items():
            target.slur_categories.setdefault(category, set()).update(offset + i for i in indexes & moved)
        for sense in source.senses:
            if sense.entry_index not in moved:
                continue
            sense.entry_index += offset
            duplicate = next((s for s in target.senses if same_meaning(s, sense)), None)
            if duplicate is None:
                sense.order = len(target.senses)
                target.senses.append(sense)
            else:
                duplicate.translations += sense.translations
                duplicate.secondary = duplicate.secondary and sense.secondary
                duplicate.synonym = duplicate.synonym and sense.synonym
                duplicate.example = duplicate.example or sense.example
        target.related |= source.related
        inflection_of[word].add((american, "alt_of"))

    # Inflections of British spellings ("ploughed" -> "plough") now count toward the
    # American word.
    for form, bases in inflection_of.items():
        inflection_of[form] = {(table.get(b, b), kind) for b, kind in bases if table.get(b, b) != form}
    return americanizer


def choose_senses(candidate: Candidate) -> list[Sense]:
    """The word's common senses, most common first."""
    primary = [s for s in candidate.senses if not s.secondary]
    pool = [s for s in primary if not s.synonym] or primary or candidate.senses
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


def is_quizzable(gloss: str, word: str) -> bool:
    return len(gloss) <= MAX_QUIZ_GLOSS_LENGTH and not mentions_word(gloss, word)


def vocab_sense(word: str, sense: Sense) -> VocabSense:
    return VocabSense(sense.pos, sense.gloss, sense.example, is_quizzable(sense.gloss, word), sense.translations)


@dataclass
class Prepared:
    """Candidates that passed the definition filters, ready to be ranked."""

    vocabulary: set[str]
    usable: dict[str, Candidate]
    chosen: dict[str, list[VocabSense]]
    inflection_of: dict[str, set[tuple[str, str]]]
    americanizer: spelling.Americanizer


def prepare(wiktionary_path: Path, blocklist_path: Path) -> Prepared:
    frequency_list = top_n_list("en", 1_000_000)
    vocabulary = {w for w in frequency_list if WORD_RE.fullmatch(w)}
    spelling.ensure_downloaded()
    variants = spelling.load_variants()
    candidates, inflection_of, names = read_candidates(wiktionary_path, vocabulary, variants)
    americanizer = use_american_spelling(candidates, inflection_of, names, variants)
    blocked = load_blocklist(blocklist_path)

    usable: dict[str, Candidate] = {}
    chosen: dict[str, list[VocabSense]] = {}
    for word, candidate in candidates.items():
        if word in blocked or candidate.flagged or (len(word) < 2 and word != "a"):
            continue
        def quizzable(sense: Sense) -> bool:
            return is_quizzable(sense.gloss, word)

        picked = choose_senses(candidate)
        if not any(quizzable(s) for s in picked):
            # A testable sense that missed the commonness cut is better than none.
            rescue = sorted(
                (s for s in candidate.senses if quizzable(s)),
                key=lambda s: (s.secondary, s.synonym, -s.translations, s.order),
            )
            if rescue:
                picked = (picked + rescue[:1])[-MAX_SENSES:]
        senses = [vocab_sense(word, s) for s in picked]
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

    return Prepared(vocabulary, usable, chosen, inflection_of, americanizer)


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


@dataclass
class Bank:
    """The words, plus what was fitted and counted on the way, for the build log."""

    words: list[VocabWord]
    model: difficulty.DifficultyModel
    cuts: list[float]
    counts: dict[str, int]


@dataclass
class _Entry:
    position: int
    word: str
    senses: list[VocabSense]
    first: int  # index of the main meaning
    items: set[int]
    common: bool = False  # one of the `REMOVED_COMMON_WORDS`, asked only on later meanings


def mentions_inflection(gloss: str, word: str) -> bool:
    """True if a definition uses the word or an inflected form of it ("run: Act or
    instance of running"), which restates the main meaning and gives the answer away."""
    for token in re.split(r"[^a-z]+", gloss.lower()):
        if token == word or word in derivatives.uninflected(token):
            return True
    return False


def common_word_meanings(
    word: str, candidate: Candidate, chosen: list[VocabSense], matcher: difficulty.MeaningMatcher
) -> tuple[list[VocabSense], set[int]]:
    """For one of the `REMOVED_COMMON_WORDS`: the meanings to show, main meaning first,
    and the indexes of later meanings that may be worth asking.

    The usual commonness cut keeps meanings with a good share of the main meaning's
    translations, which for "table" (330) drops "to postpone" (13). Here a later
    meaning qualifies if it is testable, does not use the word itself, and either is
    matched in the age-of-acquisition norms to a meaning learned at least
    `COMMON_WORD_MIN_AGE_GAP` years after the word's first, or is unmatched with
    `COMMON_WORD_MIN_TRANSLATIONS` translations and a different part of speech from
    the main meaning. Up to `COMMON_WORD_MAX_LATER` later meanings are kept, matched
    ones first, then the most translated; the usual common meanings fill the rest of
    the meanings card."""
    primary = [s for s in candidate.senses if not s.secondary]
    pool = [s for s in primary if not s.synonym] or primary or candidate.senses
    main = max(pool, key=lambda s: (s.translations, -s.order))
    first_age = matcher.first_age(word) if word in matcher.meaning_ages else None

    matches = {id(s): matcher.match(word, s.gloss) for s in pool}

    def is_later(sense: Sense) -> bool:
        if sense is main or not is_quizzable(sense.gloss, word) or mentions_inflection(sense.gloss, word):
            return False
        match = matches[id(sense)]
        if match is not None:
            return match.age - first_age >= COMMON_WORD_MIN_AGE_GAP
        return sense.translations >= COMMON_WORD_MIN_TRANSLATIONS and sense.pos != main.pos

    def commonness(sense: Sense) -> tuple[int, int]:
        return -sense.translations, sense.order

    later = sorted(
        (s for s in pool if is_later(s)), key=lambda s: (matches[id(s)] is None, *commonness(s))
    )[:COMMON_WORD_MAX_LATER]
    later_ids = {id(s) for s in later}
    chosen_glosses = {s.gloss for s in chosen}
    others = sorted(
        (s for s in candidate.senses if s.gloss in chosen_glosses and s is not main and id(s) not in later_ids),
        key=commonness,
    )
    picked = ([main] + later + others)[:MAX_SENSES]
    shown = [main] + sorted(picked[1:], key=commonness)
    return [vocab_sense(word, s) for s in shown], {i for i, s in enumerate(shown) if id(s) in later_ids}


def choose_items(
    senses: list[VocabSense], transparent: list[bool], word_rank: float, pool_limit: float, in_norms
) -> tuple[int, set[int]] | None:
    """The word's main meaning and the meanings to ask, or None if nothing is worth
    asking. `in_norms(gloss)` says whether a meaning is in the age-of-acquisition norms."""
    open_meanings = [i for i, s in enumerate(senses) if not transparent[i]]
    if not open_meanings:
        return None
    testable = [i for i in open_meanings if senses[i].quizzable]
    # A word with no testable meaning is still asked on its main meaning, as before.
    first = max(testable or open_meanings, key=lambda i: (senses[i].translations, -i))
    items = {first}
    top = max(senses[i].translations for i in open_meanings)
    for i in testable:
        if i == first:
            continue
        share = (senses[i].translations + 1) / (top + 1)
        established = in_norms(senses[i].gloss) or (
            senses[i].translations >= MIN_ITEM_TRANSLATIONS and share >= MIN_ITEM_SHARE
        )
        if established and word_rank / share <= pool_limit:
            items.add(i)
    return first, items


def american_keys(table: dict, american: spelling.Americanizer) -> dict:
    """`table` keyed by American spellings. The norms list a few words only under a
    British spelling (centre, cheque); where both are listed, the American entry wins."""
    respelled = {american.word(k): v for k, v in table.items() if american.word(k) != k}
    return respelled | {k: v for k, v in table.items() if american.word(k) == k}


def rank(prepared: Prepared, books: dict[str, Path], ranks: dict[str, dict[str, float]] | None = None) -> Bank:
    usable, chosen = prepared.usable, prepared.chosen
    ranks = ranks if ranks is not None else source_ranks(prepared, books)
    scores = blended_rank(ranks)
    norms.ensure_downloaded()
    american = prepared.americanizer
    school_and_work = {american.word(w) for w in norms.load_school_and_work_words()}
    meaning_ages = american_keys(
        {w: [norms.MeaningAge(american.text(m.description), m.age) for m in ms]
         for w, ms in norms.load_meaning_ages().items()},
        american,
    )
    prevalence = american_keys(norms.load_prevalence(), american)

    def boost(word: str) -> float:
        return SCHOOL_AND_WORK_BOOST if word in school_and_work else 1.0

    # Prefer words with a testable definition: words whose definitions all lean on
    # the word itself ("in a grateful manner") need to be more common to get in.
    def selection_rank(word: str) -> float:
        testable = any(s.quizzable for s in chosen[word])
        return scores[word] * (1 if testable else UNTESTABLE_RANK_PENALTY) / boost(word)

    def doubtful(word: str) -> bool:
        return (
            len(word) <= SHORT_WORD_LENGTH
            and scores[word] > SHORT_WORD_MAX_RANK
            and top_translations(usable[word]) < SHORT_WORD_TRANSLATIONS
        )

    eligible = [w for w in scores if not doubtful(w)]
    if len(eligible) < WORD_POOL:
        raise SystemExit(f"Only {len(eligible)} usable words; need {WORD_POOL}.")
    pool = sorted(eligible, key=lambda w: (selection_rank(w), w))[:WORD_POOL]
    ordered = sorted(pool, key=lambda w: (scores[w], w))
    pool_limit = scores[ordered[-1]]
    matcher = difficulty.MeaningMatcher(
        meaning_ages, [s.gloss for w in ordered for s in chosen[w]], stem, STOP_WORDS, stems_match
    )

    counts = {"pool": len(ordered), "common words left out": 0, "removed as transparent": 0, "transparent meanings": 0}
    entries: list[_Entry] = []
    for position, word in enumerate(ordered, start=1):

        def is_more_common(base: str, word: str = word) -> bool:
            return base in usable and scores.get(base, math.inf) < scores[word]

        if position <= REMOVED_COMMON_WORDS:
            senses, later = common_word_meanings(word, usable[word], chosen[word], matcher)
            transparent = [derivatives.transparent_base(word, s.gloss, is_more_common) is not None for s in senses]
            items = {i for i in later if not transparent[i]}
            if items:
                entries.append(_Entry(position, word, senses, 0, items, common=True))
            else:
                counts["common words left out"] += 1
            continue
        senses = chosen[word]
        transparent = [derivatives.transparent_base(word, s.gloss, is_more_common) is not None for s in senses]
        choice = choose_items(senses, transparent, scores[word], pool_limit, lambda g, w=word: matcher.match(w, g) is not None)
        if choice is None:
            counts["removed as transparent"] += 1
            continue
        counts["transparent meanings"] += sum(transparent)
        entries.append(_Entry(position, word, senses, *choice))

    # Calibrated on the words asked on their main meaning; the common words' later
    # meanings are then judged on the same scale.
    model = difficulty.DifficultyModel(
        [e.word for e in entries if not e.common], scores, prevalence, matcher
    )
    eases = {
        (e.word, i): model.meaning_ease(e.word, s.gloss, is_first=i == e.first)
        for e in entries for i, s in enumerate(e.senses)
    }
    for e in entries:
        if e.common:
            e.items = {i for i in e.items if difficulty.share_of_ease(eases[(e.word, i)].ease) < COMMON_WORD_MAX_KNOWN}
            if not e.items:
                counts["common words left out"] += 1
    entries = [e for e in entries if e.items]
    common = [e for e in entries if e.common]
    counts["common words asked on later meanings"] = len(common)
    counts["later meanings of common words"] = sum(len(e.items) for e in common)
    cuts = difficulty.level_cuts([eases[(e.word, i)].ease for e in entries for i in e.items])

    words: list[VocabWord] = []
    for e in entries:
        related = sorted(t for t in usable[e.word].related if t != e.word)[:MAX_RELATED]
        top = max(s.translations for s in e.senses)
        bank_senses = []
        for i, s in enumerate(e.senses):
            ease = eases[(e.word, i)]
            share = (s.translations + 1) / (top + 1)
            bank_senses.append(BankSense(
                s.pos, s.gloss, s.example, s.quizzable, difficulty.level_for(ease.ease, cuts), ease.ease,
                ease.source, i in e.items, scores[e.word] / boost(e.word) / share,
            ))
        words.append(VocabWord(e.word, e.position, tuple(related), tuple(bank_senses)))
    respelled = [w.word for w in words if american.word(w.word) != w.word]
    if respelled:
        raise SystemExit(f"Non-American spellings in the bank: {respelled[:10]}")
    counts["words"] = len(words)
    counts["items"] = sum(len(w.items) for w in words)
    return Bank(words, model, cuts, counts)


def build(wiktionary_path: Path, blocklist_path: Path, books: dict[str, Path]) -> Bank:
    """`books` maps each of `BOOK_SOURCES` to a `google_books.py` output file."""
    return rank(prepare(wiktionary_path, blocklist_path), books)


# Common words whose later meanings the report lists.
# Bump when `Prepared` or what `prepare` produces changes, so --reuse reparses.
PREPARED_VERSION = 2

COMMON_PROBE_WORDS = ("table", "bill", "run", "will", "novel", "minute", "court", "pupil", "fine", "bank", "have")

PROBE_WORDS = (
    "however", "meanwhile", "bill", "email", "website", "smartphone", "pestilence", "panacea",
    "importunately", "somnambulant", "inapposite", "hypogammaglobulinemia", "ragequit", "autosave",
    "stakeholder", "bipartisan", "workflow", "fiduciary", "photosynthesis", "hypotenuse", "denominator",
    "lugubrious", "vicissitude", "obsequious", "pip", "fess", "unmusical", "believably", "unprecedented",
    "theater", "plow", "jewelry", "defense", "tire", "check", "peaceful", "cheetah", "journalism", "idiot",
    "superstition", "authoritarianism", "elsewhere",
)


def report(prepared: Prepared, books: dict[str, Path], seed: int) -> None:
    """Prints what a build would produce, for tuning by eye."""
    import random

    ranks = source_ranks(prepared, books)
    bank = rank(prepared, books, ranks)
    model, by_word = bank.model, {w.word: w for w in bank.words}
    print(", ".join(f"{k}: {v}" for k, v in bank.counts.items()))
    print("model:", model.counts, f"secondary gap {model.secondary_gap:.2f} years, ease per year {model.age_slope:.3f}")
    print(f"  ease ~ rank + first age: {[round(c, 3) for c in model.with_age]} "
          f"(R2 {model.with_age_r2:.2f}, residual sd {model.with_age_sd:.2f})")
    print(f"  ease ~ rank: {[round(c, 3) for c in model.rank_only]} "
          f"(R2 {model.rank_only_r2:.2f}, residual sd {model.rank_only_sd:.2f})")
    print("level cuts (share who know):", [f"{difficulty.share_of_ease(c):.1%}" for c in bank.cuts])
    sources = defaultdict(int)
    for w in bank.words:
        for s in w.items:
            sources[s.ease_source] += 1
    print("item difficulty from:", dict(sources))

    rng = random.Random(seed)
    items = [(w, s) for w in bank.words for s in w.items]
    for level in range(1, difficulty.LEVELS + 1):
        band = [(w, s) for w, s in items if s.difficulty == level]
        print(f"\n== level {level}: {len(band)} items, e.g.")
        for w, s in sorted(rng.sample(band, 16), key=lambda t: t[1].item_rank):
            print(f"  {w.word:<18} {difficulty.share_of_ease(s.ease):6.1%}  {s.gloss[:70]}")

    print("\n== later meanings of common words")
    for word in COMMON_PROBE_WORDS:
        entry = by_word.get(word)
        print(f"  {word} (rank {entry.rank if entry else '-'})" + ("" if entry else ": not asked"))
        for sense in entry.senses if entry else ():
            mark = f"L{sense.difficulty} {difficulty.share_of_ease(sense.ease):6.1%}" if sense.is_item else " " * 10
            print(f"    {mark}  {sense.pos:<5} {sense.gloss[:75]}")

    def source_rank(source: str, word: str) -> str:
        value = ranks[source].get(word)
        return f"{value:>9.0f}" if value else "        -"

    print(f"\n{'probe':<22}{'rank':>7}" + "".join(f"{s:>10}" for s in SOURCE_WEIGHTS) + "  items (level, share who know)")
    for word in PROBE_WORDS:
        entry = by_word.get(word)
        final = entry.rank if entry else "-"
        found = ", ".join(f"L{s.difficulty} {difficulty.share_of_ease(s.ease):.0%}" for s in entry.items) if entry else ""
        print(f"{word:<22}{final:>7}" + "".join(f" {source_rank(s, word)}" for s in SOURCE_WEIGHTS) + f"  {found}")


if __name__ == "__main__":
    import pickle
    import sys

    here = Path(__file__).parent
    books = {"fiction": here / ".cache" / "google-books" / "eng-fiction.tsv",
             "books": here / ".cache" / "google-books" / "eng.tsv"}
    # --reuse keeps the parsed Wiktionary candidates between runs (parsing takes minutes).
    # Versioned: an older parse lacks fields that ranking needs.
    cached = here / ".cache" / f"vocabulary-prepared-v{PREPARED_VERSION}.pickle"
    if "--reuse" in sys.argv and cached.exists():
        prepared = pickle.loads(cached.read_bytes())
    else:
        prepared = prepare(here / ".cache" / "kaikki-english.jsonl", here / "blocklist.txt")
        cached.write_bytes(pickle.dumps(prepared))
    seeds = [int(a) for a in sys.argv[1:] if a.isdigit()]
    report(prepared, books, seeds[0] if seeds else 7)
