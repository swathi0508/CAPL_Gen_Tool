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
            target_sheet = f"{category}_PARSED"
            # Find sheet case-insensitively
            sheet_name = next((s for s in data_frames.keys() if s.upper() == target_sheet.upper()), None)
            
            if not sheet_name:
                log.error(f"Campaign Gen: Sheet '{target_sheet}' not found in loaded data.")
                return
                
            df = data_frames[sheet_name].copy()
            df.columns = df.columns.str.strip()
            df['TEST_TYPE'] = df['TEST_TYPE'].astype(str).str.strip()
            df = df[df['TEST_TYPE'] == target_type].copy()
            
            # Aggregate empty cell checks
            for col in df.columns:
                empty_mask = df[col].isna() | (df[col].astype(str).str.strip() == "") | (df[col] == "N/A")
                empty_count = empty_mask.sum()
                if empty_count > 0:
                    log.warning(f"Campaign Gen: Col '{col}' has {empty_count} missing cells in {sheet_name}. (Will trigger compile crash)")

            # Replace empty-like items with MISSING_DATA
            df.replace(["", "N/A", "nan", "None"], pd.NA, inplace=True)
            rows = df.fillna("MISSING_DATA").astype(str).to_dict(orient='records')
            
            target_dir = Path(output_root) / category
            os.makedirs(target_dir, exist_ok=True)
            
            with open(target_dir / f"{category}_campaign.can", "w") as f:
                f.write(self.env.get_template("campaign_template.j2").render(
                    prefix=category,
                    t_type=target_type,
                    rows=rows
                ))
            log.info(f"Campaign file generated for {category}.")
        except Exception as e:
            log.error(f"Campaign Gen failed: {e}")