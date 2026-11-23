# CLAUDE.md

Native iOS general-knowledge quiz app (SwiftUI, Swift 6, iOS 26.0+, no backend, no
third-party packages). The original product brief is `init.md`; README.md covers
features and the question algorithm; TODO.md lists the remaining 15 topics.

## Commands

```sh
# Build / test (pick any installed iOS 26+ simulator)
xcodebuild -project Knowledge.xcodeproj -scheme Knowledge -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
xcodebuild -project Knowledge.xcodeproj -scheme Knowledge -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
xcodebuild ... test -only-testing:KnowledgeTests      # unit tests only (~2 s)
xcodebuild ... test -only-testing:KnowledgeUITests    # UI flow (~2 min)

# Run in a simulator, skipping onboarding, deterministic questions
xcrun simctl install booted <DerivedData>/Build/Products/Debug-iphonesimulator/Knowledge.app
xcrun simctl launch booted com.jordanhoeber.knowledge -resetState -topics mental_math,vocabulary -seed 3
xcrun simctl io booted screenshot shot.png

# UI test screenshots (attached with lifetime .keepAlways)
xcodebuild ... test -only-testing:KnowledgeUITests -resultBundlePath build/ui.xcresult
xcrun xcresulttool export attachments --path build/ui.xcresult --output-path build/shots

# Regenerate the question bank (needs the 3.4 GB Wiktionary extract; see README)
tools/content/.venv/bin/python -I tools/content/google_books.py   # once: Google Books shares (~18 GB streamed)
tools/content/.venv/bin/python tools/content/build_content.py       # downloads the norms (norms.py) on first run
tools/content/.venv/bin/python tools/content/build_content.py --reuse   # reuse the cached Wiktionary parse (~30 s)
tools/content/.venv/bin/python tools/content/geography.py           # geography levels and sizes, for tuning
tools/content/.venv/bin/python tools/content/vocabulary.py --reuse   # ranking and difficulty diagnostics, cached parse
```

## Architecture

- `Engine/QuizEngine` runs the loop: `TopicScheduler` (shuffled bag, max run 2) →
  difficulty drawn from `ProficiencyModel` weights (uniform until 10 answers, then
  a gentle lean toward the posterior-mean ability; every level keeps at least 10%;
  the 1–10 proficiency shown on Profile uses the cautious 40th percentile) → a due
  review at that difficulty from `ProgressStore` (`SpacedRepetition` boxes), else a
  new item at that difficulty. Drawing difficulty before reviews is deliberate (see
  `strugglingAfterAStrongStartBringsBackEasyLevels`). It is `@Observable` and owned
  by `App/AppModel`.
- `QuestionProvider` turns a content item ID into a `Question`. One provider per
  topic: `MentalMathProvider`, `VocabularyProvider` (a vocabulary item is one
  meaning of a word, from `vocab_items`; builds distractors at runtime, rejecting
  synonyms and definitions sharing word stems via `OverlapFilter`),
  `GeographyProvider` (maps, flags and capitals of countries and US states, from
  `geo_items`; wrong answers come from the same layer and get closer with the
  level: other continents, same continent, then neighbors, lookalike flags or
  decoy cities).
  `randomItem(in:)` picks a new item within a level: uniform by default; vocabulary
  leans toward low IDs (the meanings met most often) through `CommonFirstSampler`.
- Vocabulary difficulty is how widely a meaning is known, not word frequency:
  `tools/content/difficulty.py` (word prevalence and meaning age-of-acquisition
  norms from `norms.py`), split into five equal levels. `derivatives.py` drops
  meanings that only restate a more common word. `spelling.py` (VarCon) puts the
  bank in American spelling: British headwords merge into the American word and
  definitions, examples and related words are respelled.
- Geography content comes from `tools/content/geography.py`: hand-curated
  `countries.csv` / `states.csv` (names, capitals, notes, decoys, Wikipedia
  articles, Commons flag files) plus Natural Earth shapes (US point of view),
  Commons flags and Wikipedia pageviews cached in `tools/content/.cache/geography/`.
  The app decodes shapes into `Models/GeoAtlas` (unit-sphere rings, loaded on the
  first map question) and draws them in `Features/Quiz/GeoMapView` with an
  orthographic `MapCamera` that blends from the close-up to the zoomed-out view
  (the globe for countries, the lower 48 for states).
- `Data/ContentStore` opens the bundled read-only `Resources/content.sqlite`;
  `Data/ProgressStore` is the writable SQLite file in Application Support;
  `Data/SettingsStore` wraps `UserDefaults`. `Data/SQLiteDatabase` is a thin
  wrapper over the system SQLite C API.
