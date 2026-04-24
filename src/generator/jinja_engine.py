import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from core.logger import log


class JinjaEngine:
    def __init__(self):
        # --- PYINSTALLER PATHING FIX ---
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Running as a compiled .exe
            base_dir = Path(sys._MEIPASS) / "capl_gen"
        else:
            # Running as a normal Python script
            base_dir = Path(__file__).resolve().parent.parent

        self.template_dir = base_dir / "templates"

        if not self.template_dir.exists():
            log.error(f"Template directory missing at: {self.template_dir}")
            raise FileNotFoundError(f"Missing templates folder at {self.template_dir}")

        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
