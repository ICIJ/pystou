"""Rules that turn a path component into a valid, portable S3 key component.

Every function here is pure: no filesystem access, no logging. That keeps the
rule matrix table-testable and keeps ``normalize/main.py`` about traversal.
"""

import re
import unicodedata
from collections.abc import Sequence

RULES: tuple[str, ...] = ("utf8", "nfc", "control", "punct")
FALLBACK = "unnamed"

# Undecodable bytes reach us as lone surrogates via PEP 383 surrogateescape.
_SURROGATES = re.compile(r"[\udc80-\udcff]+")
# A high/low surrogate pair encoded as UTF-8 (CESU-8). These byte sequences are
# never produced by valid UTF-8, so decoding them back is deterministic.
_CESU8 = re.compile(rb"\xed[\xa0-\xaf][\x80-\xbf]\xed[\xb0-\xbf][\x80-\xbf]")
_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
_PUNCT = re.compile(r"[\\{}^%`\[\]~<>#|]+")
# ASCII only: NBSP and the ideographic space are valid, S3-safe UTF-8 and the
# control rule never claimed them. A Unicode-aware ``\s`` would rewrite them.
_ASCII_SPACE = " \t\n\r\f\v"
_WHITESPACE = re.compile(f"[{re.escape(_ASCII_SPACE)}]+")


def _decode_cesu8_pair(match: "re.Match[bytes]") -> bytes:
    """Rebuilds the astral codepoint a CESU-8 surrogate pair encodes."""
    raw = match.group()
    high = ((raw[0] & 0x0F) << 12) | ((raw[1] & 0x3F) << 6) | (raw[2] & 0x3F)
    low = ((raw[3] & 0x0F) << 12) | ((raw[4] & 0x3F) << 6) | (raw[5] & 0x3F)
    return chr(0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)).encode("utf-8")


def fix_utf8(name: str) -> tuple[str, str]:
    """Makes a name decodable as UTF-8, repairing before destroying.

    Args:
        name: Path component, possibly carrying surrogateescape bytes.

    Returns:
        tuple[str, str]: The name and the outcome, one of ``clean``
        (already valid), ``repaired`` (every bad byte was a recoverable CESU-8
        surrogate pair), or ``stripped`` (bytes were lost).
    """
    raw = name.encode("utf-8", "surrogateescape")
    try:
        raw.decode("utf-8")
        return name, "clean"
    except UnicodeDecodeError:
        pass
    repaired = _CESU8.sub(_decode_cesu8_pair, raw)
    try:
        return repaired.decode("utf-8"), "repaired"
    except UnicodeDecodeError:
        salvaged = repaired.decode("utf-8", "surrogateescape")
        return _SURROGATES.sub("_", salvaged), "stripped"


def trim(name: str) -> str:
    """Collapses ASCII whitespace runs and drops trailing spaces and dots."""
    return _WHITESPACE.sub(" ", name).strip(_ASCII_SPACE).rstrip(" .")


def normalize_name(name: str, rules: Sequence[str] = RULES) -> tuple[str, str, list[str]]:
    """Applies the selected rules to one path component.

    Rules run in a fixed order because later ones assume earlier ones
    succeeded: NFC cannot normalize a lone surrogate, and trimming must come
    after punctuation removal or the result stops being idempotent.

    Args:
        name: The path component to normalize.
        rules: Subset of :data:`RULES` to apply.

    Returns:
        tuple[str, str, list[str]]: The new name, the UTF-8 outcome, and the
        rules that actually changed something.
    """
    applied: list[str] = []
    mode = "clean"
    result = name

    if "utf8" in rules:
        result, mode = fix_utf8(result)
        if mode != "clean":
            applied.append("utf8")
    if "nfc" in rules:
        # Safe even when utf8 was not selected: normalize() passes lone
        # surrogates through untouched rather than raising.
        result = _record(unicodedata.normalize("NFC", result), result, "nfc", applied)
    if "control" in rules:
        result = _record(trim(_CONTROLS.sub(" ", result)), result, "control", applied)
    if "punct" in rules:
        result = _record(_PUNCT.sub("", result), result, "punct", applied)
    if "control" in rules:
        # Punctuation removal can expose a trailing space, so the trim runs
        # last; the rule that owns it must still be credited.
        result = _record(trim(result), result, "control", applied)

    if result in ("", ".", ".."):
        result = FALLBACK
    return result, mode, applied


def _record(new: str, old: str, rule: str, applied: list[str]) -> str:
    """Returns ``new``, noting ``rule`` in ``applied`` when it changed ``old``."""
    if new != old and rule not in applied:
        applied.append(rule)
    return new
