# Knowledge

A native iOS quiz app for staying sharp on general knowledge. Pick the topics you
care about and the app serves a continuous stream of questions that adapt to you:
it balances topics evenly, brings back questions you missed, and moves toward the
difficulty where you are right about half to two thirds of the time.

Everything ships inside the app. There is no account, no backend and no network
access; progress is stored on the device.

## Topics

Available now:

| Topic | Content |
| --- | --- |
| Mental Math | 11,456 unique addition, subtraction, multiplication and division problems across five difficulty levels |
| Vocabulary | 45,986 questions, one per meaning, on 35,848 words drawn from the 40,000 most used in books, fiction and current English, in American spelling. The 3,000 most common are asked only on their less-known meanings (table: to postpone; bill: a proposed law), and words that only restate a more common one ("unmusical: not musical") are left out. Difficulty comes from how many adults know each meaning |

Sixteen more topics are planned; see [TODO.md](TODO.md).

## Features

- **Onboarding without friction.** No sign-in or permissions. Choose topics and go
  straight into questions.
- **Multiple choice with one right answer.** Four options per question, large
  touch targets, and immediate feedback. Vocabulary answers list every common
  meaning of the word, with an example sentence where one exists.
- **Even topic rotation.** With three topics on, 30 questions split about 10/10/10,
  and the same topic never appears more than twice in a row.
- **Spaced repetition.** Missed questions return 5–9 questions later, then at
  growing intervals (15 answers and 10 minutes, then 1, 3, 7, 21 and 60 days)
  as you get them right.
- **Adaptive difficulty and proficiency.** Every question has a difficulty from 1
  to 5. After 10 answers in a topic, the app estimates your ability and shows a
  1–10 proficiency score on the Profile screen. A 10 means at least 90% right on
  level 5 (and about 97% on level 4, 99% below). Difficulty then leans gently
  toward your level, and every level keeps at least 10% of questions: for a strong
  user the split is 10/15/20/25/30% from level 1 to level 5.
- **Reset progress.** A button at the bottom of Profile, after a confirmation,
  deletes every answer, review schedule and proficiency score. Topic choices are kept.

## Requirements

- Xcode 27 or later (iOS 27 SDK, Swift 6)
- iOS 26.0 or later on device or simulator

No third-party Swift packages are used. SQLite is accessed through the system
library.

## Getting started

Open `Knowledge.xcodeproj` and run the **Knowledge** scheme, or from the command
line:

```sh
# Build
xcodebuild -project Knowledge.xcodeproj -scheme Knowledge \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build

# Unit tests (Swift Testing) and UI tests (XCTest)
xcodebuild -project Knowledge.xcodeproj -scheme Knowledge \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```

To run the app in a simulator from the command line:

```sh
xcodebuild -project Knowledge.xcodeproj -scheme Knowledge \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -derivedDataPath build/DerivedData build
xcrun simctl bootstatus "iPhone 17 Pro" -b   # boots the simulator if needed and waits until it is ready
open -a DeviceHub                             # shows the simulator (Xcode 27's replacement for Simulator.app)
xcrun simctl install "iPhone 17 Pro" build/DerivedData/Build/Products/Debug-iphonesimulator/Knowledge.app
xcrun simctl launch "iPhone 17 Pro" com.jordanhoeber.knowledge
```

Any installed iPhone simulator works; `xcrun simctl list devices available` lists
them. If two share a name (one per iOS version), use the UDID from that list instead.

Useful launch arguments (set them in the scheme, or add them after the bundle ID in
`simctl launch`; `--terminate-running-process` restarts the app if it is already
open, otherwise the arguments are ignored):

```sh
xcrun simctl launch --terminate-running-process "iPhone 17 Pro" com.jordanhoeber.knowledge -resetState -seed 42
```

| Argument | Effect |
| --- | --- |
| `-resetState` | Erase progress and preferences at launch |
| `-topics mental_math,vocabulary` | Skip onboarding with these topics enabled |
| `-seed 42` | Deterministic question order |
| `-disableAnimations` | Turn off animations (used by UI tests) |

## Project layout

