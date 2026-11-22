"""Builds Knowledge/Resources/content.sqlite, the question bank shipped in the app.

Usage (from the repository root):

    python3 -m venv tools/content/.venv
    tools/content/.venv/bin/pip install -r tools/content/requirements.txt
    curl -L -o tools/content/.cache/kaikki-english.jsonl \\
        https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl
    tools/content/.venv/bin/python -I tools/content/google_books.py   # streams ~18 GB once
    tools/content/.venv/bin/python tools/content/build_content.py

The output is deterministic for a given Wiktionary extract, Google Books reduction
and wordfreq version.

Schema (version `SCHEMA_VERSION`, stored in PRAGMA user_version; the app checks it
against `ContentStore.schemaVersion`):

    math_questions  one row per arithmetic problem. IDs are contiguous for each
                    (difficulty, operation) pair.
    vocab_words     one row per word; id == frequency rank, so IDs are contiguous
                    per difficulty. `related` lists synonyms and hypernyms
                    (space separated) used to reject unfair distractors.
    vocab_senses    the common definitions of each word. IDs are contiguous per
                    (pos, difficulty) so the app can sample distractors by ID range.
    meta            build information.
"""

from __future__ import annotations

import random
import sqlite3
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import mental_math
import vocabulary

SCHEMA_VERSION = 1
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
    difficulty INTEGER NOT NULL,
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


def write_vocabulary(db: sqlite3.Connection, rng: random.Random) -> tuple[int, int]:
    words = vocabulary.build(WIKTIONARY, BLOCKLIST, GOOGLE_BOOKS)
    senses = []
    for word in words:
        db.execute(
            "INSERT INTO vocab_words VALUES (?, ?, ?, ?, ?)",
            (word.rank, word.word, word.rank, word.difficulty, " ".join(word.related)),
        )
        for order, sense in enumerate(word.senses):
            senses.append((sense.pos, word.difficulty, rng.random(), word.rank, order, sense))
    senses.sort(key=lambda row: row[:3])
    for sense_id, (pos, difficulty, _, word_id, order, sense) in enumerate(senses, start=1):
        db.execute(
            "INSERT INTO vocab_senses VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sense_id, word_id, order, pos, difficulty, sense.gloss, sense.example, int(sense.quizzable)),
        )
    return len(words), len(senses)


def validate(db: sqlite3.Connection) -> None:
    def contiguous(table: str, group: str) -> None:
        for row in db.execute(f"SELECT {group}, MIN(id), MAX(id), COUNT(*) FROM {table} GROUP BY {group}"):
            *_, first, last, count = row
            assert last - first + 1 == count, f"{table} IDs not contiguous for {row}"

    contiguous("math_questions", "difficulty, operation")
    contiguous("vocab_words", "difficulty")
    contiguous("vocab_senses", "pos, difficulty")

    math_count = db.execute("SELECT COUNT(*) FROM math_questions").fetchone()[0]
    unique = db.execute("SELECT COUNT(*) FROM (SELECT DISTINCT operation, lhs, rhs FROM math_questions)").fetchone()[0]
    assert math_count >= 10_000 and unique == math_count, (math_count, unique)
    evaluate = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b, "/": lambda a, b: a / b}
    for op, a, b, answer, d1, d2, d3 in db.execute(
        "SELECT operation, lhs, rhs, answer, distractor1, distractor2, distractor3 FROM math_questions"
    ):
        assert evaluate[op](a, b) == answer, (op, a, b, answer)
        assert len({answer, d1, d2, d3}) == 4 and min(d1, d2, d3) >= 0, (op, a, b, answer, d1, d2, d3)

    word_count = db.execute("SELECT COUNT(*) FROM vocab_words").fetchone()[0]
    assert word_count == vocabulary.WORD_COUNT, word_count
    orphans = db.execute(
        "SELECT COUNT(*) FROM vocab_words w WHERE NOT EXISTS (SELECT 1 FROM vocab_senses s WHERE s.word_id = w.id)"
    ).fetchone()[0]
    assert orphans == 0, orphans


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
        word_count, sense_count = write_vocabulary(db, rng)
        meta = {
            "schema_version": str(SCHEMA_VERSION),
            "math_questions": str(math_count),
            "vocab_words": str(word_count),
            "vocab_senses": str(sense_count),
            "wordfreq_version": version("wordfreq"),
            "definitions_source": "English Wiktionary via kaikki.org (CC BY-SA 4.0)",
            "frequency_source": (
                "Google Books Ngram v3 English Fiction and English (CC BY 3.0), blended with wordfreq (CC BY-SA 4.0)"
            ),
            "google_books_years": "1920-2019, or 2000-2019 when higher",
            "frequency_weights": ", ".join(f"{k} {v}" for k, v in vocabulary.SOURCE_WEIGHTS.items()),
        }
        db.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
    validate(db)
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    db.execute("VACUUM")
    db.close()
    temporary.replace(OUTPUT)

    with sqlite3.connect(OUTPUT) as check:
        difficulties = Counter(dict(check.execute("SELECT difficulty, COUNT(*) FROM vocab_words GROUP BY difficulty")))
        quizzable_words = check.execute(
            "SELECT COUNT(DISTINCT word_id) FROM vocab_senses WHERE quizzable = 1"
        ).fetchone()[0]
    size = OUTPUT.stat().st_size / 1_000_000
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({size:.1f} MB)")
    print(f"  {math_count} math questions")
    print(f"  {word_count} words ({quizzable_words} with a testable definition), {sense_count} definitions")
    print(f"  words per difficulty: {dict(sorted(difficulties.items()))}")


if __name__ == "__main__":
    main()
