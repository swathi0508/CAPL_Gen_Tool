import logging
import sys
from pathlib import Path


def setup_logger(log_file: str = "capl_bolt.log") -> logging.Logger:
    """Configures console and file logging, adapting to Prod vs Dev environments."""
    logger = logging.getLogger("CAPL_BOLT")

    # 1. SECURITY LOCK: Detect if we are running as a compiled executable
    is_production = getattr(sys, 'frozen', False)

    # 2. DYNAMIC VERBOSITY: Save CPU cycles in production
    logger.setLevel(logging.INFO if is_production else logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(module)s] - %(message)s")

    # Prevent duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:

        # 3. CONSOLE HANDLER: Always active.
        # (When console=False in your .spec file, Windows just silently dev nulls this,
        # preventing the app from crashing while keeping no trace on the screen).
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # 4. DISK HANDLER: Strictly blocked in Production!
        if not is_production:
            fh = logging.FileHandler(Path(log_file), mode="w", encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            logger.addHandler(fh)

    return logger

# Global logger instance
log = setup_logger()
