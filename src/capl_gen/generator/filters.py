"""
Custom Jinja2 filters for CAPL code generation.

Registration
------------
All filters are collected in ``CAPL_FILTERS`` — a dict of
``{filter_name: callable}`` that ``JinjaEngine`` registers on the
Jinja2 ``Environment`` at startup.

Adding a new filter
-------------------
1. Write the function here.
2. Add it to ``CAPL_FILTERS`` at the bottom.
3. Use it in a ``.j2`` template: ``{{ value | your_filter }}``.

Filter naming convention
------------------------
Filters that produce CAPL *keywords* or *syntax* use the ``capl_``
prefix.  General-purpose formatters (hex, pad, etc.) do not.

CAPL type system reference
--------------------------
CAPL is a C-like language with these primitive types:

    byte        unsigned  8-bit  (0 … 255)
    word        unsigned 16-bit  (0 … 65535)
    dword       unsigned 32-bit  (0 … 4294967295)
    qword       unsigned 64-bit
    int         signed   16-bit  (−32768 … 32767)   ← note: NOT 32-bit
    long        signed   32-bit
    int64       signed   64-bit
    float       IEEE 754 single-precision
    double      IEEE 754 double-precision
    char        ASCII character
    byte[]      byte array (used for raw payloads)
"""
from __future__ import annotations

import re
from typing import Optional

from capl_gen.schemas.signal import ByteOrder, SomeIPPrimitive


# ---------------------------------------------------------------------------
# Numeric / ID formatting
# ---------------------------------------------------------------------------


def filter_hex(value: object, width: int = 0, prefix: bool = True) -> str:
    """
    Format an integer as a hex string.

    Parameters
    ----------
    value:  Integer to format.
    width:  Minimum digit width (zero-padded).  0 = no padding.
    prefix: Include '0x' prefix (default True).

    Examples
    --------
    >>> filter_hex(416)          → '0x1A0'
    >>> filter_hex(416, width=4) → '0x01A0'
    >>> filter_hex(416, prefix=False) → '1A0'
    """
    try:
        int_val = int(value)
    except (TypeError, ValueError):
        return str(value)

    hex_str = format(int_val, f"0{width}X") if width else format(int_val, "X")
    return f"0x{hex_str}" if prefix else hex_str


def filter_hex_lower(value: object, width: int = 0) -> str:
    """Same as ``hex`` but lowercase, no prefix — e.g. ``1a0``."""
    try:
        int_val = int(value)
    except (TypeError, ValueError):
        return str(value)
    return format(int_val, f"0{width}x") if width else format(int_val, "x")


def filter_dec(value: object) -> str:
    """
    Ensure a value renders as a plain decimal integer string.
    Useful when a value might arrive as float (e.g. 416.0 → '416').
    """
    try:
        return str(int(float(str(value))))
    except (TypeError, ValueError):
        return str(value)


def filter_capl_float(value: object, precision: int = 6) -> str:
    """
    Format a number as a CAPL float literal (always includes decimal point).

    CAPL requires a decimal point to distinguish float from integer literals.

    Examples
    --------
    >>> filter_capl_float(1.0)  → '1.000000'
    >>> filter_capl_float(255)  → '255.000000'
    """
    try:
        return f"{float(value):.{precision}f}"
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Identifier sanitisation
# ---------------------------------------------------------------------------

# CAPL identifiers: start with letter or underscore, then alphanumeric / underscore.
_CAPL_IDENT_INVALID_LEAD = re.compile(r"^[^A-Za-z_]+")
_CAPL_IDENT_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_]")


def filter_capl_identifier(value: str) -> str:
    """
    Convert an arbitrary string into a valid CAPL identifier.

    Rules applied (in order):
    1. Replace any character that is not alphanumeric or underscore with ``_``.
    2. If the result starts with a digit, prepend ``sig_``.
    3. Collapse consecutive underscores into one.
    4. Strip leading/trailing underscores.

    Examples
    --------
    >>> filter_capl_identifier("Engine Speed")    → 'Engine_Speed'
    >>> filter_capl_identifier("0x1A_Signal")     → 'sig_0x1A_Signal' ... → 'sig_1A_Signal'
    >>> filter_capl_identifier("SomeIP::Event_1") → 'SomeIP__Event_1' → 'SomeIP_Event_1'
    """
    s = str(value)
    s = _CAPL_IDENT_INVALID_CHARS.sub("_", s)
    if s and s[0].isdigit():
        s = "sig_" + s
    s = re.sub(r"_+", "_", s)       # collapse consecutive underscores
    s = s.strip("_")
    return s or "unnamed"


