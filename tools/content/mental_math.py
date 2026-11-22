"""Mental Math question bank.

Every question is a unique (operation, left, right) triple with a difficulty from
1 to 5 and three distractors modeled on common arithmetic mistakes. Generation is
seeded, so the output is identical on every run.

Difficulty levels
-----------------
Addition / subtraction:
  1  single-digit facts; two-digit +/- one-digit with no carry or borrow
  2  two-digit +/- one-digit with a carry or borrow; two-digit +/- two-digit without
  3  two-digit +/- two-digit with a carry or borrow; three-digit +/- one- or two-digit without
  4  three-digit +/- one- or two-digit with a carry or borrow; three-digit +/- three-digit without
  5  three-digit +/- three-digit with carries or borrows; four-digit +/- three-digit
Multiplication:
  1  times tables for 1-5 and 10
  2  times tables for 6-9; x11 up to 9; round tens times one digit
  3  12-49 times one digit
  4  51-99 times one digit; teen times teen
  5  two-digit times two-digit; three-digit times one digit
Division (always exact):
  1  divide by 2-5 or 10 with a quotient up to 10
  2  divide by 6-12 with a quotient up to 10; quotients of 11-12
  3  divide by 2-9 with a quotient of 13-49
  4  divide by 2-9 with a quotient of 50-199
  5  divide by a two-digit number with a two-digit quotient
"""

from __future__ import annotations

import random
from dataclasses import dataclass

SEED = 20261121
PER_LEVEL = 750  # target questions per operation per difficulty (smaller pools are used whole)

ADD, SUB, MUL, DIV = "+", "-", "*", "/"
OPERATIONS = (ADD, SUB, MUL, DIV)


@dataclass(frozen=True)
class MathQuestion:
    operation: str
    lhs: int
    rhs: int
    answer: int
    difficulty: int
    distractors: tuple[int, int, int]


def digit_count(n: int) -> int:
    return len(str(n))


def carries(a: int, b: int) -> int:
    count, carry = 0, 0
    while a or b:
        total = a % 10 + b % 10 + carry
        carry = 1 if total >= 10 else 0
        count += carry
        a //= 10
        b //= 10
    return count


def borrows(a: int, b: int) -> int:
    count, borrow = 0, 0
    while a or b:
        top = a % 10 - borrow
        bottom = b % 10
        borrow = 1 if top < bottom else 0
        count += borrow
        a //= 10
        b //= 10
    return count


def addition_level(a: int, b: int) -> int | None:
    big, small = sorted((digit_count(a), digit_count(b)), reverse=True)
    c = carries(a, b)
    if big == 1:
        return 1
    if big == 2 and small == 1:
        return 1 if c == 0 else 2
    if big == 2 and small == 2:
        return 2 if c == 0 else 3
    if big == 3 and small <= 2:
        return 3 if c == 0 else 4
    if big == 3 and small == 3:
        return 4 if c == 0 else 5
    if big == 4 and small == 3:
        return 5
    return None


def subtraction_level(a: int, b: int) -> int | None:
    if b < 1 or a <= b:
        return None
    da, db = digit_count(a), digit_count(b)
    br = borrows(a, b)
    if a <= 18 and b <= 9 and a - b <= 9:
        return 1
    if da == 2 and db == 1:
        return 1 if br == 0 else 2
    if da == 2 and db == 2:
        return 2 if br == 0 else 3
    if da == 3 and db <= 2:
        return 3 if br == 0 else 4
    if da == 3 and db == 3:
        return 4 if br == 0 else 5
    if da == 4 and db == 3:
        return 5
    return None


def addition_pairs(level: int, rng: random.Random) -> set[tuple[int, int]]:
    domains = {
        1: [(1, 9, 1, 9), (10, 99, 1, 9), (1, 9, 10, 99)],
        2: [(10, 99, 1, 9), (1, 9, 10, 99), (10, 99, 10, 99)],
        3: [(10, 99, 10, 99), (100, 999, 1, 99), (1, 99, 100, 999)],
        4: [(100, 999, 1, 99), (1, 99, 100, 999), (100, 999, 100, 999)],
        5: [(100, 999, 100, 999), (1000, 9999, 100, 999), (100, 999, 1000, 9999)],
    }[level]
    return sample_pairs(domains, lambda a, b: addition_level(a, b) == level, rng)


