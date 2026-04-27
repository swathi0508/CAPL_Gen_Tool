"""
Reads the requirements Excel sheet, maps columns, and validates each row
into a typed RequirementRow Pydantic model.

Data flow
---------
    .xlsx file
        │
        ▼  (pandas)
    raw DataFrame                 ← raw column headers, mixed types
        │
        ▼  (ColumnMapper)
    renamed DataFrame             ← canonical column names
        │
        ▼  (row iteration)
    dict per row                  ← still raw Python types
        │
        ▼  (RequirementRow(**row_dict))
    RequirementRow  OR  InvalidRow
        │
        ▼
    IngestionResult               ← returned to caller
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger
from pydantic import ValidationError

from capl_gen.core.exceptions import IngestionError
from capl_gen.ingestion.column_mapper import ColumnMapper
from capl_gen.schemas.requirement import IngestionResult, InvalidRow, RequirementRow


class ExcelReader:
    """
    Loads a requirements Excel sheet and returns an ``IngestionResult``.

    Parameters
    ----------
    file_path:
        Path to the ``.xlsx`` / ``.xls`` file.
    sheet_name:
        Worksheet to read.  Defaults to the first sheet (index 0).
    column_mapper:
        Pre-configured ``ColumnMapper`` instance.  If not supplied, one
        is constructed with the default ``column_map.yaml``.
    header_row:
        0-based row index of the header row (default 0 = first row).
    skip_empty_rows:
        Drop rows where ALL cells are NaN before validation (default True).

    Example
    -------
    ::

        reader = ExcelReader("requirements.xlsx")
        result = reader.read()
        for row in result.active_rows:
            print(row.signal_name, row.template_name)
    """

    # Pandas uses these sentinel values for blank cells — normalise to None.
    _NA_STRINGS = {"", "nan", "none", "n/a", "na", "-"}

    def __init__(
        self,
        file_path: str | Path,
        sheet_name: str | int = 0,
        column_mapper: Optional[ColumnMapper] = None,
        header_row: int = 0,
        skip_empty_rows: bool = True,
    ) -> None:
        self._path = Path(file_path).resolve()
        self._sheet_name = sheet_name
        self._mapper = column_mapper or ColumnMapper()
        self._header_row = header_row
        self._skip_empty = skip_empty_rows

        if not self._path.exists():
            raise FileNotFoundError(f"Excel file not found: {self._path}")
        if self._path.suffix.lower() not in {".xlsx", ".xls", ".xlsm"}:
            raise IngestionError(
                f"Unsupported file type '{self._path.suffix}'. "
                "Expected .xlsx / .xls / .xlsm"
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def read(self) -> IngestionResult:
        """
        Read, map, and validate the entire sheet.

        Returns
        -------
        IngestionResult
            Contains ``valid_rows``, ``invalid_rows``, and summary stats.
            Callers should use ``result.active_rows`` to get only the rows
            that should be passed to the generator.

        Raises
        ------
        IngestionError
            If the sheet cannot be read at all (wrong name, corrupt file, etc.)
        """
        logger.info(f"Reading Excel sheet: {self._path}  [sheet={self._sheet_name}]")

        raw_df = self._load_dataframe()
        mapped_df = self._apply_column_mapping(raw_df)
        valid_rows, invalid_rows = self._validate_rows(mapped_df)

        result = IngestionResult(
            source_file=str(self._path),
            sheet_name=str(self._sheet_name),
            total_rows=len(mapped_df),
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
        )

        logger.success(result.summary())
        if invalid_rows:
            logger.warning(
                f"{len(invalid_rows)} row(s) failed validation — "
                "check the ingestion report for details."
            )
        return result

    def preview_column_mapping(self) -> dict[str, str | None]:
        """
        Return a dry-run mapping of Excel headers → canonical field names
        without loading/validating rows.  Useful for the GUI mapping panel.
        """
        raw_df = self._load_dataframe(nrows=0)   # headers only
        return self._mapper.preview(raw_df)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_dataframe(self, nrows: Optional[int] = None) -> pd.DataFrame:
        """Load the raw DataFrame from the Excel file."""
        try:
            df = pd.read_excel(
                self._path,
                sheet_name=self._sheet_name,
                header=self._header_row,
                nrows=nrows,
                dtype=str,       # keep everything as string initially; Pydantic coerces
                engine="openpyxl",
            )
        except ValueError as exc:
            # sheet_name not found
            raise IngestionError(
                f"Sheet '{self._sheet_name}' not found in '{self._path.name}'. "
                f"Available sheets: {self._get_sheet_names()}"
            ) from exc
        except Exception as exc:
            raise IngestionError(
                f"Could not read '{self._path.name}': {exc}"
            ) from exc

        logger.debug(
            f"Loaded raw DataFrame: {len(df)} rows × {len(df.columns)} cols"
        )

        if self._skip_empty and nrows is None:
            before = len(df)
            df = df.dropna(how="all").reset_index(drop=True)
            dropped = before - len(df)
            if dropped:
                logger.debug(f"Dropped {dropped} fully-empty row(s)")

        return df

    def _apply_column_mapping(self, df: pd.DataFrame) -> pd.DataFrame:
        """Delegate to ColumnMapper and return renamed DataFrame."""
        try:
            return self._mapper.apply(df)
        except Exception as exc:
            # Wrap so callers see IngestionError, not ColumnMappingError
            raise IngestionError(f"Column mapping failed: {exc}") from exc

    def _validate_rows(
        self, df: pd.DataFrame
    ) -> tuple[list[RequirementRow], list[InvalidRow]]:
        """Iterate rows and build RequirementRow instances via Pydantic."""
        valid:   list[RequirementRow] = []
        invalid: list[InvalidRow]     = []

        for idx, raw_row in enumerate(df.to_dict(orient="records")):
            cleaned = self._clean_row(raw_row)
            cleaned["row_index"] = idx          # inject for error reporting

            try:
                row = RequirementRow(**cleaned)
                valid.append(row)
            except ValidationError as exc:
                error_summary = self._summarise_validation_error(exc)
                invalid.append(
                    InvalidRow(
                        row_index=idx,
                        raw_data=raw_row,
                        error_message=error_summary,
                    )
                )
                logger.debug(f"Row {idx} invalid: {error_summary}")

        return valid, invalid

    def _clean_row(self, row: dict) -> dict:
        """
        Normalise a raw row dict before Pydantic validation:
        - Convert sentinel NA strings to None
        - Strip leading/trailing whitespace from strings
        """
        cleaned: dict = {}
        for key, value in row.items():
            if isinstance(value, str):
                stripped = value.strip()
                cleaned[key] = None if stripped.lower() in self._NA_STRINGS else stripped
            elif pd.isna(value) if not isinstance(value, (list, dict)) else False:
                cleaned[key] = None
            else:
                cleaned[key] = value
        return cleaned

    @staticmethod
    def _summarise_validation_error(exc: ValidationError) -> str:
        """Produce a compact single-line summary of all Pydantic errors."""
        parts = []
        for error in exc.errors():
            field = " → ".join(str(loc) for loc in error["loc"])
            msg   = error["msg"]
            parts.append(f"[{field}] {msg}")
        return " | ".join(parts)

    def _get_sheet_names(self) -> list[str]:
        """Return available sheet names for a better error message."""
        try:
            xl = pd.ExcelFile(self._path, engine="openpyxl")
            return xl.sheet_names
        except Exception:
            return ["<could not read sheet names>"]