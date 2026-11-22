"""Reduces Google Books Ngram 1-grams to per-word book shares.

Source: Google Books Ngram Viewer, version 3 (20200217), https://books.google.com/ngrams.
Licensed under Creative Commons Attribution 3.0. Two corpora are used: `eng` (all English
books) and `eng-fiction`.

For each word this records the share of a year's books that use it, averaged so that
every year counts equally, over two windows: the last century of the corpus
(`CENTURY`) and the last twenty years (`RECENT`). Counting books rather than
occurrences keeps a term that one technical book repeats hundreds of times from
looking common. Lowercase and Titlecase spellings are kept apart ("bill" versus
"Bill"); `vocabulary.py` decides how to combine them.

Usage (from the repository root; streams about 18 GB, nothing large is stored):

    tools/content/.venv/bin/python -I tools/content/google_books.py

Output: `tools/content/.cache/google-books/<corpus>.tsv` with the columns
`word, lower_century, title_century, lower_recent, title_recent`. Each shard's result
is cached under `.cache/google-books/<corpus>/`, so an interrupted run resumes.
"""

from __future__ import annotations

import gzip
import io
import re
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from wordfreq import top_n_list

BASE_URL = "http://storage.googleapis.com/books/ngrams/books/20200217"
CORPORA = {"eng": 24, "eng-fiction": 1}  # corpus -> number of 1-gram shards
CENTURY = range(1920, 2020)
RECENT = range(2000, 2020)
CACHE = Path(__file__).resolve().parent / ".cache" / "google-books"
WORKERS = 6
ATTEMPTS = 4

LOWER_RE = re.compile(r"[a-z]+")
TITLE_RE = re.compile(r"[A-Z][a-z]+")

_vocabulary: frozenset[str] = frozenset()


def output_path(corpus: str) -> Path:
    return CACHE / f"{corpus}.tsv"


def shard_name(index: int, count: int) -> str:
    return f"1-{index:05d}-of-{count:05d}"


def open_url(url: str) -> io.BufferedIOBase:
    request = urllib.request.Request(url, headers={"User-Agent": "knowledge-content-builder"})
    return urllib.request.urlopen(request, timeout=120)


def total_volumes(corpus: str) -> dict[int, int]:
    """Books per year, from the corpus's `totalcounts-1` file (year,matches,pages,volumes)."""
    with open_url(f"{BASE_URL}/{corpus}/totalcounts-1") as response:
        text = response.read().decode()
    totals = {}
    for entry in text.split():
        year, _matches, _pages, volumes = entry.split(",")
        totals[int(year)] = int(volumes)
    return totals


def _init_worker(vocabulary: frozenset[str]) -> None:
    global _vocabulary
    _vocabulary = vocabulary


def reduce_shard(corpus: str, index: int, count: int, totals: dict[int, int]) -> str:
    """Streams one shard and writes `word, form, century_share, recent_share` rows."""
    name = shard_name(index, count)
    target = CACHE / corpus / f"{name}.tsv"
    if target.exists():
        return f"{corpus}/{name}: cached"
    target.parent.mkdir(parents=True, exist_ok=True)
    century_years = set(CENTURY)
    recent_years = set(RECENT)

    for attempt in range(1, ATTEMPTS + 1):
        rows = []
        try:
            with open_url(f"{BASE_URL}/{corpus}/{name}.gz") as response:
                stream = io.TextIOWrapper(gzip.GzipFile(fileobj=response), encoding="utf-8", errors="replace")
                for line in stream:
                    token, _, rest = line.partition("\t")
                    if LOWER_RE.fullmatch(token):
                        word, form = token, "lower"
                    elif TITLE_RE.fullmatch(token):
                        word, form = token.lower(), "title"
                    else:
                        continue  # POS-tagged, numbers, punctuation, all caps
                    if word not in _vocabulary:
                        continue
                    century = recent = 0.0
                    for entry in rest.split("\t"):
                        year_text, _, counts = entry.partition(",")
                        year = int(year_text)
                        if year not in century_years:
                            continue
                        share = int(counts.rpartition(",")[2]) / totals[year]
                        century += share
                        if year in recent_years:
                            recent += share
                    if century > 0:
                        rows.append((word, form, century / len(CENTURY), recent / len(RECENT)))
            break
        except (OSError, EOFError, ValueError) as error:
            if attempt == ATTEMPTS:
                raise
            print(f"{corpus}/{name}: attempt {attempt} failed ({error}); retrying", flush=True)
            time.sleep(10 * attempt)

    rows.sort()
    temporary = target.with_suffix(".partial")
    with temporary.open("w") as handle:
        for word, form, century, recent in rows:
            handle.write(f"{word}\t{form}\t{century:.6e}\t{recent:.6e}\n")
    temporary.replace(target)
    return f"{corpus}/{name}: {len(rows)} rows"


def merge(corpus: str) -> int:
    shares: dict[str, list[float]] = {}
    for path in sorted((CACHE / corpus).glob("1-*.tsv")):
        for line in path.read_text().splitlines():
            word, form, century, recent = line.split("\t")
            row = shares.setdefault(word, [0.0, 0.0, 0.0, 0.0])
            offset = 0 if form == "lower" else 1
            row[offset] += float(century)
            row[offset + 2] += float(recent)
    with output_path(corpus).open("w") as handle:
        handle.write("# word\tlower_century\ttitle_century\tlower_recent\ttitle_recent\n")
        for word in sorted(shares):
            handle.write(word + "".join(f"\t{value:.6e}" for value in shares[word]) + "\n")
    return len(shares)


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    vocabulary = frozenset(w for w in top_n_list("en", 1_000_000) if LOWER_RE.fullmatch(w))
    totals = {corpus: total_volumes(corpus) for corpus in CORPORA}
    jobs = [(corpus, index, count) for corpus, count in CORPORA.items() for index in range(count)]
    # The single, largest fiction shard goes first so it is not the last one running.
    jobs.sort(key=lambda job: (job[2] != 1, job))
    with ProcessPoolExecutor(WORKERS, initializer=_init_worker, initargs=(vocabulary,)) as pool:
        futures = [pool.submit(reduce_shard, corpus, index, count, totals[corpus]) for corpus, index, count in jobs]
        failures = 0
        for future in as_completed(futures):
            try:
                print(future.result(), flush=True)
            except Exception as error:  # noqa: BLE001 - report every failed shard, then stop
                failures += 1
                print(f"shard failed: {error}", flush=True)
    if failures:
        sys.exit(f"{failures} shard(s) failed; run again to retry them.")
    for corpus in CORPORA:
        print(f"Wrote {output_path(corpus)} ({merge(corpus)} words)")


if __name__ == "__main__":
    main()