def subtraction_pairs(level: int, rng: random.Random) -> set[tuple[int, int]]:
    domains = {
        1: [(2, 18, 1, 9), (10, 99, 1, 9)],
        2: [(10, 99, 1, 9), (10, 99, 10, 99)],
        3: [(10, 99, 10, 99), (100, 999, 1, 99)],
        4: [(100, 999, 1, 99), (100, 999, 100, 999)],
        5: [(100, 999, 100, 999), (1000, 9999, 100, 999)],
    }[level]
    return sample_pairs(domains, lambda a, b: subtraction_level(a, b) == level, rng)


def sample_pairs(domains, accept, rng: random.Random) -> set[tuple[int, int]]:
    """Enumerates small domains exhaustively and samples large ones."""
    pairs: set[tuple[int, int]] = set()
    for a_lo, a_hi, b_lo, b_hi in domains:
        size = (a_hi - a_lo + 1) * (b_hi - b_lo + 1)
        if size <= 20_000:
            pairs.update((a, b) for a in range(a_lo, a_hi + 1) for b in range(b_lo, b_hi + 1) if accept(a, b))
        else:
            for _ in range(60_000):
                a, b = rng.randint(a_lo, a_hi), rng.randint(b_lo, b_hi)
                if accept(a, b):
                    pairs.add((a, b))
    return pairs


def multiplication_pairs(level: int, rng: random.Random) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    if level == 1:
        easy = {1, 2, 3, 4, 5, 10}
        pairs = {(a, b) for a in range(1, 11) for b in range(1, 11) if a in easy or b in easy}
    elif level == 2:
        pairs |= {(a, b) for a in range(6, 10) for b in range(6, 10)}
        pairs |= {(11, k) for k in range(2, 10)} | {(k, 11) for k in range(2, 10)}
        pairs |= {(t, k) for t in range(20, 100, 10) for k in range(2, 10)}
        pairs |= {(k, t) for t in range(20, 100, 10) for k in range(2, 10)}
    elif level == 3:
        for a in range(12, 50):
            if a % 10 == 0:
                continue
            for b in range(2, 10):
                pairs |= {(a, b), (b, a)}
    elif level == 4:
        for a in range(51, 100):
            if a % 10 == 0:
                continue
            for b in range(2, 10):
                pairs |= {(a, b), (b, a)}
        pairs |= {(a, b) for a in range(11, 20) for b in range(11, 20)}
    elif level == 5:
        while len(pairs) < PER_LEVEL * 3:
            if rng.random() < 0.7:
                a, b = rng.randint(13, 99), rng.randint(13, 99)
                if a % 10 == 0 or b % 10 == 0 or (a < 20 and b < 20):
                    continue
            else:
                a, b = rng.randint(101, 999), rng.randint(3, 9)
                if a % 100 == 0:
                    continue
                if rng.random() < 0.5:
                    a, b = b, a
            pairs.add((a, b))
    return pairs


def division_pairs(level: int, rng: random.Random) -> set[tuple[int, int]]:
    """Returns (dividend, divisor) pairs."""
    facts: set[tuple[int, int]] = set()  # (divisor, quotient)
    if level == 1:
        facts = {(d, q) for d in (2, 3, 4, 5, 10) for q in range(1, 11)}
    elif level == 2:
        facts |= {(d, q) for d in range(6, 13) for q in range(2, 11)}
        facts |= {(d, q) for d in range(2, 10) for q in (11, 12)}
    elif level == 3:
        facts = {(d, q) for d in range(2, 10) for q in range(13, 50)}
    elif level == 4:
        facts = {(d, q) for d in range(2, 10) for q in range(50, 200)}
    elif level == 5:
        facts = {(d, q) for d in range(11, 100) for q in range(11, 100) if d % 10 != 0}
    return {(d * q, d) for d, q in facts}


