import re
import ast
import difflib
import pandas as pd

class EnumResolver:
    """
    Generic boundary selection and lexical mapping engine.
    Ensures 'Perfect Logic' from CrossValidator is maintained across all protocols.
    """

    def resolve_enum_mapping(self, df: pd.DataFrame, sig1_col: str, sig2_col: str) -> pd.DataFrame:
        """Dual signal mapping: e.g., CAN_ENUM vs SOMEIP_FF_ENUM"""
        p1, p2 = sig1_col.replace('_ENUM', ''), sig2_col.replace('_ENUM', '')
        res_cols = [
            'ENUM_LEXICAL_MATCH',
            f'COMPUTED_{p1}_VALUE_MIN', f'COMPUTED_{p1}_VALUE_MID', f'COMPUTED_{p1}_VALUE_MAX',
            f'COMPUTED_{p2}_VALUE_MIN', f'COMPUTED_{p2}_VALUE_MID', f'COMPUTED_{p2}_VALUE_MAX'
        ]

        mask = df["IS_ENUM"] == True
        if mask.any():
            for col in res_cols:
                if col not in df.columns:
                    df[col] = "N/A"

            res = df.loc[mask].apply(
                lambda r: self._resolve_mapping_logic(r, p1, sig1_col, p2, sig2_col), 
                axis=1, result_type='expand'
            )
            df.loc[mask, res_cols] = res[res_cols].values
        return df

    def resolve_single_enum(self, df: pd.DataFrame, sig_enum_col: str) -> pd.DataFrame:
        """Single signal boundary extraction when mapping isn't possible."""
        prefix = sig_enum_col.replace('_ENUM', '')
        res_cols = [f'COMPUTED_{prefix}_VALUE_MIN', f'COMPUTED_{prefix}_VALUE_MID', f'COMPUTED_{prefix}_VALUE_MAX']

        mask = df["IS_ENUM"] == True
        if mask.any():
            for col in res_cols:
                if col not in df.columns:
                    df[col] = "N/A"

            res = df.loc[mask].apply(
                lambda r: self._resolve_single_row_logic(r, prefix, sig_enum_col), 
                axis=1, result_type='expand'
            )
            df.loc[mask, res_cols] = res[res_cols].values
        return df

    def _resolve_single_row_logic(self, row, prefix, col_name):
        raw_dict = self.extract_dict(row.get(col_name, {}))
        # Filter for forbidden keywords and ensure numeric keys
        filtered_keys = sorted(
            [str(k) for k, v in raw_dict.items() if not self.is_strictly_excluded(v) and str(k).lstrip('-').replace('.','',1).isdigit()],
            key=lambda x: int(float(x))
        )
        mi, md, mx = self._pick_boundaries_from_list(filtered_keys)
        return {
            f'COMPUTED_{prefix}_VALUE_MIN': mi,
            f'COMPUTED_{prefix}_VALUE_MID': md,
            f'COMPUTED_{prefix}_VALUE_MAX': mx
        }

    def _resolve_mapping_logic(self, row, p1, col1, p2, col2):
        d1 = self.extract_dict(row.get(col1, {}))
        d2 = self.extract_dict(row.get(col2, {}))
        
        f1 = {k: v for k, v in d1.items() if not self.is_strictly_excluded(v)}
        f2 = {k: v for k, v in d2.items() if not self.is_strictly_excluded(v)}

        lex_match = "MISMATCH"
        min1, mid1, max1 = self._get_keys_bounds(d1)
        min2, mid2, max2 = self._get_keys_bounds(d2)

        # 1. ATTEMPT MAPPING
        if f1 and f2:
            context = (str(row.get('SOMEIP_TOPIC_ATTRIBUTE', '')) + " " + 
                       " ".join(map(str, f1.values())) + " " + 
                       " ".join(map(str, f2.values()))).lower()
            
            is_gear = any(x in context for x in ['gear', 'lever', 'pnrdb'])
            is_binary = (len(f1) == 2 and len(f2) == 2)

            match_pool = []
            for id1, val1 in f1.items():
                for id2, val2 in f2.items():
                    score = self.calculate_priority_score(id1, id2, val1, val2, is_binary, is_gear)
                    match_pool.append({'id1': id1, 'id2': id2, 'score': score})

            match_pool.sort(key=lambda x: x['score'], reverse=True)
            
            final_map, used2 = {}, set()
            for m in match_pool:
                if m['id1'] not in final_map and m['id2'] not in used2:
                    if m['score'] > -5000:
                        final_map[m['id1']] = m['id2']
                        used2.add(m['id2'])

            sorted_f1_keys = sorted(f1.keys(), key=lambda x: int(float(x)))
            valid_results = [{'id1': k, 'id2': final_map[k]} for k in sorted_f1_keys if k in final_map]
            
            if len(valid_results) >= 2:
                min1, mid1, max1 = self._pick_boundaries_from_list([v['id1'] for v in valid_results])
                min2, mid2, max2 = self._pick_boundaries_from_list([v['id2'] for v in valid_results])
                lex_match = "MATCH"

        # 2. MISMATCH FALLBACK (Single Signal Logic)
        if lex_match == "MISMATCH":
            if f1 and not f2:
                b1 = self._resolve_single_row_logic(row, p1, col1)
                min1, mid1, max1 = b1[f'COMPUTED_{p1}_VALUE_MIN'], b1[f'COMPUTED_{p1}_VALUE_MID'], b1[f'COMPUTED_{p1}_VALUE_MAX']
                min2, mid2, max2 = min1, mid1, max1
            elif f2 and not f1:
                b2 = self._resolve_single_row_logic(row, p2, col2)
                min2, mid2, max2 = b2[f'COMPUTED_{p2}_VALUE_MIN'], b2[f'COMPUTED_{p2}_VALUE_MID'], b2[f'COMPUTED_{p2}_VALUE_MAX']
                min1, mid1, max1 = min2, mid2, max2

        res = {
            'ENUM_LEXICAL_MATCH': lex_match,
            f'COMPUTED_{p1}_VALUE_MIN': min1, f'COMPUTED_{p1}_VALUE_MID': mid1, f'COMPUTED_{p1}_VALUE_MAX': max1,
            f'COMPUTED_{p2}_VALUE_MIN': min2, f'COMPUTED_{p2}_VALUE_MID': mid2, f'COMPUTED_{p2}_VALUE_MAX': max2
        }

        # 3. CROSS-POLLINATION (Mirroring)
        for suf in ['MIN', 'MID', 'MAX']:
            k1, k2 = f'COMPUTED_{p1}_VALUE_{suf}', f'COMPUTED_{p2}_VALUE_{suf}'
            v1, v2 = str(res[k1]), str(res[k2])
            if v1 in ["N/A", "", "nan"] and v2 not in ["N/A", "", "nan"]: res[k1] = v2
            elif v2 in ["N/A", "", "nan"] and v1 not in ["N/A", "", "nan"]: res[k2] = v1

        return res

    def _pick_boundaries_from_list(self, items):
        """CRITICAL: Exact index selection rules from CrossValidator."""
        n = len(items)
        if n == 0: return "N/A", "N/A", "N/A"
        if n == 1: return items[0], items[0], items[0]
        if n == 2: return items[0], items[1], items[1] # Rule: mid == max
        
        # Rule: If n > 3, min is 1st index (index 1)
        idx_min = 1 if n > 3 else 0
        idx_mid = n // 2
        idx_max = n - 1
        return str(items[idx_min]), str(items[idx_mid]), str(items[idx_max])

    def calculate_priority_score(self, id1, id2, val1, val2, is_binary, is_gear):
        """THE CORE SCORING ENGINE (Tier 0-6)"""
        v1_raw, v2_raw = str(val1).lower(), str(val2).lower()
        v1_norm, v2_norm = self.normalize_strict(val1), self.normalize_strict(val2)
        index_bias = 50 if str(id1) == str(id2) else 0

        # Tier 0: Gear Lever
        if is_gear:
            gear_map = {'p': 'parking', 'r': 'reverse', 'n': 'neutral', 'd': 'drive', 'b': 'brake', 'm': 'manual'}
            for short, full in gear_map.items():
                if (re.search(rf'^{short}_|\b{short}\b', v1_raw) or full in v1_raw) and full in v2_raw:
                    return 70000 + index_bias

        # Tier 1: Numbers
        num_map = {'1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'}
        v1_ints = re.findall(r'\d+', v1_raw)
        if v1_ints:
            for digit in v1_ints:
                word = num_map.get(digit)
                if word and (f"_{word}" in v2_raw or f" {word}" in v2_raw or v2_raw.endswith(word)):
                    return 65000 + index_bias

        # Tier 2: Sequence Matcher & Directional Guard
        ratio = difflib.SequenceMatcher(None, v1_norm, v2_norm).ratio()
        c_dir = "b_to_m" if any(x in v1_raw for x in ["battery_to_motor", "battery_to_rear"]) else "m_to_b" if any(x in v1_raw for x in ["motor_to_battery", "rear_motor_to_battery"]) else "none"
        s_dir = "b_to_m" if "battery_to_motor" in v2_raw else "m_to_b" if "motor_to_battery" in v2_raw else "none"
        if c_dir != "none" and s_dir != "none" and c_dir != s_dir: return -10000

        if (ratio >= 0.90 or v1_norm in v2_norm or v2_norm in v1_norm):
            if self.get_polarity(val1) == self.get_polarity(val2):
                return 50000 + (ratio * 1000) + index_bias

        # Tier 3: Token Overlap
        v1_tokens = set(re.findall(r'\b\w{3,}\b', v1_raw.replace('_', ' ')))
        v2_tokens = set(re.findall(r'\b\w{3,}\b', v2_raw.replace('_', ' ')))
        common = v1_tokens.intersection(v2_tokens)
        if common and self.get_polarity(val1) == self.get_polarity(val2):
            return 40000 + (len(common) * 1000) + index_bias

        # Tier 6: Binary
        if is_binary and self.get_polarity(val1) == self.get_polarity(val2):
            return 10000 + index_bias

        if self.get_polarity(val1) != self.get_polarity(val2): return 0
        return (ratio * 100) + index_bias

    def normalize_strict(self, text):
        t = str(text).lower().replace('no_activated', 'not_activated').replace('noactivated', 'notactivated')
        return re.sub(r'[^a-z0-9]', '', t.replace('_', '').replace(' ', ''))

    def get_polarity(self, text):
        neg = {'no', 'not', 'false', 'off', 'incorrect', 'notactivated', 'disengaged', 'disabled', 'invalid', 'noalert', 'nodisplay'}
        text_clean = str(text).lower().replace('_', ' ')
        tokens = set(re.findall(r'\b\w+\b', text_clean))
        return "NEG" if any(word in tokens for word in neg) or 'not' in text_clean or 'no' in text_clean else "POS"

    def is_strictly_excluded(self, text):
        if not text: return True
        forbidden = ['unavailable', 'not_used', 'notused', 'reserved', 'unvailable', 'x__', 'unspecified', 'init']
        return any(sub in str(text).lower() for sub in forbidden)

    def extract_dict(self, data):
        if pd.isna(data) or str(data).strip() in ['N/A', '', 'nan', '{}']: return {}
        if isinstance(data, dict): return data
        content = str(data).strip()
        try:
            raw = ast.literal_eval(content) if content.startswith('{') else {'0': content}
            return {str(k): v for k, v in raw.items()}
        except: return {'0': str(content)}

    def _get_keys_bounds(self, d):
        keys = sorted([str(k) for k in d.keys() if str(k).lstrip('-').replace('.','',1).isdigit()], 
                      key=lambda x: int(float(x)))
        return self._pick_boundaries_from_list(keys)