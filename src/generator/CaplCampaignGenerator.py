import pandas as pd
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from core.logger import log

pd.set_option('future.no_silent_downcasting', True)

class CaplCampaignGenerator:
    def __init__(self, template_dir):
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def generate(self, data_frames: dict, category: str, target_type: str, output_root: str):
        try:
            # 1. Format Strings for Filenames
            # Force everything to Upper, then specifically replace "_TO_" with "_to_"
            clean_category = category.upper().strip()
            # This ensures CAN->SOMEIP becomes CAN_to_SOMEIP
            clean_target_type = target_type.replace("->", "_to_").upper().replace("_TO_", "_to_").strip()
            
            target_sheet = f"{clean_category}_PARSED"
            
            # Find sheet case-insensitively
            sheet_name = next((s for s in data_frames.keys() if s.upper() == target_sheet.upper()), None)
            
            if not sheet_name:
                log.error(f"Campaign Gen: Sheet '{target_sheet}' not found in loaded data.")
                return
                
            df = data_frames[sheet_name].copy()
            df.columns = df.columns.str.strip()
            
            # Filter rows based on original target_type
            df['TEST_TYPE'] = df['TEST_TYPE'].astype(str).str.strip()
            df = df[df['TEST_TYPE'] == target_type].copy()
            
            if df.empty:
                log.warning(f"Campaign Gen: No rows found for {target_type} in {sheet_name}.")
                return

            # 2. Data Cleaning
            null_variations = ["", " ", "N/A", "n/a", "nan", "NaN", "None", "none", "NULL"]
            df.replace(null_variations, pd.NA, inplace=True)
            
            rows = df.fillna("MISSING_DATA").astype(str).to_dict(orient='records')
            
            # 3. Final Filename Construction
            # Result: E2E_CAN_CAN_to_SOMEIP_campaign.can
            file_name = f"{clean_category}_{clean_target_type}_campaign.can"
            
            target_dir = Path(output_root) / clean_category
            os.makedirs(target_dir, exist_ok=True)
            
            # 4. Render
            with open(target_dir / file_name, "w") as f:
                f.write(self.env.get_template("campaign_template.j2").render(
                    prefix=clean_category,
                    t_type=target_type,
                    rows=rows
                ))
                
            log.info(f"Campaign file generated: {file_name}")

        except Exception as e:
            log.error(f"Campaign Gen failed: {e}")