def distractors(operation: str, a: int, b: int, answer: int, rng: random.Random) -> tuple[int, int, int]:
    """Three wrong answers drawn from typical mistakes.

    The mix always includes a near miss and, for larger answers, a value with the
    same last digit, so neither "closest number" nor "check the last digit"
    shortcuts reveal the answer.
    """
    minimum = 1 if operation == DIV else 0
    near: list[int] = []
    same_last_digit: list[int] = []
    method: list[int] = []

    def add(bucket: list[int], value: int) -> None:
        if value != answer and value >= minimum and value not in bucket:
            bucket.append(value)

    for delta in (1, -1, 2, -2) if answer >= 10 else (1, -1, 2, -2, 3, -3):
        add(near, answer + delta)
    if answer >= 20:
        add(same_last_digit, answer + 10)
        add(same_last_digit, answer - 10)
    if answer >= 200:
        add(same_last_digit, answer + 100)
        add(same_last_digit, answer - 100)

    if operation == ADD:
        # Forgot to carry: add each column independently.
        no_carry = int("".join(str((int(x) + int(y)) % 10) for x, y in zip(str(a).zfill(5), str(b).zfill(5))))
        add(method, no_carry)
    elif operation == SUB:
        # Subtracted the smaller digit from the larger in every column.
        smaller_from_larger = int("".join(str(abs(int(x) - int(y))) for x, y in zip(str(a).zfill(5), str(b).zfill(5))))
        add(method, smaller_from_larger)
    elif operation == MUL:
        for value in ((a + 1) * b, (a - 1) * b, a * (b + 1), a * (b - 1)):
            add(method, value)
        if a > 10 and b < 10:
            # Multiplied only the tens or forgot to carry into them.
            add(method, (a // 10) * 10 * b + (a % 10) * b % 10)
    elif operation == DIV:
        add(method, answer + 1)
        add(method, answer - 1)
        if answer > 10:
            add(method, answer + 10)
            add(method, answer - 10)

    picks: list[int] = []

    def take(bucket: list[int]) -> None:
        options = [v for v in bucket if v not in picks]
        if options:
            picks.append(rng.choice(options))

    plausible_method = [v for v in method if answer == 0 or abs(v - answer) <= max(10, answer * 0.6)]
    take(plausible_method or method)
    take(near)
    take(same_last_digit if same_last_digit else near)
    pool = [v for v in near + same_last_digit + method if v not in picks]
    while len(picks) < 3 and pool:
        picks.append(pool.pop(rng.randrange(len(pool))))
    offset = 3
    while len(picks) < 3:
        candidate = answer + offset
        if candidate not in picks and candidate != answer:
            picks.append(candidate)
        offset = -offset if offset > 0 else -offset + 1
    return tuple(picks[:3])  # type: ignore[return-value]


def generate() -> list[MathQuestion]:
    rng = random.Random(SEED)
    questions: list[MathQuestion] = []
    seen: set[tuple[str, int, int]] = set()
    builders = {
        ADD: (addition_pairs, lambda a, b: a + b),
        SUB: (subtraction_pairs, lambda a, b: a - b),
        MUL: (multiplication_pairs, lambda a, b: a * b),
        DIV: (division_pairs, lambda a, b: a // b),
    }
    for level in range(1, 6):
        for operation in OPERATIONS:
            make_pairs, evaluate = builders[operation]
            pairs = sorted(make_pairs(level, rng))
            # Earlier levels claim shared pairs first, so each pair keeps its easiest level.
            pairs = [p for p in pairs if (operation, *p) not in seen]
            if len(pairs) > PER_LEVEL:
                pairs = rng.sample(pairs, PER_LEVEL)
            for a, b in sorted(pairs):
                answer = evaluate(a, b)
                seen.add((operation, a, b))
                questions.append(
                    MathQuestion(operation, a, b, answer, level, distractors(operation, a, b, answer, rng))
                )
    return questions


if __name__ == "__main__":
    from collections import Counter

    bank = generate()
    print(f"{len(bank)} questions")
    print(Counter((q.difficulty, q.operation) for q in bank))
    for q in random.Random(1).sample(bank, 12):
        print(q)
