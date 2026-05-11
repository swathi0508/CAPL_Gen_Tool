import os
import math
import re
import warnings
import pandas as pd
import difflib
import ast
from core.logger import log

# Suppress the warning natively without altering Pandas' internal data types
warnings.simplefilter(action='ignore', category=FutureWarning)

class CrossValidator:
    """Filters enums and performs mapping using the priority-score mapping engine strictly in RAM."""

    def __init__(self, can_db: dict, eth_db: dict):
        self.can_lookup = {str(k).lower(): v for k, v in can_db.items()}
        self.eth_lookup = {}
        for sig_str, data in eth_db.items():
            meth = str(data.get('Method', data.get('Attribute_Value', ''))).strip().lower()
            if meth:
                self.eth_lookup[meth] = data

    # --- START OF PERFECT MAPPING CORE LOGIC (FROM REMOTE) ---
    @staticmethod
    def normalize_strict(text):
        t = str(text).lower()
        t = t.replace('no_activated', 'not_activated').replace('noactivated', 'notactivated')
        t = t.replace('_', '').replace(' ', '')
        return re.sub(r'[^a-z0-9]', '', t)

    @staticmethod
    def is_strictly_excluded(text):
        if not text: return True
        text_clean = str(text).lower()
        # Merged forbidden list for maximum safety
        forbidden = ['unavailable', 'not_used', 'notused', 'reserved', 'unvailable', 'x__', 'unspecified', 'init']
        return any(sub in text_clean for sub in forbidden)

    @staticmethod
    def get_polarity(text):
        text_clean = str(text).lower().replace('_', ' ')
        neg_indicators = {'no', 'not', 'false', 'off', 'incorrect', 'notactivated', 'disengaged', 'disabled', 'invalid', 'noalert', 'nodisplay'}
        tokens = set(re.findall(r'\b\w+\b', text_clean))
        if any(word in tokens for word in neg_indicators) or 'not' in text_clean or 'no' in text_clean:
            return "NEG"
        return "POS"

    @staticmethod
    def calculate_priority_score(cid, sid, cval, sval, is_binary, is_gear_context):
        c_raw, s_raw = str(cval).lower(), str(sval).lower()
        c_norm, s_norm = CrossValidator.normalize_strict(cval), CrossValidator.normalize_strict(sval)
        index_bias = 50 if str(cid) == str(sid) else 0

        # 0. GEAR LEVER LOCK
        if is_gear_context:
            gear_map = {'p': 'parking', 'r': 'reverse', 'n': 'neutral', 'd': 'drive', 'b': 'brake', 'm': 'manual'}
            for short, full in gear_map.items():
                if (re.search(rf'^{short}_|\b{short}\b', c_raw) or full in c_raw) and full in s_raw:
                    return 70000 + index_bias

        # 1. HARD SEMANTIC NUMBER OVERRIDE
        num_map = {'1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'}
        c_ints = re.findall(r'\d+', c_raw)
        if c_ints:
            for digit in c_ints:
                word = num_map.get(digit)
                if word and (f"_{word}" in s_raw or f" {word}" in s_raw or s_raw.endswith(word)):
                    return 65000 + index_bias

        # 2. 90% SUBSTRING & DIRECTIONAL/STATE LOCK
        ratio = difflib.SequenceMatcher(None, c_norm, s_norm).ratio()
        c_dir = "b_to_m" if "battery_to_motor" in c_raw or "battery_to_rear" in c_raw else "m_to_b" if "motor_to_battery" in c_raw or "rear_motor_to_battery" in c_raw else "none"
        s_dir = "b_to_m" if "battery_to_motor" in s_raw else "m_to_b" if "motor_to_battery" in s_raw else "none"
        if c_dir != "none" and s_dir != "none" and c_dir != s_dir:
            return -10000 

        if ratio >= 0.90 or c_norm in s_norm or s_norm in c_norm:
            if CrossValidator.get_polarity(cval) == CrossValidator.get_polarity(sval):
                return 50000 + (ratio * 1000) + index_bias

        # 3. TOKEN OVERLAP
        c_tokens = set(re.findall(r'\b\w{3,}\b', c_raw.replace('_', ' ')))
        s_tokens = set(re.findall(r'\b\w{3,}\b', s_raw.replace('_', ' ')))
        common = c_tokens.intersection(s_tokens)
        if common and CrossValidator.get_polarity(cval) == CrossValidator.get_polarity(sval):
            return 40000 + (len(common) * 1000) + index_bias

        # 4. ORDINAL/LEVEL MATCH
        ord_map = {'1': 'level1', '2': 'level2', '3': 'level3'}
        if c_ints:
            for digit in c_ints:
                level = ord_map.get(digit)
                if level and level in s_norm:
                    return 35000 + index_bias

        # 5. INTEGER DIRECT MAPPING
        s_ints = re.findall(r'\d+', s_raw)
        if c_ints and s_ints and c_ints[0] == s_ints[0]:
            if any(x in c_raw for x in ["not_used", "reserved", "notused"]):
                return 0
            return 20000 + index_bias

        # 6. BINARY 1:1
        if is_binary and CrossValidator.get_polarity(cval) == CrossValidator.get_polarity(sval):
            return 10000 + index_bias

        if CrossValidator.get_polarity(cval) != CrossValidator.get_polarity(sval): return 0
        return (ratio * 100) + index_bias
    # --- END OF PERFECT MAPPING CORE LOGIC ---

    @staticmethod
    def extract_dict(data):
        if pd.isna(data) or str(data).strip() in ['N/A', '', 'nan', '{}']: 
            return {}
        content = str(data).strip()
        try:
            if content.startswith('{'): return ast.literal_eval(content)
            return {'0': content}
        except Exception: return {'0': content}

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

    def process_dataframe(self, df: pd.DataFrame, is_can_sheet: bool) -> pd.DataFrame:
        """Processes the logic purely in-memory for production-grade speed."""
        updated_rows = []

        for idx, row in df.iterrows():
            new_row = row.to_dict()
            
            try:
                can_sig, eth_sig = None, None
                row_upper = {str(k).strip().upper(): v for k, v in new_row.items()}

                if is_can_sheet:
                    raw_can = str(row_upper.get('CAN_PORT', '')).strip().lower() 
                    if raw_can and raw_can != 'nan': can_sig = ("i" + raw_can).lower()
                    raw_eth = str(row_upper.get('ATTRIBUTE_VALUE', '')).strip().lower()
                    if raw_eth and raw_eth != 'nan': eth_sig = raw_eth
                else:
                    raw_eth = str(row_upper.get('ATTRIBUTE_VALUE', '')).strip().lower()
                    if raw_eth and raw_eth != 'nan': eth_sig = raw_eth
                    raw_can = str(row_upper.get('CAN_PORT', '')).strip().lower()
                    if raw_can and raw_can != 'nan': can_sig = ("i" + raw_can).lower()

                # 1. Extract and Filter Enums
                can_raw_dict = {}
                if can_sig and can_sig in self.can_lookup:
                    can_raw_dict = self.extract_dict(self.can_lookup[can_sig].get('Attributes', {}).get('Enums', {}))
                
                sip_raw_dict = {}
                if eth_sig and eth_sig in self.eth_lookup:
                    sip_raw_dict = self.extract_dict(self.eth_lookup[eth_sig].get('Enums', {}))

                can_f = {k: v for k, v in can_raw_dict.items() if not self.is_strictly_excluded(v)}
                sip_f = {k: v for k, v in sip_raw_dict.items() if not self.is_strictly_excluded(v)}

                # --- NEW UNIFIED LOGIC ---
                is_enum = bool(can_f or sip_f)
                new_row['IS_ENUM'] = is_enum
                
                can_min, can_mid, can_max = "N/A", "N/A", "N/A"
                sip_min, sip_mid, sip_max = "N/A", "N/A", "N/A"

                # 2. Assign Enums if BOTH exist
                if can_f and sip_f:
                    context_str = (str(row_upper.get('SOMEIP_TOPIC_ATTRIBUTE', '')) + " " + " ".join(map(str, sip_f.values()))).lower()
                    is_gear = any(x in context_str for x in ['gear', 'lever', 'pnrdb'])
                    is_binary = (len(can_f) == 2 and len(sip_f) == 2)

                    match_pool = []
                    for cid, cval in can_f.items():
                        for sid, sval in sip_f.items():
                            score = self.calculate_priority_score(cid, sid, cval, sval, is_binary, is_gear)
                            match_pool.append({'cid': cid, 'sid': sid, 'score': score, 'sval': sval, 'cval': cval})

                    match_pool.sort(key=lambda x: x['score'], reverse=True)
                    final_mapping, used_sip = {}, set()
                    
                    for m in match_pool:
                        if m['cid'] not in final_mapping and m['sid'] not in used_sip:
                            if m['score'] > -5000:
                                final_mapping[m['cid']] = str(m['sid'])
                                used_sip.add(m['sid'])

                    valid_results = [{'c_id': str(cid), 's_id': final_mapping[cid]} for cid in can_f if cid in final_mapping]

                    n = len(valid_results)
                    if n >= 2:
                        idx_min, idx_mid, idx_max = (1 if n > 3 else 0), n // 2, n - 1
                        m_min, m_mid, m_max = valid_results[idx_min], valid_results[idx_mid], valid_results[idx_max]
                        can_min, can_mid, can_max = m_min['c_id'], m_mid['c_id'], m_max['c_id']
                        sip_min, sip_mid, sip_max = m_min['s_id'], m_mid['s_id'], m_max['s_id']

                    new_row['Enum_Lexical_Match'] = "MATCH" if final_mapping else "MISMATCH"
                else:
                    new_row['Enum_Lexical_Match'] = "N/A"

                # 3. Assign Physical Limits (Only computes if the specific signal is NOT an enum)
                if not can_f and can_sig and can_sig in self.can_lookup:
                    limits = self.can_lookup[can_sig].get('Attributes', {}).get('Phys_Limits', {})
                    can_min, can_mid, can_max = self.compute_phy_stats(limits.get('Min'), limits.get('Max'))

                if not sip_f and eth_sig and eth_sig in self.eth_lookup:
                    e_data = self.eth_lookup[eth_sig]
                    sip_min, sip_mid, sip_max = self.compute_phy_stats(e_data.get('Min'), e_data.get('Max'))

                # Flush unified values to the row
                new_row.update({
                    'COMPUTED_CAN_VALUE_MIN': can_min, 'COMPUTED_CAN_VALUE_MID': can_mid, 'COMPUTED_CAN_VALUE_MAX': can_max,
                    'COMPUTED_SOMEIP_VALUE_MIN': sip_min, 'COMPUTED_SOMEIP_VALUE_MID': sip_mid, 'COMPUTED_SOMEIP_VALUE_MAX': sip_max
                })

                # 4. Unified Cross-pollinate Fallbacks
                for suffix in ['MIN', 'MID', 'MAX']:
                    s_key = f'COMPUTED_SOMEIP_VALUE_{suffix}'
                    c_key = f'COMPUTED_CAN_VALUE_{suffix}'
                    
                    s_val = new_row.get(s_key)
                    if s_val in [None, '', 'N/A'] and new_row.get(c_key) not in [None, '', 'N/A']:
                        new_row[s_key] = new_row[c_key]
                            
            except Exception as e:
                log.debug(f"Row error safely bypassed: {e}")

            updated_rows.append(new_row)

        df_final = pd.DataFrame(updated_rows).fillna("N/A")

        # 5. Clean expected headers
        expected_computed_cols = [
            'IS_ENUM',
            'COMPUTED_CAN_VALUE_MIN', 'COMPUTED_CAN_VALUE_MID', 'COMPUTED_CAN_VALUE_MAX',
            'COMPUTED_SOMEIP_VALUE_MIN', 'COMPUTED_SOMEIP_VALUE_MID', 'COMPUTED_SOMEIP_VALUE_MAX'
        ]
        for col in expected_computed_cols:
            if col not in df_final.columns:
                df_final[col] = "N/A"

        return df_final