from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseParser(ABC):
    """Abstract Base Class defining the contract for all parsers."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path

    @abstractmethod
    def parse(self) -> Dict[str, Any]:
        """Parses the input file and returns a standardized dictionary."""
        pass