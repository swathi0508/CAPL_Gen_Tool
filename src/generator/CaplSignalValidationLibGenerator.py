import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from logger import log


class CaplSignalValidationLibGenerator:
    def __init__(self, eth_db_source, template_dir):
        # We accept the raw source, which could be a dict or a file path
        self.template_dir = Path(template_dir)
        self.env = Environment(loader=FileSystemLoader(self.template_dir))
        self.eth_data = self._load_data(eth_db_source)

    def _load_data(self, source) -> dict:
        """Loads data directly from RAM, or falls back to disk reading if needed."""

        # 1. IN-MEMORY PIPELINE: If passed a dictionary, unwrap and return it!
        if isinstance(source, dict):
            return source.get("SIGNAL_LIST", source.get("SOMEIP_SIGNAL", source))

        # 2. LEGACY DISK PIPELINE: If passed a string path, open the file
        if isinstance(source, str) and os.path.exists(source):
            try:
                import json
                with open(source, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                    return raw_data.get("SIGNAL_LIST", raw_data.get("SOMEIP_SIGNAL", raw_data))
            except Exception as e:
                log.error(f"Failed to load JSON from {source}: {e}")

        return {}

    def _resolve(self, signal_list, event, attribute, target_enum):
        """Searches the JSON structure for the matching event and attribute."""
        if not signal_list:
            log.error(f"Lib Gen: Cannot resolve '{event}' - no signal data loaded.")
            return {"path": "MISSING_DATA", "enum_name": "MISSING_DATA", "enum_value": "MISSING_DATA"}

        for path, details in signal_list.items():
            if details.get("Event") == event and details.get("Attribute_Value") == attribute:
                enums = details.get("Enums", {})
                if target_enum in enums.values():
                    # Get the numeric key for the enum string
                    val = next((k for k, v in enums.items() if v == target_enum), "0")
                    return {"path": path, "enum_name": target_enum, "enum_value": val}

                log.error(f"Lib Gen: Enum '{target_enum}' not found for signal '{path}'")
                return {"path": path, "enum_name": "MISSING_DATA", "enum_value": "MISSING_DATA"}

        log.error(f"Lib Gen: Could not resolve signal for Event={event}, Attr={attribute}")
        return {"path": "MISSING_DATA", "enum_name": "MISSING_DATA", "enum_value": "MISSING_DATA"}

    def render(self, output_path):
        """Renders the Library using the securely loaded in-memory data."""
        try:
            context = {
                "signals": {
                    "gadeStatusValueState": self._resolve(self.eth_data, "gadeEvent", "gadeStatusValueState", "VALUE_STATE_VALID"),
                    "gadeStatus": self._resolve(self.eth_data, "gadeEvent", "gadeStatus", "GADESTATUS_MISSION_MODE_ON")
                }
            }

            os.makedirs(output_path, exist_ok=True)
            with open(Path(output_path) / "SignalValidation_Lib.cin", 'w') as f:
                f.write(self.env.get_template("signalValidationLib_template.j2").render(context))
            log.info("Signal Validation Library generated.")
        except Exception as e:
            log.error(f"Lib Gen failed: {e}")
            