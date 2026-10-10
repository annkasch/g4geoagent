"""Program checks on what the readers extracted. No LLM in this file.

So far: checks on a single reading. Matching the two readings comes next.
"""

import re
import unicodedata

NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
# numbers inside words such as "Ge-76" or "p+" are names, not values
NAME_NUMBER = re.compile(r"[A-Za-z]+-\d+")
THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
WORDS = {w: float(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
# numbers that point somewhere in the paper instead of stating a value
POINTERS = re.compile(r"\[page \d+\]|\[\d+(?:\s*[,–-]\s*\d+)*\]"
                      r"|(?:Figs?\.?|Figures?|Tables?|Tab\.|Sections?|Sec\.|Eqs?\.?|Refs?\.?|Chapters?)\s*\(?\d+(?:\.\d+)*\)?")
DASHES = "-­‐‑‒–—―−"


def numbers_in(text):
    """Every number written in digits in `text`."""
    text = THOUSANDS.sub("", NAME_NUMBER.sub(" ", text.replace("\u2212", "-")))
    return [float(n) for n in NUMBER.findall(text)]


def as_number(value):
    """The first number in a claim's value, or None for text such as a material name."""
    if isinstance(value, (int, float)):
        return float(value)
    found = numbers_in(str(value))
    return found[0] if found else None


def claim_numbers(claim):
    """All numbers a claim states: its value, or every number inside a text value."""
    if isinstance(claim.value, (int, float)):
        return [float(claim.value)]
    return numbers_in(str(claim.value))


def _squash(text):
    """Only the letters, digits and decimal points of a text, in lower case.

    Line breaks, hyphenation, quotation marks and other typography differ
    between a PDF and a quote of it, and must not make a quote fail.
    """
    text = unicodedata.normalize("NFKC", text).lower().replace("×", "x")
    return re.sub(r"[^a-z0-9.]+|\.(?!\d)", "", text)


def check_quotes(reading, documents):
    """Claims whose quote is not in the cited document, or does not contain the value.

    A count may be written as a word ("two shrouds"). Returns a list of (claim, problem).
    """
    problems = []
    for claim in reading.claims:
        text = documents.get(claim.source)
        if text is None:
            problems.append((claim, f"no document named {claim.source!r}"))
            continue
        if _squash(claim.quote) not in _squash(text):
            problems.append((claim, "quote is not in the document"))
            continue
        quote = unicodedata.normalize("NFKC", claim.quote)
        stated = numbers_in(quote) + [WORDS[w] for w in re.findall(r"[a-z]+", quote.lower()) if w in WORDS]
        for word, factor in (("thousand", 1e3), ("million", 1e6), ("billion", 1e9)):   # "2 millions" states 2000000
            if word in quote.lower():
                stated += [n * factor for n in stated]
        if any(number not in stated for number in claim_numbers(claim)):
            problems.append((claim, "quote does not contain the value"))
    return problems


def uncovered_numbers(reading, documents):
    """Numbers that appear in the documents more often than in the claims.

    For complete descriptions, where every number matters.
    Returns {number: how many occurrences no claim accounts for}.
    """
    missing = {}
    claimed = [n for c in reading.claims for n in claim_numbers(c)]
    for text in documents.values():
        # headings and list markers are not values
        body = re.sub(r"^\s*(#+.*|\d+\.\s)", "", text, flags=re.MULTILINE)
        for number in set(numbers_in(body)):
            short = numbers_in(body).count(number) - claimed.count(number)
            if short > 0:
                missing[number] = missing.get(number, 0) + short
    return missing


def sentences(text):
    """The sentences of a document, each on one line."""
    flat = " ".join(text.split())
    return [s for s in re.split(r"(?<=[.;:])\s+(?=[A-Z\[(])", flat) if s]


def uncovered_near_claims(reading, documents, window=1):
    """Numbers without a claim, in the sentences where the reader found claims and their neighbours.

    For papers, where most numbers are not about construction: only the text
    around existing claims is checked. Returns a list of (number, sentence).
    """
    claimed = {n for c in reading.claims for n in claim_numbers(c)}
    found = []
    for name, text in documents.items():
        parts = sentences(text)
        squashed = [_squash(s) for s in parts]
        starts, total = [], 0
        for s in squashed:
            starts.append(total)
            total += len(s)
        whole, active = "".join(squashed), set()
        for claim in reading.claims:
            quote = _squash(claim.quote)
            at = whole.find(quote) if claim.source == name and quote else -1
            if at < 0:
                continue
            for i, start in enumerate(starts):
                if start < at + len(quote) and start + len(squashed[i]) > at:
                    active.update(range(max(0, i - window), min(len(parts), i + window + 1)))
        for i in sorted(active):
            for number in dict.fromkeys(numbers_in(POINTERS.sub(" ", parts[i]))):
                if number not in claimed:
                    found.append((number, parts[i]))
    return found


def locate(quote, text):
    """Indices of the sentences of `text` that a quote lies in. Empty if the quote is not found."""
    parts = [_squash(s) for s in sentences(text)]
    whole, wanted = "".join(parts), _squash(quote)
    at = whole.find(wanted) if wanted else -1
    if at < 0:
        return set()
    found, start = set(), 0
    for i, part in enumerate(parts):
        if start < at + len(wanted) and start + len(part) > at:
            found.add(i)
        start += len(part)
    return found


def _same_claim(one, other):
    """Do two claims from the same sentence state the same thing?"""
    numbers, others = set(claim_numbers(one)), set(claim_numbers(other))
    if not numbers and not others:
        return one.category == other.category
    if not numbers & others:
        return False
    units = one.unit.strip().lower(), other.unit.strip().lower()
    if all(units):
        return units[0] == units[1]
    # a number can occur twice in a sentence ("2 ton ... 2 millions cubes"): then the quotes must overlap
    quotes = _squash(one.quote), _squash(other.quote)
    return quotes[0] in quotes[1] or quotes[1] in quotes[0]


def match_readings(a, b, documents):
    """Pair up the claims of two readings.

    Two claims are the same if their quotes lie in the same sentence and they
    state the same number with the same unit, or are both text claims of the
    same category. Returns (pairs, only in a, only in b).
    """
    import difflib

    def place(claim):
        return locate(claim.quote, documents.get(claim.source, ""))

    places_b = [place(c) for c in b.claims]
    used, pairs, only_a = set(), [], []
    for claim in a.claims:
        here = place(claim)
        candidates = [j for j, other in enumerate(b.claims)
                      if j not in used and here & places_b[j] and _same_claim(claim, other)]
        if not candidates:
            only_a.append(claim)
            continue
        best = max(candidates, key=lambda j: difflib.SequenceMatcher(None, claim.quote, b.claims[j].quote).ratio())
        used.add(best)
        pairs.append((claim, b.claims[best]))
    return pairs, only_a, [c for j, c in enumerate(b.claims) if j not in used]


def closest_sentences(claim, text, n=3):
    """The sentences most likely meant by a quote that is not in the text word for word."""
    import difflib
    numbers = set(claim_numbers(claim))
    scored = []
    for sentence in sentences(text):
        ratio = difflib.SequenceMatcher(None, claim.quote.lower(), sentence.lower()).ratio()
        bonus = 0.3 if numbers and numbers <= set(numbers_in(sentence)) else 0
        scored.append((ratio + bonus, sentence))
    return [s for _, s in sorted(scored, reverse=True)[:n]]