def filter_capl_var(signal_name: str, prefix: str = "v") -> str:
    """
    Produce a conventional CAPL local variable name for a signal.

    Convention: ``v{SanitisedSignalName}`` — matches the style used
    in Vector CANalyzer/CANoe test node examples.

    Examples
    --------
    >>> filter_capl_var("Engine Speed")   → 'vEngineSpeed'  (spaces removed, camelCase)
    >>> filter_capl_var("Wheel_Speed_FL") → 'vWheelSpeedFL'
    """
    sanitised = filter_capl_identifier(signal_name)
    # Title-case each underscore-separated word, then remove underscores
    camel = "".join(word.capitalize() for word in sanitised.split("_"))
    return f"{prefix}{camel}"


# ---------------------------------------------------------------------------
# CAPL type mapping
# ---------------------------------------------------------------------------

# Maps SomeIPPrimitive → CAPL type keyword
_SOMEIP_TO_CAPL: dict[SomeIPPrimitive, str] = {
    SomeIPPrimitive.UINT8:   "byte",
    SomeIPPrimitive.UINT16:  "word",
    SomeIPPrimitive.UINT32:  "dword",
    SomeIPPrimitive.UINT64:  "qword",
    SomeIPPrimitive.SINT8:   "int",       # CAPL 'int' = signed 16-bit; closest for sint8
    SomeIPPrimitive.SINT16:  "int",
    SomeIPPrimitive.SINT32:  "long",
    SomeIPPrimitive.SINT64:  "int64",
    SomeIPPrimitive.FLOAT32: "float",
    SomeIPPrimitive.FLOAT64: "double",
    SomeIPPrimitive.BOOLEAN: "byte",      # CAPL has no bool; byte with 0/1 convention
    SomeIPPrimitive.UNKNOWN: "byte",      # safe fallback
}

# Maps Python/DBC bit-length + signed flag → CAPL type keyword
_BITLEN_SIGNED_TO_CAPL: dict[tuple[int, bool], str] = {
    (8,  False): "byte",
    (8,  True):  "int",
    (16, False): "word",
    (16, True):  "int",
    (32, False): "dword",
    (32, True):  "long",
    (64, False): "qword",
    (64, True):  "int64",
}


def filter_capl_type_from_primitive(primitive: SomeIPPrimitive) -> str:
    """
    Map a ``SomeIPPrimitive`` enum value to a CAPL type keyword.

    Examples
    --------
    {{ signal.primitive | capl_type_from_primitive }}
    → 'dword'   (for UINT32)
    """
    return _SOMEIP_TO_CAPL.get(primitive, "byte")


def filter_capl_type_from_signal(length: int, is_signed: bool) -> str:
    """
    Map a CAN signal's bit length + signed flag to a CAPL type keyword.

    For lengths not in the standard map (e.g. 12-bit signals), the
    next-larger standard type is returned.

    Examples
    --------
    {{ msg.signals[0] | capl_type_from_signal }}
    Usage in template: {{ signal.length | capl_type_from_signal(signal.is_signed) }}
    """
    # Exact match first
    if (length, is_signed) in _BITLEN_SIGNED_TO_CAPL:
        return _BITLEN_SIGNED_TO_CAPL[(length, is_signed)]

    # Next-larger standard width
    for width in (8, 16, 32, 64):
        if length <= width:
            return _BITLEN_SIGNED_TO_CAPL.get((width, is_signed), "dword")

    return "qword"  # > 64 bit — unusual, fallback


def filter_capl_byte_order(byte_order: ByteOrder) -> str:
    """
    Map ``ByteOrder`` enum to the CAPL ``getValue`` byte order parameter.

    In CAPL, ``getValue(sig, 0)`` = Motorola/big-endian,
    ``getValue(sig, 1)`` = Intel/little-endian.
    Returns the *literal integer string* for direct use in generated code.
    """
    return "0" if byte_order == ByteOrder.BIG_ENDIAN else "1"


# ---------------------------------------------------------------------------
# CAPL comment & string formatting
# ---------------------------------------------------------------------------


