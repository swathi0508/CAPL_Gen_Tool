import pandas as pd

from capl_gen.core.logger import log


class ExcelMapper:
    """Reads Excel requirements and maps them to internal dictionaries/objects."""
    def __init__(self, excel_path: str):
        self.excel_path = excel_path

    def load_requirements(self) -> pd.DataFrame:
        log.info(f"Loading requirements from {self.excel_path}")
        try:
            df = pd.read_excel(self.excel_path, engine="openpyxl")
            return df
        except Exception as e:
            log.error(f"Failed to load Excel: {e}")
            raise
