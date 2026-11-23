"""Builds Knowledge/Resources/content.sqlite, the question bank shipped in the app.

Usage (from the repository root):

    python3 -m venv tools/content/.venv
    tools/content/.venv/bin/pip install -r tools/content/requirements.txt
    curl -L -o tools/content/.cache/kaikki-english.jsonl \\
        https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl
    tools/content/.venv/bin/python -I tools/content/google_books.py   # streams ~18 GB once
    tools/content/.venv/bin/python tools/content/build_content.py   # also downloads the norms, VarCon,
                                                                    # Natural Earth, flags and pageviews
    tools/content/.venv/bin/python tools/content/build_content.py --reuse   # reuse the cached Wiktionary parse

The output is deterministic for a given Wiktionary extract, Google Books reduction,
wordfreq version, set of norms and geography cache (`.cache/geography/`).

Schema (version `SCHEMA_VERSION`, stored in PRAGMA user_version; the app checks it
against `ContentStore.schemaVersion`):

    math_questions  one row per arithmetic problem. IDs are contiguous for each
                    (difficulty, operation) pair.
    vocab_words     one row per word, in frequency order. `frequency_rank` is the
                    word's position among the most common `WORD_POOL` candidates.
                    The most common `REMOVED_COMMON_WORDS` are asked only on later
                    meanings; their main meaning is listed first (sense_order 0).
                    `related` lists synonyms and hypernyms (space separated) used
                    to reject unfair distractors.
    vocab_senses    the common definitions of each word, each with its own
                    difficulty. IDs are contiguous per (pos, difficulty) so the app
                    can sample distractors by ID range.
    vocab_items     the quiz items: one meaning (sense) each. IDs are contiguous per
                    difficulty and, within a level, ordered from the most to the
                    least often met, so the app can lean toward the front.
    geo_regions     every country, territory and US state drawn on maps, with its
                    label point, close-up and zoomed-out frames, and for quiz places
                    the capital and notes (see geography.py).
    geo_shapes      each region's outline at two levels of detail (geography.encode_shape).
    geo_flags       flag images (WebP) of the quiz countries, with source and license.
    geo_related     per quiz place, its nearest places ('neighbor') and, for countries,
                    the most similar flags ('lookalike'), ranked.
    geo_decoys      famous non-capital cities used as tempting wrong capitals.
    geo_items       the geography quiz items. IDs are contiguous per (difficulty,
                    category); the categories are map, flag and capital.
    meta            build information.
"""

from __future__ import annotations

import pickle
import random
import sqlite3
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import difficulty
import geography
import mental_math
import vocabulary