def filter_capl_comment(text: Optional[str], width: int = 76) -> str:
    """
    Wrap text as a CAPL block comment, word-wrapped to *width* characters.

    If *text* is None or blank, returns an empty string.

    Example
    -------
    {{ signal.comment | capl_comment }}
    →
    /* Engine torque request from ECU.
       Valid range: 0..100 % */
    """
    if not text or not text.strip():
        return ""

    words = text.strip().split()
    lines: list[str] = []
    current = ""

    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current.strip())
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)

    if len(lines) == 1:
        return f"/* {lines[0]} */"

    body = "\n   ".join(lines)
    return f"/* {body} */"


def filter_capl_line_comment(text: Optional[str]) -> str:
    """
    Format text as a CAPL single-line comment (``// …``).

    Returns empty string for None / blank input.
    """
    if not text or not text.strip():
        return ""
    return f"// {text.strip()}"


def filter_capl_string_literal(value: str) -> str:
    """
    Escape a string for use as a CAPL string literal (double-quoted).

    CAPL string escapes are the same as C: ``\\``, ``\"``, ``\n``, ``\t``.
    """
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


# ---------------------------------------------------------------------------
# CAPL test / value helpers
# ---------------------------------------------------------------------------


def filter_capl_bool(value: object) -> str:
    """
    Render a Python truthy value as a CAPL integer boolean (1 or 0).

    CAPL has no boolean type — by convention 1 = true, 0 = false.
    """
    return "1" if value else "0"


def filter_choices_to_capl(choices: dict[int, str], var_name: str = "val") -> str:
    """
    Render a DBC value table (``choices`` dict) as a CAPL switch/case block.

    Parameters
    ----------
    choices:  ``{int_value: "label_string"}`` from ``CANSignalModel.choices``.
    var_name: The CAPL variable to switch on (default ``"val"``).

    Example
    -------
    {{ signal.choices | choices_to_capl('rawVal') }}
    →
    switch (rawVal) {
      case 0: write("OFF"); break;
      case 1: write("ON");  break;
      default: write("UNKNOWN"); break;
    }
    """
    if not choices:
        return ""

    lines = [f"switch ({var_name}) {{"]
    for int_val, label in sorted(choices.items()):
        safe_label = label.replace('"', '\\"')
        lines.append(f'  case {int_val}: write("{safe_label}"); break;')
    lines.append('  default: write("UNKNOWN"); break;')
    lines.append("}")
    return "\n".join(lines)


def filter_timeout_ms(value: Optional[int], default: int = 100) -> str:
    """
    Format a timeout value (ms) as a CAPL integer literal.

    Falls back to *default* when value is None.
    """
    ms = int(value) if value is not None else default
    return str(ms)


def filter_cycle_time_ms(value: Optional[int], default: int = 10) -> str:
    """Format a cycle time (ms) as a CAPL integer literal."""
    ms = int(value) if value is not None else default
    return str(ms)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def filter_default_if_none(value: object, default: str = "0") -> object:
    """Return *default* when value is None, otherwise value unchanged."""
    return default if value is None else value


def filter_upper_snake(value: str) -> str:
    """
    Convert a string to UPPER_SNAKE_CASE — used for CAPL constants.

    Example: 'engineSpeed' → 'ENGINE_SPEED'
    """
    s = filter_capl_identifier(value)
    return s.upper()


# ---------------------------------------------------------------------------
# Filter registry — imported and registered by JinjaEngine
# ---------------------------------------------------------------------------

CAPL_FILTERS: dict[str, object] = {
    # Numeric
    "hex":                  filter_hex,
    "hex_lower":            filter_hex_lower,
    "dec":                  filter_dec,
    "capl_float":           filter_capl_float,
    # Identifiers
    "capl_identifier":      filter_capl_identifier,
    "capl_var":             filter_capl_var,
    # Type mapping
    "capl_type_primitive":  filter_capl_type_from_primitive,
    "capl_type_signal":     filter_capl_type_from_signal,
    "capl_byte_order":      filter_capl_byte_order,
    # Comments & strings
    "capl_comment":         filter_capl_comment,
    "capl_line_comment":    filter_capl_line_comment,
    "capl_string":          filter_capl_string_literal,
    # Logic & values
    "capl_bool":            filter_capl_bool,
    "choices_to_capl":      filter_choices_to_capl,
    "timeout_ms":           filter_timeout_ms,
    "cycle_time_ms":        filter_cycle_time_ms,
    # Utility
    "default_if_none":      filter_default_if_none,
    "upper_snake":          filter_upper_snake,
}