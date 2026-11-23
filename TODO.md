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
