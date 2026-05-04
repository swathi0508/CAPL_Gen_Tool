import re
import pandas as pd
from .base_mapper import BaseMapper

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

    def get_signal_data(self, attr_value: str, event_name: str = None) -> dict:
        """Looks up a SOME/IP signal and dynamically finds its sibling ValueState."""
        cols = [
            "SOMEIP_DB_SIGNAL_NAME", "SOMEIP_ENUM", "SOMEIP_MIN_PHY", 
            "SOMEIP_MAX_PHY", "SOMEIP_OFFSET", "SOMEIP_RESOLUTION",
            "SOMEIP_DB_SIGNAL_VALUESTATE"
        ]
        
        if pd.isna(attr_value) or str(attr_value).strip() == "":
            return {col: None for col in cols}

        attr_lower = str(attr_value).strip().lower()
        ev_lower = str(event_name).strip().lower() if event_name else ""
        ev_lower = re.sub(r'^someip', '', ev_lower)

        sig_data = None
        
        # 1. SMART SEARCH: Find exact match using both Event + Attribute
        for data in self.raw_db_values:
            db_attr = str(data.get('Method', data.get('Attribute_Value', ''))).strip().lower()
            if db_attr == attr_lower:
                db_ev = str(data.get('Event', '')).strip().lower()
                db_ev = re.sub(r'^someip', '', db_ev)
                
                if ev_lower and ev_lower in db_ev:
                    sig_data = data
                    break
                elif not sig_data:
                    sig_data = data 
                    
        if not sig_data:
            return {col: "ETH_NOT_FOUND" for col in cols}

        # 2. SIBLING SEARCH: Find the ValueState corresponding to this exact event+attribute
        vs_attr_full_path = None
        db_event_exact = sig_data.get("Event")
        db_attr_exact = sig_data.get("Attribute_Value", "")
        db_sif = sig_data.get("SIF")  # Extract SIF for final fallback
        
        if db_event_exact:
            # Search for ANY valuestate in the same event
            for data in self.raw_db_values:
                if data.get("Event") == db_event_exact:
                    sibling_attr = data.get("Attribute_Value", "")
                    if "valuestate" in sibling_attr.lower():
                        vs_attr_full_path = data.get("Signal_String")
                        break


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