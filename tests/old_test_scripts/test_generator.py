import os
from pathlib import Path

# Adjust imports based on your IDE/environment pathing
from core.logger import log
from generator.jinja_engine import JinjaEngine

def run_generator_test(excel_path: str, json_path: str, category: str, test_type: str, output_root: str):
    """Executes the CAPL Code Generation pipeline."""
    
    log.info("==================================================")
    log.info(f"⚙️ STARTING JINJA ENGINE TEST")
    log.info(f"   Target Category: {category}")
    log.info(f"   Target Type:     {test_type}")
    log.info("==================================================")

    if not os.path.exists(excel_path):
        log.error(f"❌ Input Excel not found: {excel_path}")
        log.error("Please run the 'test_pipeline.py' first to generate the Intermediate file.")
        return

    if not os.path.exists(json_path):
        log.error(f"❌ JSON cache not found: {json_path}")
        return

    try:
        # Initialize the Engine
        # The engine expects the output_root directory name (e.g., "Output_CAPL_Scripts")
        engine = JinjaEngine(output_root=output_root)
        
        # Run the generation pipeline
        engine.run(
            excel_path=excel_path, 
            json_path=json_path, 
            category=category, 
            test_type=test_type
        )
        
        log.info("==================================================")
        log.info(f"✅ GENERATION COMPLETE! Check the '{output_root}' folder.")
        log.info("==================================================")

    except Exception as e:
        log.exception(f"❌ Generator encountered a fatal error: {e}")

if __name__ == "__main__":
    # --- CONFIGURE YOUR LOCAL PATHS HERE ---
    # This should point to the output of your mapper/validator test
    INTERMEDIATE_EXCEL = r"./output/Requirements_Intermediate.xlsx" 
    
    # This JSON is needed for the SignalValidationLibGenerator
    SOMEIP_JSON_CACHE = r"someip_db_cache.json" 
    
    # The folder where the .cin and .can files will be dumped
    OUTPUT_DIRECTORY = "Output_CAPL_Scripts" 
    
    # Test Parameters
    TARGET_CATEGORY = "E2E_CAN"      # Tells the campaign generator which sheet to look at
    TARGET_TEST_TYPE = "CAN->SOMEIP" # Tells the engine which specific logic generator to trigger
    
    # Run the test
    run_generator_test(
        excel_path=INTERMEDIATE_EXCEL,
        json_path=SOMEIP_JSON_CACHE,
        category=TARGET_CATEGORY,
        test_type=TARGET_TEST_TYPE,
        output_root=OUTPUT_DIRECTORY
    )