```
Knowledge/                 App target (Xcode synchronized folder: new files are picked up automatically)
  App/                     Entry point, launch configuration, app-wide state
  Models/                  Topic and Question types
  Data/                    SQLite wrapper, bundled content store, progress and settings stores
  Engine/                  Question selection: topic scheduler, spaced repetition,
                           proficiency model, question providers, quiz engine
  DesignSystem/            Color roles, spacing, shared components
  Features/                Onboarding, Quiz, Topics, Profile screens
  Resources/content.sqlite Generated question bank (do not edit by hand)
KnowledgeTests/            Unit tests (Swift Testing)
KnowledgeUITests/          End-to-end UI tests (XCTest), which also capture screenshots
tools/content/             Python pipeline that generates content.sqlite
tools/make_app_icon.py     Renders the app icon
```

## How questions are chosen

1. **Topic.** A shuffled bag holds two copies of each enabled topic; topics are
   drawn without replacement, skipping any draw that would make three in a row.
2. **Difficulty.** Until a topic has 10 answers, every level is equally likely.
   After that, ability is estimated with a one-parameter logistic (Rasch) model
   over the last 120 answers (an answer 60 back counts half as much as the newest),
   giving a posterior over ability. Each level's weight is `6 − |level − target|`,
   where the target is the level you answer about half right (the posterior mean,
   clamped to 1–5):

   | Target | L1 | L2 | L3 | L4 | L5 |
   | --- | --- | --- | --- | --- | --- |
   | 1 | 30% | 25% | 20% | 15% | 10% |
   | 3 | 17% | 21% | 25% | 21% | 17% |
   | 5 | 10% | 15% | 20% | 25% | 30% |

3. **Review or new.** If an item at that level is due for review, it is asked with
   a probability that depends on how recently it was missed (90% for just-missed
   items, 35% for long-interval reviews). Otherwise a new item at that level is
   chosen. Drawing the level first keeps the mix of levels on target: a run of
   missed hard questions cannot crowd out the easy ones.
4. **Common meanings first.** Within a vocabulary level, new questions lean toward
   the meanings a reader meets most often (school and work words count as twice as
   common): half come from the most frequent quarter of the level, and the rarest
   quarter still supplies about one in eight.

## How proficiency is scored

The 1–10 score on Profile comes from the same posterior as difficulty, but from its
40th percentile rather than its mean, so a high score needs evidence: a perfect
start shows 8 after 10 answers, 9 after 20 and 10 after about 30. Each score has an
ability threshold; a 10 needs 90% predicted accuracy on level 5, and each point
below is the same accuracy at a level 0.6 easier. Predicted accuracy at each
threshold:

| Score | L1 | L2 | L3 | L4 | L5 |
| --- | --- | --- | --- | --- | --- |
| 10 | 100% | 100% | 99% | 97% | 90% |
| 9 | 100% | 100% | 98% | 94% | 80% |
| 8 | 100% | 99% | 97% | 87% | 63% |
| 7 | 99% | 98% | 92% | 75% | 42% |
| 6 | 99% | 95% | 84% | 56% | 24% |
| 5 | 97% | 90% | 69% | 35% | 12% |
| 4 | 94% | 80% | 49% | 19% | 6% |
| 3 | 87% | 63% | 29% | 9% | 2% |
| 2 | 75% | 42% | 15% | 4% | 1% |

How steeply accuracy falls from level to level comes from the model's slope (1.4),
which is a design choice, not fitted to real answers.

See `Knowledge/Engine/` for the implementation and `KnowledgeTests/` for the
behavior each part guarantees.

## Content pipeline

`Knowledge/Resources/content.sqlite` is generated, deterministically, by
`tools/content/build_content.py`:

```sh
python3 -m venv tools/content/.venv
tools/content/.venv/bin/pip install -r tools/content/requirements.txt
mkdir -p tools/content/.cache
curl -L -o tools/content/.cache/kaikki-english.jsonl \
  https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl   # about 3.4 GB
tools/content/.venv/bin/python -I tools/content/google_books.py              # streams about 18 GB once
tools/content/.venv/bin/python tools/content/build_content.py
```

- `mental_math.py` generates the arithmetic bank. Distractors model real mistakes:
  off by one, a dropped carry, subtracting the smaller digit from the larger, a
  neighboring times-table fact, or the same last digit.
