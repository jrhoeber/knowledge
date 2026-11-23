"""Published word-knowledge norms and word lists used to judge vocabulary difficulty.

Sources (downloaded once into `.cache/norms/` by `ensure_downloaded`)
--------------------------------------------------------------------
* Word prevalence: Brysbaert, Mandera, McCormick & Keuleers (2019), "Word prevalence
  norms for 62,000 English lemmas", Behavior Research Methods 51, 467-479,
  https://doi.org/10.3758/s13428-018-1077-9 (supplementary file 2). For each word, the
  share of roughly 400 native speakers per word who said they knew it in an online
  vocabulary test with nonword checks (`Pknown`), and its probit (`Prevalence`).
* Meaning age of acquisition: Brysbaert & Biemiller (2017), "Test-based
  age-of-acquisition norms for 44 thousand English word meanings", Behavior Research
  Methods 49, 1520-1523, https://doi.org/10.3758/s13428-016-0811-4. Built on Dale &
  O'Rourke's Living Word Vocabulary, which tested school children on each meaning
  of a word with three-choice questions. One row per meaning: the word, a short
  description ("bill: proposed law") and the age it is known (`AoAtestbased`). The
  authors' site (crr.ugent.be) has been taken down; the file comes from the Internet
  Archive's copy.
* School and work vocabulary: the New Academic Word List 1.2 (NAWL, about 960 words
  frequent in academic text) and the Business Service List 1.2 (BSL, about 1,700
  words frequent in business text), by Browne, Culligan & Phillips,
  https://www.newgeneralservicelist.com, CC BY-SA 4.0. Both lists leave out the
  2,800 core words of the New General Service List.
"""

from __future__ import annotations

import re
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

CACHE = Path(__file__).resolve().parent / ".cache" / "norms"
SOURCES = {
    "prevalence.xlsx": "https://static-content.springer.com/esm/art%3A10.3758%2Fs13428-018-1077-9"
    "/MediaObjects/13428_2018_1077_MOESM2_ESM.xlsx",
    "meaning-aoa.xlsx": "https://web.archive.org/web/20171010003536id_/http://crr.ugent.be:80/papers/"
    "Master%20file%20with%20all%20values%20for%20test%20based%20AoA%20measures.xlsx",
    "nawl.csv": "https://www.newgeneralservicelist.com/s/NAWL_12_lemmatized_for_teaching.csv",
    "bsl.csv": "https://www.newgeneralservicelist.com/s/BSL_120_lemmatized_for_teaching.csv",
}
USER_AGENT = "Mozilla/5.0 (compatible; content-build)"
_SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def path(name: str) -> Path:
    return CACHE / name


def ensure_downloaded() -> None:
    """Downloads any missing source file (about 15 MB in all)."""
    download(SOURCES, CACHE)


def download(sources: dict[str, str], cache: Path) -> None:
    """Downloads each `name: url` in `sources` into `cache` unless already there."""
    cache.mkdir(parents=True, exist_ok=True)
    for name, url in sources.items():
        target = cache / name
        if target.exists():
            continue
        print(f"Downloading {name}")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        if name.endswith(".xlsx") and not data.startswith(b"PK"):
            raise SystemExit(f"{url} did not return a spreadsheet")
        partial = target.with_suffix(".partial")
        partial.write_bytes(data)
        partial.replace(target)


def xlsx_rows(file: Path) -> list[dict[str, str]]:
    """Rows of the first sheet as {header: value}. Minimal reader for plain data
    sheets (shared and inline strings, numbers), so the build needs no extra package."""
    with zipfile.ZipFile(file) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for item in ElementTree.fromstring(archive.read("xl/sharedStrings.xml")).iter(f"{_SHEET_NS}si"):
                shared.append("".join(t.text or "" for t in item.iter(f"{_SHEET_NS}t")))
        sheet = sorted(n for n in archive.namelist() if n.startswith("xl/worksheets/sheet"))[0]
        table: list[dict[str, str]] = []
        for row in ElementTree.fromstring(archive.read(sheet)).iter(f"{_SHEET_NS}row"):
            cells: dict[str, str] = {}
            for cell in row.iter(f"{_SHEET_NS}c"):
                column = re.match(r"[A-Z]+", cell.get("r", "")).group()
                kind = cell.get("t")
                if kind == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(f"{_SHEET_NS}t"))
                else:
                    node = cell.find(f"{_SHEET_NS}v")
                    value = "" if node is None or node.text is None else node.text
                    if kind == "s":
                        value = shared[int(value)]
                cells[column] = value
            table.append(cells)
    if not table:
        return []
    header = table[0]
    return [{header[c]: v for c, v in row.items() if c in header} for row in table[1:]]


def number(text: str) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if value == value else None  # NaN


def load_prevalence() -> dict[str, float]:
    """Word -> share of people who know it (0-1)."""
    known = {}
    for row in xlsx_rows(path("prevalence.xlsx")):
        word, share = row.get("Word", "").strip().lower(), number(row.get("Pknown"))
        if word and share is not None:
            known[word] = share
    return known


@dataclass(frozen=True)
class MeaningAge:
    description: str
    age: float


def load_meaning_ages() -> dict[str, list[MeaningAge]]:
    """Word -> its tested meanings with the age (in years) at which each is known."""
    meanings: dict[str, list[MeaningAge]] = {}
    for row in xlsx_rows(path("meaning-aoa.xlsx")):
        word = row.get("WORD", "").strip().lower()
        age = number(row.get("AoAtestbased"))
        description = re.sub(r"\s+", " ", row.get("MEANING", "")).strip()
        if word and description and age is not None:
            meanings.setdefault(word, []).append(MeaningAge(description, age))
    return meanings


def load_word_list(name: str) -> set[str]:
    """Headwords (first column) of a NAWL or BSL file."""
    words = set()
    for line in path(name).read_text(encoding="latin-1").splitlines():
        head = line.split(",", 1)[0].strip().lower()
        if head:
            words.add(head)
    return words


def load_school_and_work_words() -> set[str]:
    return load_word_list("nawl.csv") | load_word_list("bsl.csv")