SCHEMA_VERSION = 3
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUTPUT = ROOT / "Knowledge" / "Resources" / "content.sqlite"
WIKTIONARY = HERE / ".cache" / "kaikki-english.jsonl"
GOOGLE_BOOKS = {
    "fiction": HERE / ".cache" / "google-books" / "eng-fiction.tsv",
    "books": HERE / ".cache" / "google-books" / "eng.tsv",
}
BLOCKLIST = HERE / "blocklist.txt"
PREPARED = HERE / ".cache" / f"vocabulary-prepared-v{vocabulary.PREPARED_VERSION}.pickle"
SHUFFLE_SEED = 4242

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE math_questions (
    id INTEGER PRIMARY KEY,
    operation TEXT NOT NULL,
    lhs INTEGER NOT NULL,
    rhs INTEGER NOT NULL,
    answer INTEGER NOT NULL,
    distractor1 INTEGER NOT NULL,
    distractor2 INTEGER NOT NULL,
    distractor3 INTEGER NOT NULL,
    difficulty INTEGER NOT NULL
);
CREATE TABLE vocab_words (
    id INTEGER PRIMARY KEY,
    word TEXT NOT NULL UNIQUE,
    frequency_rank INTEGER NOT NULL,
    related TEXT NOT NULL
);
CREATE TABLE vocab_senses (
    id INTEGER PRIMARY KEY,
    word_id INTEGER NOT NULL REFERENCES vocab_words(id),
    sense_order INTEGER NOT NULL,
    pos TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    gloss TEXT NOT NULL,
    example TEXT,
    quizzable INTEGER NOT NULL
);
CREATE INDEX vocab_senses_by_word ON vocab_senses(word_id, sense_order);
CREATE TABLE vocab_items (
    id INTEGER PRIMARY KEY,
    sense_id INTEGER NOT NULL UNIQUE REFERENCES vocab_senses(id),
    difficulty INTEGER NOT NULL
);
CREATE TABLE geo_regions (
    id INTEGER PRIMARY KEY,
    layer TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    continent TEXT NOT NULL,
    subregion TEXT NOT NULL,
    area_name TEXT NOT NULL,
    area_km2 REAL NOT NULL,
    quizzable INTEGER NOT NULL,
    label_lon REAL NOT NULL,
    label_lat REAL NOT NULL,
    frame_lon REAL NOT NULL,
    frame_lat REAL NOT NULL,
    frame_x REAL NOT NULL,
    frame_y REAL NOT NULL,
    frame_min REAL NOT NULL,
    context_lon REAL NOT NULL,
    context_lat REAL NOT NULL,
    context_x REAL NOT NULL,
    context_y REAL NOT NULL,
    capital TEXT,
    capital_note TEXT,
    flag_note TEXT,
    UNIQUE (layer, code)
);
CREATE TABLE geo_shapes (
    region_id INTEGER PRIMARY KEY REFERENCES geo_regions(id),
    fine BLOB NOT NULL,
    coarse BLOB NOT NULL
);
CREATE TABLE geo_flags (
    region_id INTEGER PRIMARY KEY REFERENCES geo_regions(id),
    image BLOB NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    source TEXT NOT NULL,
    license TEXT NOT NULL
);
CREATE TABLE geo_related (
    region_id INTEGER NOT NULL REFERENCES geo_regions(id),
    relation TEXT NOT NULL,
    rank INTEGER NOT NULL,
    other_id INTEGER NOT NULL REFERENCES geo_regions(id),
    PRIMARY KEY (region_id, relation, rank)
);
CREATE TABLE geo_decoys (
    region_id INTEGER NOT NULL REFERENCES geo_regions(id),
    city TEXT NOT NULL
);
CREATE TABLE geo_items (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    category TEXT NOT NULL,
    region_id INTEGER NOT NULL REFERENCES geo_regions(id),
    difficulty INTEGER NOT NULL
);
"""


def write_math(db: sqlite3.Connection, rng: random.Random) -> int:
    questions = mental_math.generate()
    groups: dict[tuple[int, str], list[mental_math.MathQuestion]] = {}
    for question in questions:
        groups.setdefault((question.difficulty, question.operation), []).append(question)
    next_id = 1
    for key in sorted(groups):
        group = groups[key]
        rng.shuffle(group)
        for q in group:
            db.execute(
                "INSERT INTO math_questions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (next_id, q.operation, q.lhs, q.rhs, q.answer, *q.distractors, q.difficulty),
            )
            next_id += 1
    return len(questions)


class _PreparedUnpickler(pickle.Unpickler):
    """`vocabulary.py --reuse` pickles from `__main__`; its classes live in `vocabulary`."""

    def find_class(self, module: str, name: str):
        return super().find_class("vocabulary" if module == "__main__" else module, name)


def write_vocabulary(db: sqlite3.Connection, rng: random.Random) -> vocabulary.Bank:
    # --reuse keeps the parsed Wiktionary candidates between runs, like vocabulary.py.
    if "--reuse" in sys.argv and PREPARED.exists():
        with PREPARED.open("rb") as handle:
            prepared = _PreparedUnpickler(handle).load()
    else:
        prepared = vocabulary.prepare(WIKTIONARY, BLOCKLIST)
        PREPARED.write_bytes(pickle.dumps(prepared))
    bank = vocabulary.rank(prepared, GOOGLE_BOOKS)
    senses = []
    for word_id, word in enumerate(bank.words, start=1):
        db.execute(
            "INSERT INTO vocab_words VALUES (?, ?, ?, ?)",
            (word_id, word.word, word.rank, " ".join(word.related)),
        )
        for order, sense in enumerate(word.senses):
            senses.append((sense.pos, sense.difficulty, rng.random(), word_id, order, sense))
    senses.sort(key=lambda row: row[:3])
    items = []
    for sense_id, (pos, level, _, word_id, order, sense) in enumerate(senses, start=1):
        db.execute(
            "INSERT INTO vocab_senses VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sense_id, word_id, order, pos, level, sense.gloss, sense.example, int(sense.quizzable)),
        )
        if sense.is_item:
            items.append((level, sense.item_rank, word_id, order, sense_id))
    items.sort()
    db.executemany(
        "INSERT INTO vocab_items VALUES (?, ?, ?)",
        [(item_id, sense_id, level) for item_id, (level, *_, sense_id) in enumerate(items, start=1)],
    )
    return bank


def write_geography(db: sqlite3.Connection) -> geography.Atlas:
    atlas = geography.build()
    ids = {id(region): number for number, region in enumerate(atlas.regions, start=1)}
    for region in atlas.regions:
        place = region.place
        db.execute(
            "INSERT INTO geo_regions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ids[id(region)], region.layer, region.code, region.name, region.continent, region.subregion,
             region.area_name, round(region.area_km2, 3), int(place is not None), *region.label, *region.frame,
             region.frame_min, *region.context, place.capital if place else None,
             place.capital_note if place else None, place.flag_note if place else None),
        )
        db.execute("INSERT INTO geo_shapes VALUES (?, ?, ?)",
                   (ids[id(region)], geography.encode_shape(region.fine), geography.encode_shape(region.coarse)))
        if region.flag:
            db.execute("INSERT INTO geo_flags VALUES (?, ?, ?, ?, ?, ?)",
                       (ids[id(region)], region.flag, *region.flag_size, place.flag_file, region.flag_license))
        for relation, others in (("neighbor", region.neighbors), ("lookalike", region.lookalikes)):
            db.executemany("INSERT INTO geo_related VALUES (?, ?, ?, ?)",
                           [(ids[id(region)], relation, rank, ids[id(other)]) for rank, other in enumerate(others)])
        if place:
            db.executemany("INSERT INTO geo_decoys VALUES (?, ?)", [(ids[id(region)], city) for city in place.decoys])
    items = sorted(atlas.items, key=lambda i: (i.difficulty, geography.ITEM_KINDS[i.kind], i.kind, -i.score, i.region.code))
    db.executemany(
        "INSERT INTO geo_items VALUES (?, ?, ?, ?, ?)",
        [(number, item.kind, geography.ITEM_KINDS[item.kind], ids[id(item.region)], item.difficulty)
         for number, item in enumerate(items, start=1)],
    )
    return atlas


def validate(db: sqlite3.Connection) -> None:
    def contiguous(table: str, group: str) -> None:
        for row in db.execute(f"SELECT {group}, MIN(id), MAX(id), COUNT(*) FROM {table} GROUP BY {group}"):
            *_, first, last, count = row
            assert last - first + 1 == count, f"{table} IDs not contiguous for {row}"

    contiguous("math_questions", "difficulty, operation")
    contiguous("vocab_senses", "pos, difficulty")
    contiguous("vocab_items", "difficulty")
    contiguous("geo_items", "difficulty, category")

    math_count = db.execute("SELECT COUNT(*) FROM math_questions").fetchone()[0]
    unique = db.execute("SELECT COUNT(*) FROM (SELECT DISTINCT operation, lhs, rhs FROM math_questions)").fetchone()[0]
    assert math_count >= 10_000 and unique == math_count, (math_count, unique)
    evaluate = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b, "/": lambda a, b: a / b}
    for op, a, b, answer, d1, d2, d3 in db.execute(
        "SELECT operation, lhs, rhs, answer, distractor1, distractor2, distractor3 FROM math_questions"
    ):
        assert evaluate[op](a, b) == answer, (op, a, b, answer)
        assert len({answer, d1, d2, d3}) == 4 and min(d1, d2, d3) >= 0, (op, a, b, answer, d1, d2, d3)

    main_meanings_of_common_words = db.execute(
        "SELECT COUNT(*) FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id "
        "JOIN vocab_words w ON w.id = s.word_id WHERE w.frequency_rank <= ? AND s.sense_order = 0",
        (vocabulary.REMOVED_COMMON_WORDS,),
    ).fetchone()[0]
    assert main_meanings_of_common_words == 0, main_meanings_of_common_words
    unasked = db.execute(
        "SELECT COUNT(*) FROM vocab_words w WHERE NOT EXISTS "
        "(SELECT 1 FROM vocab_items i JOIN vocab_senses s ON s.id = i.sense_id WHERE s.word_id = w.id)"
    ).fetchone()[0]
    assert unasked == 0, unasked
    mismatched = db.execute(
        "SELECT COUNT(*) FROM vocab_items i LEFT JOIN vocab_senses s ON s.id = i.sense_id "
        "WHERE s.id IS NULL OR s.difficulty != i.difficulty"
    ).fetchone()[0]
    assert mismatched == 0, mismatched
    levels = db.execute("SELECT COUNT(DISTINCT difficulty) FROM vocab_items").fetchone()[0]
    assert levels == 5, levels

    # Geography: every kind is split into five equal levels, every quiz place has a
    # shape, every country a flag, and no capital question gives itself away.
    for kind, sizes in db.execute(
        "SELECT kind, group_concat(n) FROM (SELECT kind, difficulty, COUNT(*) n FROM geo_items "
        "GROUP BY kind, difficulty) GROUP BY kind"
    ):
        counts = [int(n) for n in sizes.split(",")]
        assert len(counts) == 5 and max(counts) - min(counts) <= 1, (kind, counts)
    expected = {"country_map": 196, "country_flag": 196, "state_map": 50}
    for kind, count in expected.items():
        found = db.execute("SELECT COUNT(*) FROM geo_items WHERE kind = ?", (kind,)).fetchone()[0]
        assert found == count, (kind, found)
    unshaped = db.execute(
        "SELECT COUNT(*) FROM geo_regions r LEFT JOIN geo_shapes s ON s.region_id = r.id "
        "WHERE s.region_id IS NULL OR length(s.fine) < 32 OR length(s.coarse) < 32"  # one ring of 3 points
    ).fetchone()[0]
    assert unshaped == 0, unshaped
    flagless = db.execute(
        "SELECT COUNT(*) FROM geo_regions r LEFT JOIN geo_flags f ON f.region_id = r.id "
        "WHERE r.layer = 'world' AND r.quizzable = 1 AND f.region_id IS NULL"
    ).fetchone()[0]
    assert flagless == 0, flagless
    for name, capital in db.execute(
        "SELECT r.name, r.capital FROM geo_items i JOIN geo_regions r ON r.id = i.region_id "
        "WHERE i.category = 'capital'"
    ):
        assert capital and capital.casefold() not in name.casefold() and name.casefold() not in capital.casefold(), name


def main() -> None:
    if not WIKTIONARY.exists():
        sys.exit(f"Missing {WIKTIONARY}. See the module docstring for the download command.")
    missing = [path for path in GOOGLE_BOOKS.values() if not path.exists()]
    if missing:
        sys.exit(f"Missing {', '.join(map(str, missing))}. Run tools/content/google_books.py first.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".building")
    temporary.unlink(missing_ok=True)

    db = sqlite3.connect(temporary)
    db.executescript(SCHEMA)
    rng = random.Random(SHUFFLE_SEED)
    with db:
        math_count = write_math(db, rng)
        bank = write_vocabulary(db, rng)
        atlas = write_geography(db)
        model = bank.model
        sense_count = db.execute("SELECT COUNT(*) FROM vocab_senses").fetchone()[0]
        meta = {
            "schema_version": str(SCHEMA_VERSION),
            "math_questions": str(math_count),
            "vocab_words": str(len(bank.words)),
            "vocab_senses": str(sense_count),
            "vocab_items": str(bank.counts["items"]),
            "wordfreq_version": version("wordfreq"),
            "definitions_source": "English Wiktionary via kaikki.org (CC BY-SA 4.0)",
            "frequency_source": (
                "Google Books Ngram v3 English Fiction and English (CC BY 3.0), blended with wordfreq (CC BY-SA 4.0)"
            ),
            "google_books_years": "1920-2019, or 2000-2019 when higher",
            "frequency_weights": ", ".join(f"{k} {v}" for k, v in vocabulary.SOURCE_WEIGHTS.items()),
            "word_pool": (
                f"{vocabulary.WORD_POOL} most common; the {vocabulary.REMOVED_COMMON_WORDS} most common only on later "
                f"meanings known by fewer than {vocabulary.COMMON_WORD_MAX_KNOWN:.0%}"
            ),
            "spelling": "American, from VarCon (Kevin Atkinson and Benjamin Titze, SCOWL)",
            "school_and_work_lists": (
                f"NAWL 1.2 and BSL 1.2 (Browne, Culligan & Phillips, CC BY-SA 4.0), boost {vocabulary.SCHOOL_AND_WORK_BOOST}"
            ),
            "difficulty_source": (
                "Word prevalence norms (Brysbaert, Mandera, McCormick & Keuleers 2019) and test-based "
                "age-of-acquisition norms for word meanings (Brysbaert & Biemiller 2017)"
            ),
            "difficulty_levels": "equal fifths of items; level cuts at "
            + ", ".join(f"{difficulty.share_of_ease(c):.3f}" for c in bank.cuts)
            + " share of adults who know the meaning",
            "difficulty_model": (
                f"ease ~ {model.with_age[0]:.3f} + {model.with_age[1]:.3f} ln(rank) + {model.with_age[2]:.3f} age; "
                f"ease ~ {model.rank_only[0]:.3f} + {model.rank_only[1]:.3f} ln(rank); "
                f"{model.age_slope:.3f} per year of meaning age; later meanings {model.secondary_gap:.2f} years"
            ),
            "geo_items": ", ".join(f"{kind} {count}" for kind, count in atlas.counts.items()),
            "geo_sources": (
                "Natural Earth 1:10m admin 0 (United States point of view) and admin 1, and lakes (public domain); "
                "flags from Wikimedia Commons (public domain, Oman's under the Open Government Licence - Oman 1.0)"
            ),
            "geo_difficulty": (
                f"English Wikipedia pageviews {geography.pageview_window()}, "
                "area for maps, distance to the nearest lookalike for flags"
            ),
        }
        db.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
    validate(db)
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    db.execute("VACUUM")
    db.close()
    temporary.replace(OUTPUT)

    with sqlite3.connect(OUTPUT) as check:
        difficulties = Counter(dict(check.execute("SELECT difficulty, COUNT(*) FROM vocab_items GROUP BY difficulty")))
    size = OUTPUT.stat().st_size / 1_000_000
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({size:.1f} MB)")
    print(f"  {math_count} math questions")
    print("  vocabulary: " + ", ".join(f"{k} {v}" for k, v in bank.counts.items()) + f", definitions {sense_count}")
    print(f"  items per difficulty: {dict(sorted(difficulties.items()))}")
    print("  level cuts (share who know): " + ", ".join(f"{difficulty.share_of_ease(c):.1%}" for c in bank.cuts))
    print("  geography: " + ", ".join(f"{kind} {count}" for kind, count in atlas.counts.items()))


if __name__ == "__main__":
    main()
