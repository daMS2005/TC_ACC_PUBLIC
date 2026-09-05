"""Resolving identifiers a model reproduced imperfectly.

The ids in this pipeline are long and mostly prose -- a provider name, a
hyphenated description, then a provider id and a hash. A model copying one from
a list reliably keeps the numbers and rewrites the words, and contracts that
treat a near miss as fatal have ended runs over it more than once:

    asked for  pexels-hands-reading-and-tearing-paper-bin-6670603-7617764
    meant      candidate-pexels-hands-tearing-blank-paper-at-cafe-ta-6670603-7617764e

Same clip, same provider id, a paraphrased middle, a dropped prefix and a hash
one character short.

Repairs here are deliberately conservative. A reference is resolved only when
exactly one known id carries the same distinctive number, which makes the
intended target certain. Where several carry it, or none does, the reference is
left alone and still reported -- an id whose numbers match nothing is an
invention rather than a transcription slip, and inventions must not be quietly
accepted.
"""

from __future__ import annotations

import re

# Shorter runs of digits appear inside descriptions ("route-66", "flight-19")
# and would match by coincidence. Provider ids are long.
MINIMUM_DISTINCTIVE_DIGITS = 6


def distinctive_numbers(reference: str) -> list[str]:
    """Digit runs long enough to identify an asset, longest first."""

    numbers = [
        part
        for part in re.split(r"[^0-9]+", reference)
        if len(part) >= MINIMUM_DISTINCTIVE_DIGITS
    ]
    return sorted(numbers, key=len, reverse=True)


def repair_reference(reference: str, known_ids: set[str]) -> str:
    """The id ``reference`` unambiguously meant, or "" when it is not certain."""

    for number in distinctive_numbers(reference):
        # The number must stand on its own in the candidate: "667060" sitting
        # inside "6670603" is a different id that happens to share digits, and
        # a plain substring test would call that a unique match.
        pattern = re.compile(rf"(?<![0-9]){re.escape(number)}(?![0-9])")
        matches = [known for known in known_ids if pattern.search(known)]
        if len(matches) == 1:
            return matches[0]
    return ""


def repair_reference_by_suffix(
    reference: str,
    known_ids: set[str],
    *,
    components: int = 2,
) -> str:
    """Resolve a reference by its trailing dash-separated components.

    The complement of ``repair_reference`` for ids whose distinctive numbers
    are shared rather than unique: every claim in an episode carries the same
    long episode number, and what identifies one claim is the tail
    (``claim-14``). One run wrote them under ``holyshistory-...`` when the
    episode is ``episode-...`` -- prefix mistyped, tail exact -- and
    the stage died. As above, a repair happens only when exactly one known id
    shares the tail, so the intended target is certain.
    """

    tail = str(reference).rsplit("-", components)[-components:]
    suffix = "-".join(tail)
    if not suffix:
        return ""
    matches = [
        known for known in known_ids if known.endswith(f"-{suffix}")
    ]
    if len(matches) == 1:
        return matches[0]
    return ""


# Short tails are ordinary data -- ``claim-14``, ``shot-29`` -- and matching on
# them would resolve to whatever happened to end the same way. A content hash is
# long enough that a collision inside one episode's approved set is not a real
# possibility.
MINIMUM_DISTINCTIVE_HASH_CHARACTERS = 6


def repair_reference_by_hash(reference: str, known_ids: set[str]) -> str:
    """Resolve a reference by the content hash it ends with.

    The complement of ``repair_reference`` for ids whose distinctive part is a
    hash rather than a provider number. A web-image id carries a truncated URL
    and then a hash, and one run asked for

        openai_web_image-unnamed-man-case-pictures-https-news-one-82cc544e

    when no such asset existed. The hash ``82cc544e`` belongs to
    ``...-https-archive-a-82cc544e``, while ``news-one`` belongs to two other
    assets entirely: the model had taken the readable half from one id and the
    hash from another.

    The hash is the half to trust. As the module docstring says, a model copying
    an id keeps the machine-generated part and rewrites the words, so a
    disagreement between them is evidence about which half was remembered rather
    than copied. As everywhere else here, a repair happens only when exactly one
    known id carries the hash.
    """

    tail = str(reference).rsplit("-", 1)[-1].strip().lower()
    if len(tail) < MINIMUM_DISTINCTIVE_HASH_CHARACTERS:
        return ""
    if any(character not in "0123456789abcdef" for character in tail):
        return ""
    matches = [
        known for known in known_ids if known.lower().endswith(f"-{tail}")
    ]
    # Require a complete, unique hash match. A truncated prefix does not
    # establish asset identity, even if only one known hash starts with it.
    return matches[0] if len(matches) == 1 else ""


