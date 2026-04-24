import cantools
from base_parser import BaseParser

from core.logger import log


class SomeIPEventParser(BaseParser):
    """Parses ARXML files using cantools."""

    def parse(self) -> dict:
        log.info(f"Parsing ETH ARXML : {self.file_path}")
        db = cantools.database.load_file(self.file_path)

        parsed_data = {}
        for message in db.messages:
            parsed_data[message.name] = {
                "id": message.frame_id,
                "signals": [sig.name for sig in message.signals]
            }
        return parsed_data
