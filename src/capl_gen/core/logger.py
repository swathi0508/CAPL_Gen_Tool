import logging
import sys
from pathlib import Path


def setup_logger(log_file: str = "capl_gen.log") -> logging.Logger:
    """Configures console and file logging."""
    logger = logging.getLogger("CAPL_Gen")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(module)s] - %(message)s")

    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    # File Handler
    fh = logging.FileHandler(Path(log_file), mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(ch)
        logger.addHandler(fh)

    return logger

# Global logger instance
log = setup_logger()
