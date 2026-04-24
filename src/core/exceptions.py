"""
Custom exception hierarchy for CAPL Gen Tool.

All tool exceptions derive from CAPLGenError so callers can catch
the full family with a single except clause, or target specific
failure modes precisely.

Hierarchy
---------
CAPLGenError
├── ConfigError
├── IngestionError
│   └── ColumnMappingError
├── ParseError
│   ├── DBCParseError
│   └── ARXMLParseError
├── TemplateRenderError
└── OutputWriteError
"""


class CAPLGenError(Exception):
    """Base class for all CAPL Gen Tool errors."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ConfigError(CAPLGenError):
    """Raised when settings or YAML config files are missing or malformed."""


# ---------------------------------------------------------------------------
# Ingestion (Excel reading + validation)
# ---------------------------------------------------------------------------


class IngestionError(CAPLGenError):
    """Raised when the Excel requirement sheet cannot be read or validated."""


class ColumnMappingError(IngestionError):
    """A required column is missing or mis-mapped in the Excel sheet."""


# ---------------------------------------------------------------------------
# Signal parsing
# ---------------------------------------------------------------------------


class ParseError(CAPLGenError):
    """Raised when a signal file (DBC, ARXML, …) cannot be parsed."""


class DBCParseError(ParseError):
    """Specific to CAN DBC parsing failures."""


class ARXMLParseError(ParseError):
    """Specific to SOME/IP ARXML parsing failures."""


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


class TemplateRenderError(CAPLGenError):
    """Raised when Jinja2 template rendering fails."""


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------


class OutputWriteError(CAPLGenError):
    """Raised when generated CAPL files cannot be written to disk."""