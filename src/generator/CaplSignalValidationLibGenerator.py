import json
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from core.logger import log

class CaplSignalValidationLibGenerator:
    def __init__(self, json_path, template_dir):
        self.json_path = json_path
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def _resolve(self, signal_list, event, attribute, target_enum):
        # Search the JSON structure for the matching event and attribute
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
        try:
            with open(self.json_path, 'r') as f:
                data = json.load(f)
            
            s_list = data.get("SIGNAL_LIST", {})
            context = {
                "signals": {
                    "gadeStatusValueState": self._resolve(s_list, "gadeEvent", "gadeStatusValueState", "VALUE_STATE_VALID"),
                    "gadeStatus": self._resolve(s_list, "gadeEvent", "gadeStatus", "GADESTATUS_MISSION_MODE_ON")
                }
            }
            
            os.makedirs(output_path, exist_ok=True)
            with open(Path(output_path) / "SignalValidation_Lib.cin", 'w') as f:
                f.write(self.env.get_template("signalValidationLib_template.j2").render(context))
            log.info("Signal Validation Library generated.")
        except Exception as e:
            log.error(f"Lib Gen failed: {e}")