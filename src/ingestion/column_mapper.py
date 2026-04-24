"""
Translates raw Excel column headers into the canonical field names
defined in RequirementRow, using the config/column_map.yaml contract.

Responsibilities
----------------
1. Load column_map.yaml (once, cached).
2. Build a {raw_header: canonical_field} lookup table.
3. Rename a pandas DataFrame's columns.
4. Report unmapped / missing required columns clearly.

Why case-insensitive matching?
-------------------------------
Engineers frequently capitalise inconsistently: "Signal Name" vs "signal name"
vs "SIGNAL NAME".  Normalising to lowercase for lookup prevents silent
mismatches while keeping the YAML readable with natural capitalisation.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from loguru import logger

from capl_gen.core.exceptions import ColumnMappingError, IngestionError

# Default location — can be overridden via settings.py later
_DEFAULT_COLUMN_MAP = Path(__file__).parents[2] / "config" / "column_map.yaml"

# Canonical fields that MUST be present after mapping for a sheet to be usable.
# These correspond to non-Optional fields in RequirementRow.
REQUIRED_CANONICAL_FIELDS: frozenset[str] = frozenset(
    {
        "requirement_id",
        "bus_type",
        "signal_name",
        "source_file",
        "template_name",
    }
)


# ---------------------------------------------------------------------------
# Config loader (cached — YAML is read once per process)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def _load_column_map_config(config_path: str) -> dict:
    """Load and cache the column_map.yaml file."""
    path = Path(config_path)
    if not path.exists():
        raise IngestionError(
            f"column_map.yaml not found at: {path}\n"
            "Create one or set CAPL_GEN_COLUMN_MAP env variable to override."
        )
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# ColumnMapper
# ---------------------------------------------------------------------------


class ColumnMapper:
    """
    Renames DataFrame columns from Excel headers to RequirementRow field names.

    Parameters
    ----------
    config_path:
        Path to column_map.yaml.  Defaults to ``config/column_map.yaml``
        relative to the package root.

    Example
    -------
    ::

        mapper = ColumnMapper()
        renamed_df = mapper.apply(raw_df)
    """

    def __init__(self, config_path: str | Path = _DEFAULT_COLUMN_MAP) -> None:
        self._config_path = str(config_path)
        config = _load_column_map_config(self._config_path)

        # {normalised_raw_header → canonical_field_name}
        raw_mappings: dict[str, str] = config.get("column_mappings", {})
        self._lookup: dict[str, str] = {
            k.strip().lower(): v for k, v in raw_mappings.items()
        }

        # Columns to silently drop
        ignored_raw: list[str] = config.get("ignored_columns", [])
        self._ignored: set[str] = {c.strip().lower() for c in ignored_raw}

        self._strict: bool = config.get("strict_unknown_columns", False)

        logger.debug(
            f"ColumnMapper loaded {len(self._lookup)} mappings, "
            f"{len(self._ignored)} ignored columns "
            f"(strict={self._strict})"
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Rename *df* columns to canonical field names and drop ignored columns.

        Parameters
        ----------
        df:
            Raw DataFrame as loaded from Excel (headers = Excel column names).

        Returns
        -------
        pd.DataFrame
            Copy of *df* with renamed columns.  Unmapped columns are either
            dropped (non-strict) or raise ``ColumnMappingError`` (strict).

        Raises
        ------
        ColumnMappingError
            If a required canonical field is absent after mapping, or if
            strict mode is on and an unknown column is encountered.
        """
        rename_map: dict[str, str] = {}
        drop_cols:  list[str]      = []
        unknown:    list[str]      = []

        for col in df.columns:
            normalised = str(col).strip().lower()

            if normalised in self._ignored or normalised == "":
                drop_cols.append(col)
                continue

            canonical = self._lookup.get(normalised)
            if canonical:
                rename_map[col] = canonical
                logger.debug(f"  Column '{col}' → '{canonical}'")
            else:
                unknown.append(col)

        # Handle unknown columns
        if unknown:
            if self._strict:
                raise ColumnMappingError(
                    f"Unmapped columns in strict mode: {unknown}. "
                    "Add them to column_map.yaml or mark as ignored."
                )
            else:
                logger.warning(
                    f"Dropping {len(unknown)} unmapped column(s): {unknown}"
                )
                drop_cols.extend(unknown)

        result = df.drop(columns=drop_cols, errors="ignore").rename(columns=rename_map)

        self._assert_required_fields_present(result)

        return result

    def preview(self, df: pd.DataFrame) -> dict[str, Optional[str]]:
        """
        Dry-run: return a dict of {original_col → mapped_canonical_or_None}
        without modifying the DataFrame.  Useful for GUI column-mapping preview.
        """
        preview: dict[str, Optional[str]] = {}
        for col in df.columns:
            normalised = str(col).strip().lower()
            if normalised in self._ignored:
                preview[col] = None
                continue
            preview[col] = self._lookup.get(normalised)
        return preview

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assert_required_fields_present(self, df: pd.DataFrame) -> None:
        """Raise if any required canonical field is missing after mapping."""
        present = set(df.columns)
        missing = REQUIRED_CANONICAL_FIELDS - present
        if missing:
            raise ColumnMappingError(
                f"Required field(s) missing after column mapping: {sorted(missing)}.\n"
                "Check your column_map.yaml or the Excel headers."
            )