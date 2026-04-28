import pandas as pd
from lxml import etree
import re
import os

def parse_arxml_signals_to_df(file_path):
    # 1. Safely load the ARXML file
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        return pd.DataFrame()
        
    try:
        print(f"Parsing {file_path}...")
        tree = etree.parse(file_path)
        root = tree.getroot()
    except etree.XMLSyntaxError as e:
        print(f"XML Parsing Error: {e}")
        return pd.DataFrame()

    parsed_data = []

    # 2. Find all mapping blocks using namespace-agnostic XPath
    for dtms in root.xpath("//*[local-name()='DATA-TYPE-MAPPING-SET']"):
        short_name_elem = dtms.xpath("*[local-name()='SHORT-NAME']")
        if not short_name_elem:
            continue
            
        short_name = short_name_elem[0].text.strip()
        
        # Extract SIF and Event Name
        match = re.search(r'^X(\d+)_(.*?)SvcProv', short_name)
        if not match:
            continue
            
        sif = match.group(1)
        raw_event_name = match.group(2)
        someip_event = f"SomeIp{raw_event_name}"
        
        valid_methods = []
        has_valuestate = False
        
        # --- PASS 1: Scan for ValueState placeholders and clean method names ---
        for dt_map in dtms.xpath(".//*[local-name()='DATA-TYPE-MAP']"):
            app_ref = dt_map.xpath("*[local-name()='APPLICATION-DATA-TYPE-REF']")
            
            if app_ref and app_ref[0].text:
                method_raw = app_ref[0].text.split("/")[-1].strip()
                
                # Corner Case 1: Detect and swallow ValueState placeholders (e.g., ValueState70)
                if re.match(r'^ValueState\d*$', method_raw, re.IGNORECASE):
                    has_valuestate = True
                    continue # Skip adding this as a standalone method
                    
                # Clean method name: Strip trailing 'T'
                method_name = method_raw[:-1] if method_raw.endswith("T") else method_raw
                valid_methods.append(method_name)
        
        # --- PASS 2: Generate the final signals ---
        for method in valid_methods:
            
            # Base Signal (Standard generation)
            parsed_data.append({
                "Cluster": "EthernetCluster",
                "SIF": sif,
                "Event": someip_event,
                "Method": method,
                "Signal_String": f'"EthernetCluster::sif_{sif}::{someip_event}::{method}"'
            })
            
            # Corner Case 2: Expand ValueState signals across all methods in the block
            if has_valuestate:
                # Fix grammar: Drop trailing 's' if it exists (States -> State)
                vs_event = someip_event[:-1] if someip_event.endswith('s') else someip_event
                vs_method = f"{method}ValueState"
                
                parsed_data.append({
                    "Cluster": "EthernetCluster",
                    "SIF": sif,
                    "Event": vs_event,
                    "Method": vs_method,
                    "Signal_String": f'"EthernetCluster::sif_{sif}::{vs_event}::{vs_method}"'
                })

    # 3. Convert to Pandas DataFrame
    df = pd.DataFrame(parsed_data)
    
    # Sort the data so Base signals and their ValueStates appear sequentially
    if not df.empty:
        df = df.sort_values(by=['SIF', 'Event', 'Method']).reset_index(drop=True)
        
    return df

# --- Execution ---
if __name__ == "__main__":
    # Update this path to point to your actual local ARXML file
    file_name = "ETH_CAN.arxml" 
    
    df_signals = parse_arxml_signals_to_df(file_name)
    
    if not df_signals.empty:
        print(f"Success! Extracted {len(df_signals)} total signals.\n")
        
        # Adjust display settings to prevent pandas from truncating the long Signal Strings
        pd.set_option('display.max_columns', None)
        pd.set_option('display.max_colwidth', None)
        
        print("--- DataFrame Preview ---")
        print(df_signals.head(20).to_string())

        # uncomment to print all signals under 591 
        print(df_signals[df_signals['SIF'] == '591'])
        
        # OPTIONAL: Save the DataFrame to a CSV or Excel file for external analytics
        # df_signals.to_csv("parsed_signals.csv", index=False)
        # df_signals.to_excel("parsed_signals.xlsx", index=False)
        
        # Save to CSV for your downstream analytics
        # df_signals.to_csv("parsed_ethernet_signals.csv", index=False)
        # print("\nData exported to 'parsed_ethernet_signals.csv'")
    else:
        print("No signals extracted. Please verify the file path and ARXML structure.")