"""Utility to clean __pycache__ folders from the entire repository."""
import shutil
from pathlib import Path


def cleanup_pycache():
    """Delete all __pycache__ folders in the repository."""
    repo_root = Path(__file__).resolve().parents[2]  # Goes up to CAPL_Bolt_Tool root
    for cache_dir in repo_root.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
    print(f"✓ Cleaned __pycache__ from {repo_root}")
