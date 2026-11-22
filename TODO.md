# TODO

## Topics to implement

Mental Math and Vocabulary ship today. Each topic below already exists in
`Topic` (title, summary, symbol, color) and appears as "coming soon"; turning one on
means adding content, a `QuestionProvider`, and flipping `Topic.isAvailable`
(see "Adding a topic" in CLAUDE.md).

- [ ] **Geography**: name the country from its map outline or its flag. Needs
      image assets (flag and outline artwork with a compatible license) and an
      image-based prompt.
- [ ] **Spelling**: the word is spoken and the user types it. Needs text-to-speech
      (`AVSpeechSynthesizer`) and a text field with autocorrection, spell checking
      and suggestions disabled. Not multiple choice. Can reuse the Vocabulary word
      list for difficulty.
- [ ] **History**: important events and key figures.
- [ ] **Everyday Science**: "Why…?" questions (why the sea is salty, how rainbows
      form, why ice floats). The category most likely to come up with kids, and the
      one parents most often cannot answer.
- [ ] **Space, Earth and Weather**: planets, moon phases, seasons, volcanoes, how
      clouds and wind work.
- [ ] **Human Body and Health**: organs, how vaccines work, nutrition basics, how to
      read a medicine label; also kids' questions ("why does my tummy growl").
- [ ] **Animals and Nature**: habitats, food chains, which animals are mammals, how
      plants make food.
- [ ] **Money and Personal Finance**: interest, inflation, budgeting, insurance and
      risk, plus a kid-level track (saving, needs vs. wants, what a bank does).
- [ ] **Civics and Government**: branches of government, how a bill becomes law,
      rights, how elections work.
- [ ] **Estimation and Everyday Numbers**: percentages, tips, unit conversions and
      "about how many…" questions. Builds on Mental Math; answer with a slider
      rather than multiple choice.
- [ ] **Idioms, Myths and Literary References**: Achilles' heel, Pandora's box, a
      Pyrrhic victory, famous characters and fables.
- [ ] **Word Roots**: Greek and Latin prefixes and roots (bio, graph, -ology).
      Wiktionary's prefix, suffix and combining-form entries (already in the
      kaikki extract) are a good starting point.
- [ ] **How Things Work (Technology)**: how the internet, planes, electricity and
      phones work.
- [ ] **Economics in the News**: GDP, tariffs, interest rates, the stock market.
      Could be folded into Money and Personal Finance.
- [ ] **Arts and Music Basics**: famous artists and composers, instrument families.
- [ ] **Philosophy**: important figures and schools of thought.

## Follow-ups

- [ ] Attribution screen for Wiktionary and wordfreq (CC BY-SA 4.0) and Google
      Books Ngram (CC BY 3.0) before any public release; see README.
- [ ] Vocabulary content review. Known rough edges:
      - About 1,600 words only have self-referential definitions ("in a grateful
        manner"). They make easy questions; only common ones are kept.
      - Some plurals keep a niche meaning (hipsters: an undergarment).
      - Short words whose counts measure something else (foreign words, OCR
        fragments) are listed by hand in `blocklist.txt` for ranks under 20,000;
        a second pass over ranks 20,000-40,000 would catch longer ones.
      - Some fallback first senses are odd (mama, brat, yoga, heck).
      - Some first senses are not the everyday one (tracker, alum).
      - Wiktionary writes some definitions with both spellings ("colour/color",
        "tyre/tire"). Pick one dialect and normalize them in `vocabulary.py`
        (the pairs only; leave "and/or" and other slashes alone).
- [ ] Optional "Reset progress" in Profile.
- [ ] Dark mode. The brief asks for a bright look, so the app is light-only
      (`UIUserInterfaceStyle = Light`); revisit with a dark palette.
- [ ] App icon dark and tinted variants for iOS 26+ home screens.
- [ ] Install the iOS 27 simulator runtime and test on it (only iOS 26.x
      runtimes are installed; the app targets iOS 26.0).
- [ ] Consider Git LFS for `Knowledge/Resources/content.sqlite` (about 18 MB,
      regenerated with each content change).
- [ ] iPad layout pass (content is width-capped, but untested on iPad).
- [ ] VoiceOver and Dynamic Type audit at the largest accessibility sizes.
