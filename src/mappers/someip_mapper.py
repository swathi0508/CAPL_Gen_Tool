import re
import pandas as pd
from mappers.base_mapper import BaseMapper

class SomeIPMapper(BaseMapper):
    """Handles SOME/IP specific database lookups and sibling value state extraction."""
    
    def _load_database(self) -> dict:
        raw_db = super()._load_database()
        
        self.raw_db_values = []
        clean_db = {}
        
        for key, data in raw_db.items():
            # Inject the fully qualified database key directly into the data payload
            # so we can easily return the full path later for Jinja templates
            data["Signal_String"] = key
            self.raw_db_values.append(data)
            
            meth = str(data.get('Method', data.get('Attribute_Value', ''))).strip().lower()
            if meth:
                clean_db[meth] = data
                
        return clean_db

    def get_signal_data(self, attr_value: str, someip_port: str = None) -> dict:
        """Looks up a SOME/IP signal and finds its ValueState via specific fallback logic."""
        cols = [
            "SOMEIP_DB_SIGNAL_NAME", "SOMEIP_ENUM", "SOMEIP_MIN_PHY", 
            "SOMEIP_MAX_PHY", "SOMEIP_OFFSET", "SOMEIP_RESOLUTION",
            "SOMEIP_DB_SIGNAL_VALUESTATE"
        ]
        
        if pd.isna(attr_value) or str(attr_value).strip() == "":
            return {col: None for col in cols}

        attr_str = str(attr_value).strip()
        attr_lower = attr_str.lower()
        
        # Parse event name from SOMEIP_PORT (e.g., "SOMEIP_EventName" -> "EventName")
        target_event = ""
        if someip_port and "_" in str(someip_port):
            parts = str(someip_port).split("_")
            if len(parts) >= 2:
                target_event = parts[1].strip().lower()

        sig_data = None
        
        # 1. SMART SEARCH: Find the main signal based on Event + Attribute
        for data in self.raw_db_values:
            db_attr = str(data.get('Attribute_Value', '')).strip().lower()
            db_ev = str(data.get('Event', '')).strip().lower()
            
            if db_attr == attr_lower and (not target_event or target_event == db_ev):
                sig_data = data
                break
                    
        if not sig_data:
            return {col: "ETH_NOT_FOUND" for col in cols}

        # 2. VALUESTATE SEARCH (Hierarchical Fallback)
        vs_attr_full_path = None
        db_event_exact = sig_data.get("Event")
        
        # Check if the attribute itself is already a ValueState
        if "valuestate" in attr_lower:
            vs_attr_full_path = sig_data.get("Signal_String")
        elif db_event_exact:
            # Fallback Level 1 & 2 targets
            target_vs_append_1 = f"{attr_str}ValueState".lower()
            target_vs_append_2 = f"{attr_str}value_state".lower()
            
            # Level 3 fallback storage
            any_vs_in_event = None

            for data in self.raw_db_values:
                if data.get("Event") == db_event_exact:
                    curr_attr = str(data.get("Attribute_Value", "")).strip()
                    curr_attr_lower = curr_attr.lower()

                    # Fallback Level 1: attribute_value + ValueState
                    if curr_attr_lower == target_vs_append_1:
                        vs_attr_full_path = data.get("Signal_String")
                        break
                    
                    # Fallback Level 2: attribute_value + value_state
                    if not vs_attr_full_path and curr_attr_lower == target_vs_append_2:
                        vs_attr_full_path = data.get("Signal_String")

                    # Fallback Level 3: Any attribute containing "ValueState" in this event
                    if "valuestate" in curr_attr_lower:
                        any_vs_in_event = data.get("Signal_String")

            # Apply Level 3 if Level 1 & 2 failed
            if not vs_attr_full_path:
                vs_attr_full_path = any_vs_in_event

        # 3. Return the enriched payload
        return {
            "SOMEIP_DB_SIGNAL_NAME": sig_data.get("Signal_String"),
            "SOMEIP_ENUM": self.format_enum_to_string(sig_data.get("Enums", {})),
            "SOMEIP_MIN_PHY": sig_data.get("Min"),
            "SOMEIP_MAX_PHY": sig_data.get("Max"),
            "SOMEIP_OFFSET": sig_data.get("Offset"),
            "SOMEIP_RESOLUTION": sig_data.get("Resolution"),
            "SOMEIP_DB_SIGNAL_VALUESTATE": vs_attr_full_path
        }