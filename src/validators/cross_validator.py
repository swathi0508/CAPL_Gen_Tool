import os
import math
import re
import pandas as pd
from core.logger import log

# Silence Pandas FutureWarnings regarding .replace() and .fillna() behavior
pd.set_option('future.no_silent_downcasting', True)

class CrossValidator:
    """Filters garbage enums, performs lexical validation, and computes strictly-typed limits."""
    
    # 'invalid' and 'failure' are kept for negative testing in CAPL
    INVALID_ENUM_KEYWORDS = ['unavailable', 'not_used', 'notused', 'unknown', 'null', 'sna', 'reserved']

    def __init__(self, can_db: dict, eth_db: dict):
        self.can_lookup = {str(k).lower(): v for k, v in can_db.items()}
        
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
            value = str(v).strip().lower()
            
            # FIXED: We use substring check (in) so that 'Unavailable_value' and 'Not_used_10' 
            # are caught by the 'unavailable' and 'not_used' keywords.
            if any(kw in value for kw in self.INVALID_ENUM_KEYWORDS):
                continue

            try:
                valid_enums[int(k)] = v
            except ValueError:
                pass
        return valid_enums

    def get_intersected_enum_keys(self, valid_c_enums: dict, valid_e_enums: dict) -> tuple[set, set]:
        """
        CROSS-MAP FIX & SMART TOKENIZER: 
        Strips AUTOSAR prefixes, ignores noise words ('REQUESTED'), and matches exact tokens 
        or semantic initials (e.g., recognizes that CAN 'P' matches ETH 'PARKING').
        Prevents false substring matches like 'L' matching 'NEUTRAL'.
        """
        matched_c_keys = set()
        matched_e_keys = set()
        
        def extract_core_meaning(s):
            s = str(s).upper()
            # Strip standard AUTOSAR SOME/IP prefixes to isolate the actual state
            if '_T_' in s:
                s = s.split('_T_')[-1]
            elif s.startswith('VALUE_STATE_'):
                s = s.replace('VALUE_STATE_', '')
            
            # Tokenize by splitting on non-alphanumeric characters
            tokens = [t for t in re.split(r'[^A-Z0-9]', s) if t]
            
            # Filter out generic noise words that cause false positive overlaps
            stop_words = {'REQUESTED', 'REQUEST', 'STATUS', 'STATE', 'VALUE', 'IS', 'THE'}
            filtered = [t for t in tokens if t not in stop_words]
            
            return filtered if filtered else tokens
            
        if valid_c_enums and valid_e_enums:
            for c_k, c_v in valid_c_enums.items():
                c_tokens = extract_core_meaning(c_v)
                for e_k, e_v in valid_e_enums.items():
                    e_tokens = extract_core_meaning(e_v)
                    
                    is_match = False
                    if not c_tokens or not e_tokens:
                        # Fallback to direct substring match if tokenization fails
                        c_clean = self.clean_string_for_match(c_v)
                        e_clean = self.clean_string_for_match(e_v)
                        if c_clean in e_clean or e_clean in c_clean:
                            is_match = True
                    else:
                        for ct in c_tokens:
                            for et in e_tokens:
                                # Handles exact token match OR Initial Abbreviation match (e.g. 'P' == 'PARKING')
                                if ct == et or (len(ct) == 1 and et.startswith(ct)) or (len(et) == 1 and ct.startswith(et)):
                                    is_match = True
                                    break
                            if is_match: break
                            
                    if is_match:
                        matched_c_keys.add(c_k)
                        matched_e_keys.add(e_k)
                        
        return matched_c_keys, matched_e_keys

    @staticmethod
    def compute_enum_stats(keys):
        """Accepts an iterable list/set of keys and returns Min, Mid, Max."""
        if not keys: return "N/A", "N/A", "N/A"
        sorted_keys = sorted(list(keys))
        return sorted_keys[0], sorted_keys[len(sorted_keys) // 2], sorted_keys[-1]

    @staticmethod
    def compute_phy_stats(min_val, max_val):
        try:
            min_f, max_f = float(min_val), float(max_val)
            
            c_min = int(math.ceil(min_f))
            c_mid = int(math.ceil((min_f + max_f) / 2.0))
            c_max = int(math.floor(max_f))

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
                if raw_can and raw_can != 'nan': 
                    can_sig = ("i" + raw_can).lower()
                raw_eth = str(row.get('ATTRIBUTE_VALUE', '')).strip().lower()
                if raw_eth and raw_eth != 'nan': eth_sig = raw_eth
            else:
                raw_eth = str(row.get('ATTRIBUTE_VALUE', '')).strip().lower()
                if raw_eth and raw_eth != 'nan': eth_sig = raw_eth
                raw_can = str(row.get('CAN_PORT', '')).strip().lower()
                if raw_can and raw_can != 'nan': 
                    can_sig = ("i" + raw_can).lower()

            # 2. Extract Valid Enums (Filters out garbage)
            valid_c_enums = {}
            if can_sig and can_sig in self.can_lookup:
                valid_c_enums = self.get_valid_enums(self.can_lookup[can_sig].get('Attributes', {}).get('Enums', {}))

            valid_e_enums = {}
            if eth_sig and eth_sig in self.eth_lookup:
                valid_e_enums = self.get_valid_enums(self.eth_lookup[eth_sig].get('Enums', {}))

            # 3. INTERSECT ENUMS (The Semantic Cross-Map Fix)
            matched_c_keys, matched_e_keys = self.get_intersected_enum_keys(valid_c_enums, valid_e_enums)
            
            # Record Lexical Match status
            if valid_c_enums and valid_e_enums:
                new_row['Enum_Lexical_Match'] = "MATCH" if matched_c_keys else "MISMATCH"
            else:
                new_row['Enum_Lexical_Match'] = "N/A"

            # 4. Compute CAN Data Output
            if can_sig and can_sig in self.can_lookup:
                c_data = self.can_lookup[can_sig]
                if valid_c_enums:
                    # SMART SUBSETTING: Use intersected keys if available, fallback to all valid
                    keys_to_use = matched_c_keys if matched_c_keys else valid_c_enums.keys()
                    e_min, e_mid, e_max = self.compute_enum_stats(keys_to_use)
                    new_row.update({'COMPUTED_CAN_ENUM_MIN': e_min, 'COMPUTED_CAN_ENUM_MID': e_mid, 'COMPUTED_CAN_ENUM_MAX': e_max})
                    
                    new_row.update({'COMPUTED_CAN_MIN_PHY': "N/A (Is Enum)", 'COMPUTED_CAN_MID_PHY': "N/A (Is Enum)", 'COMPUTED_CAN_MAX_PHY': "N/A (Is Enum)"})
                else:
                    for col in ['ENUM_MIN', 'ENUM_MID', 'ENUM_MAX']: new_row[f'COMPUTED_CAN_{col}'] = "N/A"
                    limits = c_data.get('Attributes', {}).get('Phys_Limits', {})
                    p_min, p_mid, p_max = self.compute_phy_stats(limits.get('Min'), limits.get('Max'))
                    new_row.update({'COMPUTED_CAN_MIN_PHY': p_min, 'COMPUTED_CAN_MID_PHY': p_mid, 'COMPUTED_CAN_MAX_PHY': p_max})
            else:
                for col in ['ENUM_MIN', 'ENUM_MID', 'ENUM_MAX', 'MIN_PHY', 'MID_PHY', 'MAX_PHY']:
                    new_row[f'COMPUTED_CAN_{col}'] = "N/A"

            # 5. Compute SOME/IP Data Output
            if eth_sig and eth_sig in self.eth_lookup:
                e_data = self.eth_lookup[eth_sig]
                if valid_e_enums:
                    # SMART SUBSETTING: Use intersected keys if available, fallback to all valid
                    keys_to_use = matched_e_keys if matched_e_keys else valid_e_enums.keys()
                    e_min, e_mid, e_max = self.compute_enum_stats(keys_to_use)
                    new_row.update({'COMPUTED_SOMEIP_ENUM_MIN': e_min, 'COMPUTED_SOMEIP_ENUM_MID': e_mid, 'COMPUTED_SOMEIP_ENUM_MAX': e_max})
                    
                    new_row.update({'COMPUTED_SOMEIP_MIN_PHY': "N/A (Is Enum)", 'COMPUTED_SOMEIP_MID_PHY': "N/A (Is Enum)", 'COMPUTED_SOMEIP_MAX_PHY': "N/A (Is Enum)"})
                else:
                    for col in ['ENUM_MIN', 'ENUM_MID', 'ENUM_MAX']: new_row[f'COMPUTED_SOMEIP_{col}'] = "N/A"
                    p_min, p_mid, p_max = self.compute_phy_stats(e_data.get('Min'), e_data.get('Max'))
                    new_row.update({'COMPUTED_SOMEIP_MIN_PHY': p_min, 'COMPUTED_SOMEIP_MID_PHY': p_mid, 'COMPUTED_SOMEIP_MAX_PHY': p_max})
            else:
                for col in ['ENUM_MIN', 'ENUM_MID', 'ENUM_MAX', 'MIN_PHY', 'MID_PHY', 'MAX_PHY']:
                    new_row[f'COMPUTED_SOMEIP_{col}'] = "N/A"

            # 3b. If SOME/IP PHY is blank/missing, fallback to CAN computed PHY values
            for suffix in ['MIN', 'MID', 'MAX']:
                someip_key = f'COMPUTED_SOMEIP_{suffix}_PHY'
                can_key = f'COMPUTED_CAN_{suffix}_PHY'
                someip_val = new_row.get(someip_key)
                if someip_val in [None, '', 'N/A'] and can_key in new_row:
                    new_row[someip_key] = new_row.get(can_key)

            updated_rows.append(new_row)

        df_final = pd.DataFrame(updated_rows)

        # FINAL STEP: Replace all empty cells, NaN, and None with "N/A" for a clean Excel sheet
        df_final = df_final.fillna("N/A")

        expected_computed_cols = [
            'COMPUTED_CAN_ENUM_MIN', 'COMPUTED_CAN_ENUM_MID', 'COMPUTED_CAN_ENUM_MAX',
            'COMPUTED_CAN_MIN_PHY', 'COMPUTED_CAN_MID_PHY', 'COMPUTED_CAN_MAX_PHY',
            'COMPUTED_SOMEIP_ENUM_MIN', 'COMPUTED_SOMEIP_ENUM_MID', 'COMPUTED_SOMEIP_ENUM_MAX',
            'COMPUTED_SOMEIP_MIN_PHY', 'COMPUTED_SOMEIP_MID_PHY', 'COMPUTED_SOMEIP_MAX_PHY'
        ]
        for col in expected_computed_cols:
            if col not in df_final.columns:
                df_final[col] = "N/A"

        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df_final.to_excel(writer, sheet_name=sheet_name, index=False)
            log.info(f"✅ Computations successfully saved to {sheet_name}")
        except Exception as e:
            log.error(f"Excel write failed: {e}")