"""Builds Knowledge/Resources/content.sqlite, the question bank shipped in the app.

Usage (from the repository root):

    python3 -m venv tools/content/.venv
    tools/content/.venv/bin/pip install -r tools/content/requirements.txt
    curl -L -o tools/content/.cache/kaikki-english.jsonl \\
        https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl
    tools/content/.venv/bin/python -I tools/content/google_books.py   # streams ~18 GB once
    tools/content/.venv/bin/python tools/content/build_content.py   # also downloads the norms and VarCon

The output is deterministic for a given Wiktionary extract, Google Books reduction,
wordfreq version and set of norms.

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
    meta            build information.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import difficulty
import mental_math
import vocabulary

SCHEMA_VERSION = 2
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUTPUT = ROOT / "Knowledge" / "Resources" / "content.sqlite"
WIKTIONARY = HERE / ".cache" / "kaikki-english.jsonl"
GOOGLE_BOOKS = {
    "fiction": HERE / ".cache" / "google-books" / "eng-fiction.tsv",
    "books": HERE / ".cache" / "google-books" / "eng.tsv",
}
BLOCKLIST = HERE / "blocklist.txt"
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


def write_vocabulary(db: sqlite3.Connection, rng: random.Random) -> vocabulary.Bank:
    bank = vocabulary.build(WIKTIONARY, BLOCKLIST, GOOGLE_BOOKS)
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


def validate(db: sqlite3.Connection) -> None:
    def contiguous(table: str, group: str) -> None:
        for row in db.execute(f"SELECT {group}, MIN(id), MAX(id), COUNT(*) FROM {table} GROUP BY {group}"):
            *_, first, last, count = row
            assert last - first + 1 == count, f"{table} IDs not contiguous for {row}"

    contiguous("math_questions", "difficulty, operation")
    contiguous("vocab_senses", "pos, difficulty")
    contiguous("vocab_items", "difficulty")

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


if __name__ == "__main__":
    main()
