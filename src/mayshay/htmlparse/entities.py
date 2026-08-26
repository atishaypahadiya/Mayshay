"""
Character reference decoding.

The named reference table is `html.entities.html5` from the standard library:
2231 entries, 106 of which have no trailing semicolon, longest key 32 chars.
That module is a data table (the WHATWG named character reference list), not
a parser -- the longest-match and legacy-semicolon rules below are hand-rolled.
See the CLAUDE.md rules section.
"""

from __future__ import annotations

from html.entities import html5 as NAMED_REFS

MAX_REF_LEN = max(len(k) for k in NAMED_REFS)  # 32

# Numeric references in this range are remapped to Windows-1252, because a
# generation of authors emitted cp1252 bytes and called them code points.
C1_REPLACEMENTS = {
    0x80: "€", 0x82: "‚", 0x83: "ƒ", 0x84: "„",
    0x85: "…", 0x86: "†", 0x87: "‡", 0x88: "ˆ",
    0x89: "‰", 0x8A: "Š", 0x8B: "‹", 0x8C: "Œ",
    0x8E: "Ž", 0x91: "‘", 0x92: "’", 0x93: "“",
    0x94: "”", 0x95: "•", 0x96: "–", 0x97: "—",
    0x98: "˜", 0x99: "™", 0x9A: "š", 0x9B: "›",
    0x9C: "œ", 0x9E: "ž", 0x9F: "Ÿ",
}

REPLACEMENT = "�"

# A parse error as (offset, message), or None. The offset obeys the tokenizer's
# convention: it points at the character that caused the error.
ParseError = tuple[int, str] | None


def _decode_numeric(source: str, start: int) -> tuple[str, int, ParseError]:
    i = start + 1  # skip '#'
    hex_mode = i < len(source) and source[i] in "xX"
    if hex_mode:
        i += 1
    digits_start = i
    allowed = "0123456789abcdefABCDEF" if hex_mode else "0123456789"
    while i < len(source) and source[i] in allowed:
        i += 1
    if i == digits_start:
        # The offender is the non-digit itself, which is sitting at
        # digits_start -- one past the '#', or two past it after "#x". Note
        # that new_pos stays at `start`: nothing is consumed, so the caller
        # must not derive the offset from it.
        return "&", start, (
            digits_start, "absence of digits in numeric character reference"
        )

    value = int(source[digits_start:i], 16 if hex_mode else 10)
    error: ParseError = None
    if i < len(source) and source[i] == ";":
        i += 1
    else:
        # `i` still points at the character where the ';' should have been.
        # Capture it now, before the bump above can move it.
        error = (i, "missing semicolon after character reference")

    # The two value errors below are reported at `ref_start`, the '&'. Unlike
    # every other parse error in the tokenizer, no single character causes
    # them: the offence is the code point the reference as a whole denotes, so
    # "the character that caused the error" has no unique answer. The opening
    # '&' is the one character guaranteed to exist and to belong to the
    # offending construct, which makes it the stable choice for a caret.
    # Documented in Tokenizer._error's convention note.
    ref_start = start - 1
    if value in C1_REPLACEMENTS:
        return C1_REPLACEMENTS[value], i, (ref_start, "control character reference")
    if value == 0 or value > 0x10FFFF or 0xD800 <= value <= 0xDFFF:
        return REPLACEMENT, i, (ref_start, "invalid numeric character reference")
    return chr(value), i, error


def decode_reference(
    source: str, start: int, in_attribute: bool
) -> tuple[str, int, ParseError]:
    """
    Decode the reference beginning at `start`, which is the offset just past
    the '&'. Returns (replacement, new_offset, error_or_None), where the error
    is a (offset, message) pair.

    The error carries its own offset rather than letting the caller derive one
    from `new_offset`: the two are not the same character, and on the
    absence-of-digits path `new_offset` has not moved at all. Every offset
    follows the tokenizer's convention -- see Tokenizer._error.

    If nothing matches, returns ("&", start, ...) -- the caller emits a literal
    ampersand and carries on from where it was.
    """
    if start >= len(source):
        return "&", start, None
    if source[start] == "#":
        return _decode_numeric(source, start)

    window = source[start : start + MAX_REF_LEN]
    match = None
    for length in range(len(window), 0, -1):
        if window[:length] in NAMED_REFS:
            match = window[:length]
            break
    if match is None:
        return "&", start, None

    end = start + len(match)
    if not match.endswith(";"):
        nxt = source[end : end + 1]
        # Legacy rule: inside an attribute, a semicolon-less reference
        # followed by '=' or an alphanumeric is left alone. This is what
        # keeps query strings like "?a&copy=1" intact.
        if in_attribute and (nxt == "=" or (nxt.isascii() and nxt.isalnum())):
            return "&", start, None
        # `end` is the character where the ';' should have been.
        return NAMED_REFS[match], end, (
            end, "missing semicolon after character reference"
        )
    return NAMED_REFS[match], end, None
