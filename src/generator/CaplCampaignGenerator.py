import pandas as pd
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from core.logger import log

class CaplCampaignGenerator:
    def __init__(self, excel_path, template_dir):
        self.excel_path = excel_path
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def generate(self, category, target_type, output_root):
        try:
            xls = pd.ExcelFile(self.excel_path)
            sheet_name = next((s for s in xls.sheet_names if s.upper() == f"{category}_intermediate".upper()), None)
            if not sheet_name:
                log.error(f"Campaign Gen: Sheet {category}_intermediate not found.")
                return

            df = pd.read_excel(xls, sheet_name=sheet_name)
            df.columns = df.columns.str.strip()
            df['TEST_TYPE'] = df['TEST_TYPE'].astype(str).str.strip()
            df = df[df['TEST_TYPE'] == target_type].copy()

            # Identify if ID column exists based on the prefix (e.g., E2E_CAN_REQ_ID)
            req_col = f"{category}_REQ_ID"
            
            # Global check for empty cells in all columns
            for col in df.columns:
                null_indices = df[df[col].isna()].index.tolist()
                for idx in null_indices:
                    log.error(f"Campaign Gen: Row {idx+2} | Col '{col}' is EMPTY in {sheet_name}")

            # Prepare data
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