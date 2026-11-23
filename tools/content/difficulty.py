"""Difficulty of each word meaning, from how many people know it.

Difficulty is about whether a reader is likely to know a meaning, not how often it
is used, so it is estimated on one scale: the probit of the share of adults who know
the meaning ("ease"; 2.33 is 99%, 1.28 is 90%, 0 is 50%).

1. Word ease. `norms.load_prevalence` gives the share of people who know each of
   62,000 words. Prevalence is noisy at the top (most words are known by 98-100%), so
   it is blended with a prediction from the word's frequency rank and the age its
   earliest meaning is learned (`WORD_PREDICTION_WEIGHT`). The prediction is a
   least-squares fit over the bank's own words that have prevalence. Word ease is
   capped at 99%, the most the norms can measure. Words without
   prevalence use the prediction alone, lowered by `MISSING_WORD_PENALTY` residual
   standard deviations for single words: the norms cover nearly every word people
   know, so a word missing from them (morne, lumia) is probably less known than its
   frequency suggests. Hyphenated words are not penalized, since the norms have
   almost none.
2. Meaning ease. A word's prevalence reflects its best-known meaning. Other meanings
   are harder by the years between learning that meaning and the word's first one,
   from Brysbaert & Biemiller's test-based age-of-acquisition norms
   (`norms.load_meaning_ages`), converted to ease with the slope of word ease on age.
   Wiktionary definitions are matched to the norms' short meaning descriptions by
   shared word stems, ignoring words common to all definitions ("small", "part").
   A word's most translated meaning that matches nothing counts as its first
   meaning; any other unmatched meaning counts as learned `secondary_gap` years
   later (the average gap among the norms' later meanings).
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass

from norms import MeaningAge

# Share of the word ease taken from the frequency and age prediction rather than
# measured prevalence.
WORD_PREDICTION_WEIGHT = 0.2
# Residual standard deviations taken off the predicted ease of a single word that the
# prevalence norms do not list.
MISSING_WORD_PENALTY = 1.0
# Prevalence shares are clamped before the probit so 0% and 100% stay finite.
MIN_SHARE, MAX_SHARE = 0.01, 0.99
# A stem in at least this share of all definitions is too common to match on.
GENERIC_STEM_SHARE = 0.006
# A definition matches a meaning description if this share of the description's
# content stems appear in it.
MIN_MATCH_SHARE = 0.5
LEVELS = 5

_probit = statistics.NormalDist().inv_cdf


def ease_of_share(share: float) -> float:
    return _probit(min(max(share, MIN_SHARE), MAX_SHARE))


def share_of_ease(ease: float) -> float:
    return statistics.NormalDist().cdf(ease)


def least_squares(rows: list[list[float]], targets: list[float]) -> list[float]:
    """Ordinary least squares by the normal equations (a handful of columns)."""
    k = len(rows[0])
    matrix = [
        [sum(r[i] * r[j] for r in rows) for j in range(k)] + [sum(r[i] * t for r, t in zip(rows, targets))]
        for i in range(k)
    ]
    for column in range(k):
        pivot = max(range(column, k), key=lambda r: abs(matrix[r][column]))
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        for r in range(k):
            if r != column:
                factor = matrix[r][column] / matrix[column][column]
                matrix[r] = [a - factor * b for a, b in zip(matrix[r], matrix[column])]
    return [matrix[i][k] / matrix[i][i] for i in range(k)]


def fit_quality(rows: list[list[float]], targets: list[float], coefficients: list[float]) -> tuple[float, float]:
    """R squared and the residual standard deviation of a fit."""
    predictions = [sum(a * b for a, b in zip(r, coefficients)) for r in rows]
    mean = sum(targets) / len(targets)
    residual = sum((t - p) ** 2 for t, p in zip(targets, predictions))
    total = sum((t - mean) ** 2 for t in targets)
    return 1 - residual / total, math.sqrt(residual / len(targets))


@dataclass(frozen=True)
class MeaningEase:
    ease: float
    source: str  # "age" (matched in the norms), "first" or "later" (unmatched)
    age_gap: float


class MeaningMatcher:
    """Finds the age-of-acquisition norm that a Wiktionary definition describes.

    `glosses` is every definition being considered, used to find stems too common to
    match on; `stem`, `stop_words` and `stems_match` come from `vocabulary`."""

    def __init__(self, meaning_ages: dict[str, list[MeaningAge]], glosses: list[str], stem, stop_words, stems_match):
        self.meaning_ages = meaning_ages
        self._stem, self._stop_words, self._stems_match = stem, stop_words, stems_match
        counts = Counter(s for gloss in glosses for s in set(self.content_stems(gloss)))
        self.generic = {s for s, n in counts.items() if n >= GENERIC_STEM_SHARE * len(glosses)}

    def content_stems(self, text: str) -> list[str]:
        return [
            self._stem(t) for t in re.split(r"[^a-z]+", text.lower()) if len(t) >= 3 and t not in self._stop_words
        ]

    def first_age(self, word: str) -> float:
        return min(m.age for m in self.meaning_ages[word])

    def match(self, word: str, gloss: str) -> MeaningAge | None:
        """The norms' meaning this definition describes, if one clearly matches: most
        of the description's stems appear in the definition, and at least one of
        them is not generic."""
        gloss_stems = self.content_stems(gloss)
        best, best_share = None, 0.0
        for meaning in self.meaning_ages.get(word, ()):
            stems = self.content_stems(meaning.description)
            hits = [s for s in stems if any(self._stems_match(s, g) for g in gloss_stems)]
            if not stems or not any(h not in self.generic for h in hits):
                continue
            share = len(hits) / len(stems)
            if share >= MIN_MATCH_SHARE and (share > best_share or (share == best_share and meaning.age < best.age)):
                best, best_share = meaning, share
        return best


class DifficultyModel:
    """Fitted on the bank's words; see the module docstring. `rank` maps every word
    to its frequency rank (lower is more common)."""

    def __init__(self, words: list[str], rank: dict[str, float], prevalence: dict[str, float], matcher: MeaningMatcher):
        self.rank = rank
        self.prevalence = prevalence
        self.matcher = matcher
        ages = matcher.meaning_ages

        with_both = [w for w in words if w in prevalence and w in ages]
        with_prevalence = [w for w in words if w in prevalence]
        targets = [ease_of_share(prevalence[w]) for w in with_both]
        rows = [[1.0, math.log(rank[w]), matcher.first_age(w)] for w in with_both]
        self.with_age = least_squares(rows, targets)
        self.with_age_r2, self.with_age_sd = fit_quality(rows, targets, self.with_age)
        rows = [[1.0, math.log(rank[w])] for w in with_prevalence]
        rank_targets = [ease_of_share(prevalence[w]) for w in with_prevalence]
        self.rank_only = least_squares(rows, rank_targets)
        self.rank_only_r2, self.rank_only_sd = fit_quality(rows, rank_targets, self.rank_only)
        # Ease lost per year that a meaning is learned later.
        rows = [[1.0, matcher.first_age(w)] for w in with_both]
        self.age_slope = least_squares(rows, targets)[1]
        later = [
            m.age - matcher.first_age(w)
            for w in words if len(ages.get(w, ())) > 1
            for m in ages[w] if m.age > matcher.first_age(w)
        ]
        self.secondary_gap = statistics.mean(later) if later else 0.0
        self.counts = {"words": len(words), "with prevalence": len(with_prevalence), "with ages": sum(w in ages for w in words)}

    def predicted_ease(self, word: str) -> tuple[float, float]:
        """Predicted ease and the residual standard deviation of the fit used."""
        if word in self.matcher.meaning_ages:
            a, b, c = self.with_age
            return a + b * math.log(self.rank[word]) + c * self.matcher.first_age(word), self.with_age_sd
        a, b = self.rank_only
        return a + b * math.log(self.rank[word]), self.rank_only_sd

    def word_ease(self, word: str) -> float:
        predicted, spread = self.predicted_ease(word)
        if word not in self.prevalence:
            ease = predicted if "-" in word else predicted - MISSING_WORD_PENALTY * spread
        else:
            measured = ease_of_share(self.prevalence[word])
            ease = (1 - WORD_PREDICTION_WEIGHT) * measured + WORD_PREDICTION_WEIGHT * predicted
        # The norms cannot tell 99% from 100%, and the prediction is a straight line in
        # log rank that overshoots for the most common words, so ease stops at 99%.
        return min(ease, ease_of_share(MAX_SHARE))

    def meaning_ease(self, word: str, gloss: str, is_first: bool) -> MeaningEase:
        meaning = self.matcher.match(word, gloss)
        if meaning is not None:
            gap, source = meaning.age - self.matcher.first_age(word), "age"
        elif is_first:
            gap, source = 0.0, "first"
        else:
            gap, source = self.secondary_gap, "later"
        return MeaningEase(self.word_ease(word) + self.age_slope * gap, source, gap)


def level_cuts(eases: list[float]) -> list[float]:
    """Ease thresholds that split the bank's quiz items into equal fifths: an item
    is level 1 if its ease is at least cuts[0], level 2 if at least cuts[1], and so on."""
    ordered = sorted(eases, reverse=True)
    return [ordered[(len(ordered) * j) // LEVELS] for j in range(1, LEVELS)]


def level_for(ease: float, cuts: list[float]) -> int:
    for level, cut in enumerate(cuts, start=1):
        if ease >= cut:
            return level
    return LEVELS
