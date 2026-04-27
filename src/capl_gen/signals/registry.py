from __future__ import annotations

from pathlib import Path
from typing import Type

from capl_gen.signals.base_parser import BaseParser

# Internal registry: signal_type string → parser class
_REGISTRY: dict[str, Type[BaseParser]] = {}


# ---------------------------------------------------------------------------
# Decorator — used by concrete parser classes to self-register
# ---------------------------------------------------------------------------


def register(cls: Type[BaseParser]) -> Type[BaseParser]:
    """
    Class decorator that registers a parser into the global registry.

    Usage
    -----
    Apply ``@register`` to any ``BaseParser`` subclass::

        @register
        class CANDBCParser(BaseParser):
            signal_type = "CAN_DBC"
            ...

    Raises
    ------
    TypeError
        If the decorated class is not a BaseParser subclass.
    ValueError
        If ``signal_type`` is missing or empty on the class.
    RuntimeError
        If another parser has already been registered for the same signal_type.
    """
    if not (isinstance(cls, type) and issubclass(cls, BaseParser)):
        raise TypeError(
            f"@register can only be applied to BaseParser subclasses, got: {cls}"
        )

    signal_type: str = getattr(cls, "signal_type", "").strip()
    if not signal_type:
        raise ValueError(
            f"Parser class '{cls.__name__}' must define a non-empty 'signal_type' "
            "class attribute before being registered."
        )

    if signal_type in _REGISTRY:
        existing = _REGISTRY[signal_type].__name__
        raise RuntimeError(
            f"Cannot register '{cls.__name__}' for signal_type='{signal_type}': "
            f"already occupied by '{existing}'. Unregister it first."
        )

    _REGISTRY[signal_type] = cls
    return cls


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_parser(signal_type: str, file_path: str | Path) -> BaseParser:
    """
    Instantiate and return the registered parser for *signal_type*.

    Parameters
    ----------
    signal_type:
        One of the registered signal type keys (e.g. ``"CAN_DBC"``).
        Case-sensitive — must match the ``signal_type`` class attribute exactly.
    file_path:
        Path to the file the parser will process.

    Returns
    -------
    BaseParser
        A concrete parser instance, ready to call ``.parse()`` on.

    Raises
    ------
    KeyError
        If no parser has been registered for the given *signal_type*.
    FileNotFoundError
        If *file_path* does not exist (raised by BaseParser.__init__).
    ValueError
        If the file extension is unsupported by the resolved parser.

    Example
    -------
    ::

        from capl_gen.signals.registry import get_parser

        parser = get_parser("CAN_DBC", "path/to/network.dbc")
        result = parser.parse()        # returns ParsedCANData
    """
    if signal_type not in _REGISTRY:
        available = list(_REGISTRY.keys())
        raise KeyError(
            f"No parser registered for signal_type='{signal_type}'. "
            f"Available: {available}"
        )

    parser_cls = _REGISTRY[signal_type]
    return parser_cls(file_path)


def registered_types() -> list[str]:
    """Return a sorted list of all currently registered signal type keys."""
    return sorted(_REGISTRY.keys())


def unregister(signal_type: str) -> None:
    """
    Remove a parser from the registry.

    Primarily useful in tests to swap out a real parser for a mock.

    Raises
    ------
    KeyError
        If *signal_type* is not currently registered.
    """
    if signal_type not in _REGISTRY:
        raise KeyError(f"signal_type='{signal_type}' is not registered.")
    del _REGISTRY[signal_type]


# ---------------------------------------------------------------------------
# Auto-import concrete parsers so their @register decorators fire.
# Keeps usage simple: importing registry is enough to get all parsers.
# ---------------------------------------------------------------------------

def _load_default_parsers() -> None:
    """
    Import all built-in parser modules.

    Adding a new parser = drop the file in signals/ with @register.
    Then add one import line here.
    """
    import importlib

    _builtin_parsers = [
        "capl_gen.signals.can_dbc_parser",
        "capl_gen.signals.someip_arxml_parser",
    ]

    for module_path in _builtin_parsers:
        try:
            importlib.import_module(module_path)
        except ImportError as exc:  # pragma: no cover
            # Log a warning but don't crash — a missing optional dep
            # (e.g. cantools not installed) shouldn't break the whole tool.
            import warnings
            warnings.warn(
                f"Could not load parser module '{module_path}': {exc}",
                stacklevel=2,
            )


_load_default_parsers()