- `App/AppLaunch` reads launch arguments (`-resetState`, `-topics`, `-seed`,
  `-disableAnimations`) used by UI tests and screenshots.

## Invariants

- Content item IDs are contiguous per (difficulty, operation) for math, per
  difficulty for vocabulary items (`vocab_items`, ordered within a level by how
  often the meaning is met), per (pos, difficulty) for vocabulary senses, and per
  (difficulty, category) for geography items (map, flag, capital).
  Providers sample by ID range and throw `nonContiguousRange` if this breaks.
  `build_content.py` validates it.
- `SCHEMA_VERSION` in `tools/content/build_content.py` must equal
  `ContentStore.schemaVersion`; bump both on any content schema change.
- `GlossTokenizer.stem` in Swift and `stem()` in `tools/content/vocabulary.py`
  are ports of each other; change them together.
- Unit tests assert the brief's numbers: at least 10,000 unique math questions,
  4 unique options with one correct answer. Vocabulary is drawn from the 40,000
  most common words (`WORD_POOL`; the brief originally said 75,000), minus
  transparent derivatives; the 3,000 most common (`REMOVED_COMMON_WORDS`) are asked
  only on later meanings, never their main one (listed first, `sense_order` 0).
  About 35,800 words; tests require at least 30,000 and equal-sized levels.
- The bank is in American spelling (headwords, definitions, examples);
  `vocabulary.rank` fails the build if a non-American headword slips in. Derogatory
  meanings are allowed only if they don't insult a group (`GROUP_INSULT_RE`); review
  newly added derogatory words, and extend `blocklist.txt`, when the filters change.
- `vocabulary.py --reuse` caches the parse under `PREPARED_VERSION`; bump it when
  `prepare` changes.
- Geography: 196 countries (UN members plus Vatican City, Palestine and Taiwan)
  and 50 states, each kind split into five equal levels. Borders follow US policy;
  `geography.POLICY_CHECKS` asserts disputed places land in the right country, so
  extend it rather than editing shapes by hand. Capital questions skip giveaways
  (the capital contains the name or the reverse) and places without an
  uncontested capital. Flags must be public domain (Oman's OGL-om license is the
  one allowed exception, recorded in `geo_flags.license`).
- `encode_shape` in `geography.py` and `GeoAtlas.decodeShape` are a format pair;
  change them together.

## Conventions

- The project uses Xcode synchronized folders: add files under `Knowledge/`,
  `KnowledgeTests/` or `KnowledgeUITests/` and they are built automatically. Do not
  hand-edit `project.pbxproj` to add files.
- Default actor isolation is `MainActor` (`SWIFT_DEFAULT_ACTOR_ISOLATION`). Pure
  value types used from tests or `Layout` are marked `nonisolated`.
- Unit tests use Swift Testing (`import Testing`); UI tests use XCTest.
- UI tests find elements by accessibility identifier (`startButton`,
  `topicCard.<topic>`, `option-0`…`option-3`, `continueButton`, `menuButton`,
  `menu.topics`, `menu.profile`, `topicToggle.<topic>`, `proficiencyCard.<topic>`,
  `questionPrompt`, `meaningsCard`, `feedbackTitle`, `resetProgressButton`,
  `confirmResetProgress`, `mapView`, `mapZoomPicker`, `flagImage`,
  `flagComparisonCard`, `geographyNoteCard`). Keep them stable.

## Design rules (from the brief)

- Bright, warm, light-only look (`Palette`), saturated topic colors from
  `Topic.colors`, spacing and radii from `Spacing` / `Radius`. Do not hard-code
  colors in views.
- Native components first (`NavigationStack`, `List`, `Toggle`, `Menu`,
  toolbar), styled with Material principles: clear color roles, 4/8 pt spacing,
  touch targets of at least 48 pt, pressed states, restrained motion.
- No floating action buttons, ever. No emoji. Avoid AI-looking tells (gradients,
  sparkles, glassy decoration on custom views).
- The menu offers exactly two destinations: Topics and Profile.

## Adding a topic

1. Generate content into new tables in `content.sqlite` (extend
   `build_content.py`; keep IDs contiguous per difficulty; bump the schema version).
2. Add a `QuestionProvider` and register it in `ContentStore.makeProviders()`.
3. Extend `Question.Content` and the quiz views if the prompt is not plain text.
4. Flip the case in `Topic.isAvailable`; update `ContentTests` and TODO.md.