def _label_key(label: str) -> tuple[str, ...]:
    """Word sequence with casing and punctuation ignored, meaning preserved.

    Two earlier versions each equated labels that mean different things:

    - Stripping everything outside ``[a-z0-9]`` deleted non-Latin and accented
      characters, so ``Subject背影`` and ``Subject`` shared a key.
    - Concatenating the remaining characters erased word boundaries, so
      ``Note Book`` and ``Notebook`` shared one.

    Both put a *wrong* asset on a beat, which is a factual error on screen
    rather than a crash we would see. Keying on the sequence of alphanumeric
    runs keeps word boundaries and every script, while still ignoring the case
    and punctuation drift this repair exists to absorb.
    """

    tokens: list[str] = []
    current: list[str] = []
    for character in str(label).casefold():
        if character.isalnum():
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


# Articles a model adds or drops when it restates a label it was given.
# Stripped only from the front, and only as a fallback: "The Discovery" and
# "Discovery" name one scene, while "Before the Storm" and "Before Storm" are
# not so obviously the same and are left to the exact comparison.
_LEADING_ARTICLES = frozenset({"the", "a", "an"})

# A parenthetical tacked onto the end of a label, which reviewers add to
# tell apart two scenes a plan gave the same name.
_PARENTHETICAL_SUFFIX = re.compile(r"\s*\([^()]*\)\s*$")


def _article_free_key(label: str) -> tuple[str, ...]:
    """``_label_key`` without a leading article, for the fallback tier below."""

    key = _label_key(label)
    # A label that is only an article keeps it; dropping it leaves nothing to
    # match on, and an empty key matches every other empty key.
    if len(key) > 1 and key[0] in _LEADING_ARTICLES:
        return key[1:]
    return key


def repair_label(label: str, known_labels: set[str]) -> str:
    """Resolve a scene label whose wording matches but whose spelling drifted.

    Scene labels are prose, not ids, so the numeric matching above cannot help:
    what varies is casing, punctuation, and spacing -- "Harbour Point, Clareen"
    against "harbour point clareen". Comparing on letters and digits alone settles
    those without accepting a label that means something else. A paraphrase is
    not a spelling difference and is deliberately not matched here; that is an
    invented label and must still be reported.

    A leading article is the one exception, and it is a real one rather than a
    guess: a run died on ``The Enduring Unknowns`` when the plan said
    ``Enduring Unknowns``. Across the stored episodes the same restatement
    appears six more times (``The Final Walk``, ``The Discovery``, ``The Return
    to Clareen`` and others), and in no episode does dropping a leading article
    make two different labels collide -- the article carries no meaning here
    that any of these plans relies on. It is tried only after an exact match
    fails, so it can rescue a label that would otherwise be called invented but
    can never redirect one that already resolves.
    """

    key = _label_key(label)
    if not key:
        return ""
    matches = [known for known in known_labels if _label_key(known) == key]
    if matches:
        return matches[0] if len(matches) == 1 else ""
    article_key = _article_free_key(label)
    matches = [
        known
        for known in known_labels
        if _article_free_key(known) == article_key
    ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return ""
    # A trailing parenthetical is a disambiguator, not a different scene. A
    # plan may carry two scenes under one label, and a reviewer that has to
    # refer to them separately writes "Nothing to Identify Him (forensic
    # examination occurrence)". Nothing downstream knows that name, so the
    # revision it asked for was never applied to any scene.
    stripped = _PARENTHETICAL_SUFFIX.sub("", str(label)).strip()
    if not stripped or stripped == str(label).strip():
        return ""
    stripped_key = _label_key(stripped)
    if not stripped_key:
        return ""
    matches = [
        known for known in known_labels if _label_key(known) == stripped_key
    ]
    return matches[0] if len(matches) == 1 else ""


def repair_labels(
    labels: list[str],
    known_labels: set[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Resolve what can be resolved, reporting each repair as (asked, meant)."""

    resolved: list[str] = []
    repairs: list[tuple[str, str]] = []
    for label in labels:
        value = str(label or "").strip()
        if not value or value in known_labels:
            resolved.append(value)
            continue
        repaired = repair_label(value, known_labels)
        if repaired:
            resolved.append(repaired)
            repairs.append((value, repaired))
        else:
            resolved.append(value)
    return resolved, repairs


def repair_references(
    references: list[str],
    known_ids: set[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Resolve what can be resolved, reporting each repair as (asked, meant)."""

    resolved: list[str] = []
    repairs: list[tuple[str, str]] = []
    for reference in references:
        value = str(reference or "").strip()
        if not value or value in known_ids:
            resolved.append(value)
            continue
        repaired = repair_reference(value, known_ids)
        if repaired:
            resolved.append(repaired)
            repairs.append((value, repaired))
        else:
            resolved.append(value)
    return resolved, repairs
