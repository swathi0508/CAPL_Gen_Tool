from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

from capl_gen.schemas.signal import ParsedCANData, ParsedSomeIPData

# Union type for all possible parser return types.
# Extend this as new parsers are added (e.g. ParsedLINData | ParsedFlexRayData).
ParseResult = Union[ParsedCANData, ParsedSomeIPData]


class BaseParser(ABC):
    """
    Abstract Base Class defining the contract for all signal file parsers.

    Every concrete parser must:
      1. Declare a class-level ``signal_type`` string (used by the registry).
      2. Implement ``parse()`` returning a typed Pydantic model (not a raw dict).

    The constructor validates file existence so subclasses don't have to repeat it.

    Usage
    -----
    Parsers are not instantiated directly by callers — use the registry instead:

        from capl_gen.signals.registry import get_parser
        parser = get_parser("CAN_DBC", file_path="path/to/file.dbc")
        result = parser.parse()
    """

    # Subclasses MUST override this at the class level.
    # It must match a SignalType enum value exactly (e.g. "CAN_DBC").
    signal_type: str = ""

    def __init__(self, file_path: str | Path) -> None:
        """
        Parameters
        ----------
        file_path:
            Absolute or relative path to the signal definition file.

        Raises
        ------
        FileNotFoundError
            If the file does not exist at the given path.
        ValueError
            If the file extension is not supported by this parser.
        """
        self._path = Path(file_path).resolve()

        if not self._path.exists():
            raise FileNotFoundError(
                f"[{self.__class__.__name__}] File not found: {self._path}"
            )

        if not self._path.is_file():
            raise ValueError(
                f"[{self.__class__.__name__}] Path is not a file: {self._path}"
            )

        self._validate_extension()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @abstractmethod
    def parse(self) -> ParseResult:
        """
        Parse the input file and return a validated, typed data model.

        Returns
        -------
        ParseResult
            A Pydantic model (ParsedCANData, ParsedSomeIPData, etc.)
            containing all parsed signal/message/interface data.

        Raises
        ------
        capl_gen.core.exceptions.ParseError
            On any parsing failure (malformed file, unsupported version, etc.)
        """

    # ------------------------------------------------------------------
    # Helpers available to subclasses
    # ------------------------------------------------------------------

    @property
    def file_path(self) -> Path:
        """Resolved absolute path to the source file."""
        return self._path

    @property
    def file_name(self) -> str:
        """Filename without directory (e.g. 'my_network.dbc')."""
        return self._path.name

    # ------------------------------------------------------------------
    # Internal / overridable
    # ------------------------------------------------------------------

    def _validate_extension(self) -> None:
        """
        Validate the file extension against ``supported_extensions``.

        Subclasses that support multiple extensions should override
        ``supported_extensions`` as a class attribute:

            supported_extensions: tuple[str, ...] = (".dbc",)
        """
        supported: tuple[str, ...] = getattr(self, "supported_extensions", ())
        if supported and self._path.suffix.lower() not in supported:
            raise ValueError(
                f"[{self.__class__.__name__}] Unsupported file extension "
                f"'{self._path.suffix}'. Expected one of: {supported}"
            )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(file='{self.file_name}')"