- `google_books.py` streams the Google Books Ngram 1-grams (English Fiction and all
  English) and keeps, for each word, the share of each year's books that use it,
  averaged over 1920–2019 and over 2000–2019. Only the small result is cached in
  `tools/content/.cache/google-books/`.
- `vocabulary.py` selects words and definitions. Its module docstring explains the
  ranking (each word's rank in fiction, in all books and in wordfreq, combined as a
  weighted geometric mean with fiction weighted least, inflections folded into base
  words, and school and work words boosted), the sense selection (Wiktionary
  translation counts as a proxy for how common a meaning is), which meanings become
  questions, and the filters (obsolete, regional, vulgar and explicit senses are
  removed, and so are derogatory senses that insult a group of people; plain
  insults such as "idiot" or "philistine" stay; `blocklist.txt` keeps the word list
  family friendly). Long definitions are cut at a clause boundary to fit a quiz
  option rather than dropped. The 3,000 most
  common words of the 40,000 considered are never asked on their main meaning,
  only on up to three later meanings that fewer than 98% of adults are estimated
  to know.
- `spelling.py` puts the bank in American spelling, using VarCon's list of British
  and American spellings. British headwords are merged into the American word
  (plough into plow, jewellery into jewelry, with their frequencies combined), and
  definitions and examples are respelled ("an achromatic colour" becomes "color").
  Spellings that are also American (axe, dialogue) stay. The VarCon file is
  downloaded into `tools/content/.cache/spelling/` the first time the build runs.
- `derivatives.py` finds meanings that only restate a more common word
  ("believably: in a believable way", "rootless: having no roots"). They are not
  asked, and a word with nothing else is left out.
- `difficulty.py` gives every meaning a difficulty from how many adults know it.
  Word prevalence (the share of people who know a word) is blended with a
  prediction from frequency and age of acquisition; a word's later meanings are
  harder by the years between learning them and its first meaning, from
  test-based age-of-acquisition norms for 44,000 meanings. Questions are split into
  five equal levels; in the current build, level 1 meanings are known by at least
  98.3% of adults, level 2 by 96.3%, level 3 by 91.1%, level 4 by 74.3%, and level
  5 by fewer.
- `norms.py` downloads the norms and word lists into `tools/content/.cache/norms/`
  (about 15 MB) the first time the build runs.

## Data sources and licenses

- Definitions and examples: [English Wiktionary](https://en.wiktionary.org/),
  through the [kaikki.org](https://kaikki.org/) extract. Wiktionary text is
  available under CC BY-SA 4.0 (and GFDL).
- Written usage: [Google Books Ngram Viewer](https://books.google.com/ngrams) data
  (version 3, 2020), licensed under
  [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).
- Word frequencies: [wordfreq](https://github.com/rspeer/wordfreq) by Robyn Speer;
  its data is CC BY-SA 4.0.
- Word knowledge: Brysbaert, Mandera, McCormick & Keuleers (2019),
  [Word prevalence norms for 62,000 English lemmas](https://doi.org/10.3758/s13428-018-1077-9),
  Behavior Research Methods (supplementary data).
- Meaning age of acquisition: Brysbaert & Biemiller (2017),
  [Test-based age-of-acquisition norms for 44 thousand English word meanings](https://doi.org/10.3758/s13428-016-0811-4),
  Behavior Research Methods, built on Dale & O'Rourke's *Living Word Vocabulary*.
  The authors' site has been taken down; the build downloads the file from the
  Internet Archive.
- School and work words: the [New Academic Word List and Business Service List](https://www.newgeneralservicelist.com)
  by Browne, Culligan & Phillips, CC BY-SA 4.0.
- Spelling variants: [VarCon](http://wordlist.aspell.net/varcon/) by Kevin Atkinson
  and Benjamin Titze (part of SCOWL), under a permissive license that asks for its
  copyright notice to be kept (see the README downloaded next to it).

The bank stores only difficulty levels derived from the two sets of norms, not the
norms themselves. Confirm the terms for both before a public release (see TODO.md).

Because the vocabulary data is derived from CC BY-SA sources, the generated
`content.sqlite` must be shared under CC BY-SA 4.0 with attribution. An in-app
attribution screen is on the TODO list before any public release.
