import pandas as pd
from lxml import etree
import re
import os

def parse_arxml_with_enums(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        return pd.DataFrame()
        
    try:
        print(f"Parsing {file_path} (This might take a moment to build lookup tables)...")
        tree = etree.parse(file_path)
        root = tree.getroot()
    except etree.XMLSyntaxError as e:
        print(f"XML Parsing Error: {e}")
        return pd.DataFrame()

    # ==========================================
    # PRE-PROCESSING: Build Fast Lookup Dictionaries
    # ==========================================
    
    # 1. Extract all CompuMethods (The actual Enum dictionaries)
    compu_methods = {}
    for cm in root.xpath("//*[local-name()='COMPU-METHOD']"):
        cm_name_elem = cm.xpath("*[local-name()='SHORT-NAME']")
        if not cm_name_elem:
            continue
        cm_name = cm_name_elem[0].text.strip()
        
        enums = {}
        # Find all scale blocks which hold the value-to-text mapping
        for scale in cm.xpath(".//*[local-name()='COMPU-SCALE']"):
            lower_limit = scale.xpath("*[local-name()='LOWER-LIMIT']")
            vt = scale.xpath(".//*[local-name()='VT']") # VT holds the enum text
            
            if lower_limit and vt and lower_limit[0].text and vt[0].text:
                enums[lower_limit[0].text.strip()] = vt[0].text.strip()
                
        if enums:
            compu_methods[cm_name] = enums

    # 2. Extract Application Data Types to map them to CompuMethods
    app_to_compu = {}
    for app_dt in root.xpath("//*[local-name()='APPLICATION-PRIMITIVE-DATA-TYPE']"):
        app_name_elem = app_dt.xpath("*[local-name()='SHORT-NAME']")
        compu_ref = app_dt.xpath(".//*[local-name()='COMPU-METHOD-REF']")
        
        if app_name_elem and compu_ref and compu_ref[0].text:
            app_name = app_name_elem[0].text.strip()
            # Extract just the name from the path: "/DataTypes/CompuMethods/ValueState70" -> "ValueState70"
            ref_name = compu_ref[0].text.split("/")[-1].strip()
            app_to_compu[app_name] = ref_name

    # Helper function to format the dictionary into a readable string
    def get_enum_string(app_type_name):
        compu_name = app_to_compu.get(app_type_name)
        enum_dict = compu_methods.get(compu_name, {})
        if not enum_dict:
            return "No Enums"
        # Formats as: "0: INIT, 1: MISSION_MODE_ON"
        return " | ".join([f"{k}: {v}" for k, v in enum_dict.items()])

    # ==========================================
    # MAIN PARSING: Generate the DataFrame
    # ==========================================
    parsed_data = []

    for dtms in root.xpath("//*[local-name()='DATA-TYPE-MAPPING-SET']"):
        short_name_elem = dtms.xpath("*[local-name()='SHORT-NAME']")
        if not short_name_elem:
            continue
            
        short_name = short_name_elem[0].text.strip()
        
        match = re.search(r'^X(\d+)_(.*?)SvcProv', short_name)
        if not match:
            continue
            
        sif = match.group(1)
        raw_event_name = match.group(2)
        someip_event = f"SomeIp{raw_event_name}"
        
        valid_methods = []
        valuestate_app_name = None # Keep track of the specific ValueState name for enums
        
        # --- PASS 1: Categorize ---
        for dt_map in dtms.xpath(".//*[local-name()='DATA-TYPE-MAP']"):
            app_ref = dt_map.xpath("*[local-name()='APPLICATION-DATA-TYPE-REF']")
            
            if app_ref and app_ref[0].text:
                app_path_raw = app_ref[0].text.split("/")[-1].strip()
                
                # Check for ValueState placeholder
                if re.match(r'^ValueState\d*$', app_path_raw, re.IGNORECASE):
                    valuestate_app_name = app_path_raw # Save it (e.g., "ValueState84") to grab its enums later
                    continue 
                    
                # Store tuple of (Clean Method Name, Raw App Type Name for Enum lookup)
                clean_method = app_path_raw[:-1] if app_path_raw.endswith("T") else app_path_raw
                valid_methods.append((clean_method, app_path_raw))
        
        # --- PASS 2: Generate ---
        for clean_method, raw_app_name in valid_methods:
            
            # Base Signal
            base_enums = get_enum_string(raw_app_name)
            parsed_data.append({
                "Cluster": "EthernetCluster",
                "SIF": sif,
                "Event": someip_event,
                "Method": clean_method,
                "Signal_String": f'"EthernetCluster::sif_{sif}::{someip_event}::{clean_method}"',
                "Available_States": base_enums
            })
            
            # ValueState Signal Expansion
            if valuestate_app_name:
                vs_event = someip_event[:-1] if someip_event.endswith('s') else someip_event
                vs_method = f"{clean_method}ValueState"
                
                # Get enums specifically for the overarching ValueState (e.g., ValueState84)
                vs_enums = get_enum_string(valuestate_app_name)
                
                parsed_data.append({
                    "Cluster": "EthernetCluster",
                    "SIF": sif,
                    "Event": vs_event,
                    "Method": vs_method,
                    "Signal_String": f'"EthernetCluster::sif_{sif}::{vs_event}::{vs_method}"',
                    "Available_States": vs_enums
                })

    # ==========================================
    # DATAFRAME CONSTRUCTION
    # ==========================================
    df = pd.DataFrame(parsed_data)
    
    if not df.empty:
        df = df.sort_values(by=['SIF', 'Event', 'Method']).reset_index(drop=True)
        
    return df

if __name__ == "__main__":
    file_name = "ETH_CAN.arxml" 
    
    df_signals = parse_arxml_with_enums(file_name)
    
    if not df_signals.empty:
        print(f"Success! Extracted {len(df_signals)} signals with state definitions.\n")
        
        pd.set_option('display.max_columns', None)
        pd.set_option('display.max_colwidth', 50) # Truncate long strings just for terminal readability
        
        print(df_signals[['Method', 'Available_States']].head(15).to_string())
        
        # Dump to CSV so you can see the full strings without terminal truncation
        # df_signals.to_csv("signals_with_enums.csv", index=False)
        print("\nExported complete database to 'signals_with_enums.csv'")