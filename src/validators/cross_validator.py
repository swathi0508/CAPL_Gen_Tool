import os
import math
import re
import pandas as pd
from core.logger import log

class CrossValidator:
    """Filters garbage enums, performs lexical validation, and computes strictly-typed limits."""
    
    # 'invalid' and 'failure' are kept for negative testing in CAPL
    INVALID_ENUM_KEYWORDS = ['unavailable', 'not_used', 'notused', 'unknown', 'null', 'sna', 'reserved']

    def __init__(self, can_db: dict, eth_db: dict):
        self.can_lookup = {re.sub(r'^i', '', str(k).lower()): v for k, v in can_db.items()}
        
        self.eth_lookup = {}
        for sig_str, data in eth_db.items():
            meth = str(data.get('Method', data.get('Attribute_Value', ''))).strip().lower()
            if meth:
                self.eth_lookup[meth] = data

    @staticmethod
    def clean_string_for_match(s: str) -> str:
        return re.sub(r'_+', '', str(s)).lower()

    @staticmethod
    def parse_enum_data(raw_enum) -> dict:
        if isinstance(raw_enum, dict): return raw_enum
        enum_str = str(raw_enum).strip()
        if enum_str in ["", "Physical Value", "N/A", "{}"]: return {}
        
        parsed_dict = {}
        if enum_str.startswith('{') and enum_str.endswith('}'):
            try:
                import ast
                return ast.literal_eval(enum_str)
            except Exception: pass

        for p in enum_str.split('|'):
            if ':' in p:
                k, v = p.split(':', 1)
                parsed_dict[k.strip()] = v.strip()
        return parsed_dict

    def get_valid_enums(self, raw_enum_data) -> dict:
        enum_dict = self.parse_enum_data(raw_enum_data)
        valid_enums = {}
        for k, v in enum_dict.items():
            if not any(kw in str(v).lower() for kw in self.INVALID_ENUM_KEYWORDS):
                try: valid_enums[int(k)] = v
                except ValueError: pass
        return valid_enums

    @staticmethod
    def compute_enum_stats(valid_enums: dict):
        if not valid_enums: return "N/A", "N/A", "N/A"
        sorted_keys = sorted(valid_enums.keys())
        return sorted_keys[0], sorted_keys[len(sorted_keys) // 2], sorted_keys[-1]

    @staticmethod
    def compute_phy_stats(min_val, max_val):
        try:
            min_f, max_f = float(min_val), float(max_val)
            
            c_min = int(math.ceil(min_f))
            c_mid = int(math.ceil((min_f + max_f) / 2.0))
            c_max = int(math.floor(max_f))
            
            # Anti-False-Positive Logic: Shift 0 to 1
            c_min = 1 if c_min == 0 else c_min
            c_mid = 1 if c_mid == 0 else c_mid
            c_max = 1 if c_max == 0 else c_max

            return c_min, c_mid, c_max
        except (ValueError, TypeError):
            return "N/A", "N/A", "N/A"

    def process_sheet(self, excel_path: str, sheet_name: str, is_can_sheet: bool):
        log.info(f"Computing limits for: {sheet_name}")
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        except Exception as e:
            log.error(f"Failed to load {sheet_name}: {e}")
            return

        updated_rows = []

        for _, row in df.iterrows():
            new_row = row.to_dict()
            can_sig, eth_sig = None, None

            # 1. Safely grab lookup keys depending on the sheet topology
            if is_can_sheet:
                raw_can = str(row.get('CAN_PORT', '')).strip().lower() 
                if raw_can and raw_can != 'nan': can_sig = re.sub(r'^i', '', raw_can)
                raw_eth = str(row.get('ATTRIBUTE_VALUE', '')).strip().lower()
                if raw_eth and raw_eth != 'nan': eth_sig = raw_eth
            else:
                raw_eth = str(row.get('ATTRIBUTE_VALUE', '')).strip().lower()
                if raw_eth and raw_eth != 'nan': eth_sig = raw_eth
                raw_can = str(row.get('CAN_PORT', '')).strip().lower()
                if raw_can and raw_can != 'nan': can_sig = re.sub(r'^i', '', raw_can)

            # 2. Compute CAN Data (ALWAYS WRITTEN)
            valid_c_enums = {}
            if can_sig and can_sig in self.can_lookup:
                c_data = self.can_lookup[can_sig]
                valid_c_enums = self.get_valid_enums(c_data.get('Attributes', {}).get('Enums', {}))
                e_min, e_mid, e_max = self.compute_enum_stats(valid_c_enums)
                new_row.update({'computed_can_enum_min': e_min, 'computed_can_enum_mid': e_mid, 'computed_can_enum_max': e_max})
                
                if valid_c_enums:
                    new_row.update({'computed_can_min_phy': "N/A (Is Enum)", 'computed_can_mid_phy': "N/A (Is Enum)", 'computed_can_max_phy': "N/A (Is Enum)"})
                else:
                    limits = c_data.get('Attributes', {}).get('Phys_Limits', {})
                    p_min, p_mid, p_max = self.compute_phy_stats(limits.get('Min'), limits.get('Max'))
                    new_row.update({'computed_can_min_phy': p_min, 'computed_can_mid_phy': p_mid, 'computed_can_max_phy': p_max})
            else:
                for col in ['enum_min', 'enum_mid', 'enum_max', 'min_phy', 'mid_phy', 'max_phy']:
                    new_row[f'computed_can_{col}'] = "N/A"

            # 3. Compute SOME/IP Data (ALWAYS WRITTEN)
            valid_e_enums = {}
            if eth_sig and eth_sig in self.eth_lookup:
                e_data = self.eth_lookup[eth_sig]
                valid_e_enums = self.get_valid_enums(e_data.get('Enums', {}))
                e_min, e_mid, e_max = self.compute_enum_stats(valid_e_enums)
                new_row.update({'computed_someip_enum_min': e_min, 'computed_someip_enum_mid': e_mid, 'computed_someip_enum_max': e_max})
                
                if valid_e_enums:
                    new_row.update({'computed_someip_min_phy': "N/A (Is Enum)", 'computed_someip_mid_phy': "N/A (Is Enum)", 'computed_someip_max_phy': "N/A (Is Enum)"})
                else:
                    p_min, p_mid, p_max = self.compute_phy_stats(e_data.get('Min'), e_data.get('Max'))
                    new_row.update({'computed_someip_min_phy': p_min, 'computed_someip_mid_phy': p_mid, 'computed_someip_max_phy': p_max})
            else:
                for col in ['enum_min', 'enum_mid', 'enum_max', 'min_phy', 'mid_phy', 'max_phy']:
                    new_row[f'computed_someip_{col}'] = "N/A"

            # 4. Lexical Validation (ALWAYS WRITTEN)
            if valid_c_enums and valid_e_enums:
                c_strings = [self.clean_string_for_match(v) for v in valid_c_enums.values()]
                e_strings = [self.clean_string_for_match(v) for v in valid_e_enums.values()]
                new_row['Enum_Lexical_Match'] = "MATCH" if any(c in e for c in c_strings for e in e_strings) else "MISMATCH"
            else:
                new_row['Enum_Lexical_Match'] = "N/A"

            updated_rows.append(new_row)

        df_final = pd.DataFrame(updated_rows)

        # FINAL STEP: Replace all empty cells, NaN, and None with "N/A" for a clean Excel sheet
        df_final = df_final.fillna("N/A")

        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df_final.to_excel(writer, sheet_name=sheet_name, index=False)
            log.info(f"✅ Computations successfully saved to {sheet_name}")
        except Exception as e:
            log.error(f"Excel write failed: {e}")