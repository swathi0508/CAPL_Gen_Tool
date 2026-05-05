import os
import math
import re
import warnings
import pandas as pd
from core.logger import log

# Suppress the warning natively without altering Pandas' internal data types
# This guarantees VS Code Excel Viewers can read the generated XML schema
warnings.simplefilter(action='ignore', category=FutureWarning)

class CrossValidator:
    """Filters garbage enums, performs lexical/semantic validation, and computes strictly-typed limits."""

    # Expanded to catch all edge cases like "Not_available__init_or_lever_switched_failure_"
    INVALID_ENUM_KEYWORDS = ['unavailable', 'not_used', 'notused', 'unknown', 'null', 'sna', 'reserved', 'not_available', 'notavailable']

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
            
            # Bulletproof substring check to catch fused garbage strings
            if any(kw in value for kw in self.INVALID_ENUM_KEYWORDS):
                continue

            try:
                valid_enums[int(k)] = v
            except ValueError:
                pass
        return valid_enums

    def get_intersected_enum_keys(self, valid_c_enums: dict, valid_e_enums: dict) -> tuple[set, set]:
        """
        SEMANTIC CROSS-MAP ENGINE:
        Wrapped in a try-except to guarantee it never crashes the pipeline.
        """
        try:
            matched_c_keys = set()
            matched_e_keys = set()
            
            GEAR_MAP = {'P': 'PARKING', 'R': 'REVERSE', 'N': 'NEUTRAL', 'D': 'DRIVE', 'B': 'BRAKE', 'M': 'MANUAL', 'L': 'LOW'}
            NEGATIONS = {'NO', 'NOT', 'OFF', 'DEACTIVATED', 'DISABLE', 'DISABLED', 'WITHOUT', 'NONE', 'FALSE', 'INCORRECT', 'INACTIVE', 'UNSPECIFIED'}
            POSITIVES = {'ON', 'ACTIVATED', 'ENABLE', 'ENABLED', 'WITH', 'TRUE', 'CORRECT', 'ACTIVE', 'ONGOING', 'AVAILABLE', 'REQUESTED', 'REQUEST'}
            SYNONYMS = {'LV': 'SPEED', 'LEVEL': 'SPEED', 'PROGRESS': 'ONGOING', 'REQ': 'REQUEST'}

            def extract_tokens(s):
                s = str(s).upper()
                s = s.replace('_T_', ' ')
                if s.startswith('VALUE_STATE_'): s = s.replace('VALUE_STATE_', ' ')
                s = s.replace('STATUS', ' ').replace('STATE', ' ')
                
                raw_tokens = [t for t in re.split(r'[^A-Z0-9]', s) if t]
                
                normalized_tokens = []
                for t in raw_tokens:
                    match = re.match(r'^([A-Z]+)(\d+)$', t)
                    if match:
                        alpha, num = match.groups()
                        alpha = SYNONYMS.get(alpha, alpha)
                        normalized_tokens.extend([alpha, num])
                    else:
                        normalized_tokens.append(SYNONYMS.get(t, t))
                        
                stop_words = {'IS', 'THE', 'OR', 'IN', 'TABLE', 'DESCRIPTION', 'ACTION'}
                filtered = [t for t in normalized_tokens if t not in stop_words]
                return filtered if filtered else normalized_tokens

            if valid_c_enums and valid_e_enums:
                for c_k, c_v in valid_c_enums.items():
                    c_tokens = extract_tokens(c_v)
                    c_is_negative = bool(set(c_tokens) & NEGATIONS)
                    c_is_positive = bool(set(c_tokens) & POSITIVES)
                    c_polarity = False if c_is_negative else (True if c_is_positive else None)
                    
                    c_digits = {t for t in c_tokens if t.isdigit()}
                    c_nouns = set(c_tokens) - NEGATIONS - POSITIVES

                    for e_k, e_v in valid_e_enums.items():
                        e_tokens = extract_tokens(e_v)
                        e_is_negative = bool(set(e_tokens) & NEGATIONS)
                        e_is_positive = bool(set(e_tokens) & POSITIVES)
                        e_polarity = False if e_is_negative else (True if e_is_positive else None)
                        
                        e_digits = {t for t in e_tokens if t.isdigit()}
                        e_nouns = set(e_tokens) - NEGATIONS - POSITIVES

                        # RULE 1: Polarity Clash
                        if (c_polarity is False and e_polarity is True) or (c_polarity is True and e_polarity is False):
                            continue
                        
                        is_match = False
                        
                        # RULE 2: Number Intersection
                        if c_digits and e_digits and (c_digits & e_digits):
                            is_match = True
                            
                        # RULE 3: Noun and Gear Overlap
                        if not is_match:
                            for ct in c_nouns:
                                for et in e_nouns:
                                    if ct == et:
                                        is_match = True
                                        break
                                    elif ct in GEAR_MAP and et.startswith(GEAR_MAP[ct]):
                                        is_match = True
                                        break
                                    elif et in GEAR_MAP and ct.startswith(GEAR_MAP[et]):
                                        is_match = True
                                        break
                                if is_match: break
                                
                        # RULE 4: Semantic Polarity Fallback
                        if not is_match and c_polarity == e_polarity and c_polarity is not None:
                            if not c_nouns or not e_nouns:
                                is_match = True

                        # RULE 5: Dumb Lexical Fallback (Prevents short 1/2-letter overlaps)
                        if not is_match and not c_polarity and not e_polarity:
                            c_clean = self.clean_string_for_match(c_v)
                            e_clean = self.clean_string_for_match(e_v)
                            if len(c_clean) > 2 and len(e_clean) > 2:
                                if c_clean in e_clean or e_clean in c_clean:
                                    is_match = True

                        if is_match:
                            matched_c_keys.add(c_k)
                            matched_e_keys.add(e_k)
                            
            return matched_c_keys, matched_e_keys
        
        except Exception as e:
            log.warning(f"Semantic matcher encountered an error ({e}). Falling back to standard bounds.")
            return set(valid_c_enums.keys()), set(valid_e_enums.keys())

    @staticmethod
    def compute_enum_stats(keys):
        """Accepts an iterable of keys (list/set)."""
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

        for idx, row in df.iterrows():
            new_row = row.to_dict()
            
            # ROW SAFETY WRAPPER: Guarantees the loop never breaks midway
            try:
                can_sig, eth_sig = None, None

                # OS-PROOF FIX: Convert all dictionary keys to strict UPPERCASE for safe extraction on Linux
                row_upper = {str(k).strip().upper(): v for k, v in new_row.items()}

                # 1. Safely grab lookup keys using row_upper
                if is_can_sheet:
                    raw_can = str(row_upper.get('CAN_PORT', '')).strip().lower() 
                    if raw_can and raw_can != 'nan': 
                        can_sig = ("i" + raw_can).lower()
                    raw_eth = str(row_upper.get('ATTRIBUTE_VALUE', '')).strip().lower()
                    if raw_eth and raw_eth != 'nan': eth_sig = raw_eth
                else:
                    raw_eth = str(row_upper.get('ATTRIBUTE_VALUE', '')).strip().lower()
                    if raw_eth and raw_eth != 'nan': eth_sig = raw_eth
                    raw_can = str(row_upper.get('CAN_PORT', '')).strip().lower()
                    if raw_can and raw_can != 'nan': 
                        can_sig = ("i" + raw_can).lower()

                # 2. Extract Valid Enums
                valid_c_enums = {}
                if can_sig and can_sig in self.can_lookup:
                    c_data = self.can_lookup[can_sig]
                    valid_c_enums = self.get_valid_enums(c_data.get('Attributes', {}).get('Enums', {}))

                valid_e_enums = {}
                if eth_sig and eth_sig in self.eth_lookup:
                    e_data = self.eth_lookup[eth_sig]
                    valid_e_enums = self.get_valid_enums(e_data.get('Enums', {}))

                # 3. INTERSECT ENUMS & RECORD MATCH
                matched_c_keys, matched_e_keys = self.get_intersected_enum_keys(valid_c_enums, valid_e_enums)
                
                if valid_c_enums and valid_e_enums:
                    new_row['Enum_Lexical_Match'] = "MATCH" if matched_c_keys else "MISMATCH"
                else:
                    new_row['Enum_Lexical_Match'] = "N/A"

                # 4. Populate CAN Columns
                if can_sig and can_sig in self.can_lookup:
                    if valid_c_enums:
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

                # 5. Populate SOME/IP Columns
                if eth_sig and eth_sig in self.eth_lookup:
                    if valid_e_enums:
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

                # 6. Fallback logic: If SOME/IP PHY is blank/missing, fallback to CAN computed PHY values
                for suffix in ['MIN', 'MID', 'MAX']:
                    someip_key = f'COMPUTED_SOMEIP_{suffix}_PHY'
                    can_key = f'COMPUTED_CAN_{suffix}_PHY'
                    someip_val = new_row.get(someip_key)
                    if someip_val in [None, '', 'N/A'] and can_key in new_row:
                        new_row[someip_key] = new_row.get(can_key)
                        
                # 7. Fallback logic: If SOME/IP ENUM is blank/missing, fallback to CAN computed ENUM values
                for suffix in ['MIN', 'MID', 'MAX']:
                    someip_key = f'COMPUTED_SOMEIP_ENUM_{suffix}'
                    can_key = f'COMPUTED_CAN_ENUM_{suffix}'
                    someip_val = new_row.get(someip_key)
                    if someip_val in [None, '', 'N/A'] and can_key in new_row:
                        new_row[someip_key] = new_row.get(can_key)
                        
            except Exception as e:
                log.error(f"Critical computation error on Row {idx+2} in {sheet_name}: {e}")

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