from pathlib import Path
from lxml import etree
from loguru import logger
from pydantic import BaseModel, Field

# --- Pydantic Models for the Application Layer ---

class SignalDef(BaseModel):
    """Represents a single Event or Method under an Interface."""
    name: str
    signal_type: str  # 'Event' (Variable Data) or 'Method' (Operation)

class InterfaceDef(BaseModel):
    """Represents the Software Interface containing multiple signals."""
    name: str
    interface_type: str # 'SENDER-RECEIVER' or 'CLIENT-SERVER'
    signals: list[SignalDef] = Field(default_factory=list)

# --- Parser Logic ---

def get_signals_for_interface(arxml_path: str | Path, interface_name: str) -> InterfaceDef | None:
    """
    Searches the ARXML for a specific Interface and returns all its signals.
    Handles both Sender-Receiver (Events) and Client-Server (Methods).
    """
    ns = {'ar': 'http://autosar.org/schema/r4.0'}
    
    try:
        tree = etree.parse(str(arxml_path))
        root = tree.getroot()
    except Exception as e:
        logger.error(f"Failed to load ARXML: {e}")
        return None

    logger.info(f"Searching for Interface: '{interface_name}'")

    # 1. Look for a Sender-Receiver Interface (Used for SOME/IP Events)
    sr_xpath = f".//ar:SENDER-RECEIVER-INTERFACE[ar:SHORT-NAME='{interface_name}']"
    sr_nodes = root.xpath(sr_xpath, namespaces=ns)
    
    if sr_nodes:
        return _extract_sender_receiver(sr_nodes[0], interface_name, ns)

    # 2. Look for a Client-Server Interface (Used for SOME/IP Methods)
    cs_xpath = f".//ar:CLIENT-SERVER-INTERFACE[ar:SHORT-NAME='{interface_name}']"
    cs_nodes = root.xpath(cs_xpath, namespaces=ns)
    
    if cs_nodes:
        return _extract_client_server(cs_nodes[0], interface_name, ns)

    logger.warning(f"Interface '{interface_name}' not found as SENDER-RECEIVER or CLIENT-SERVER.")
    return None

def _extract_sender_receiver(node: etree._Element, name: str, ns: dict) -> InterfaceDef:
    """Extracts Events (Variable Data Prototypes) from a Sender-Receiver Interface."""
    logger.success(f"Found SENDER-RECEIVER-INTERFACE: {name}")
    
    interface_def = InterfaceDef(name=name, interface_type="SENDER-RECEIVER")
    
    # In ARXML, events are stored under DATA-ELEMENTS as VARIABLE-DATA-PROTOTYPE
    data_elements = node.xpath(".//ar:DATA-ELEMENTS/ar:VARIABLE-DATA-PROTOTYPE", namespaces=ns)
    
    for element in data_elements:
        short_name_node = element.xpath("./ar:SHORT-NAME", namespaces=ns)
        if short_name_node:
            signal_name = short_name_node[0].text
            interface_def.signals.append(SignalDef(name=signal_name, signal_type="Event"))
            
    return interface_def

def _extract_client_server(node: etree._Element, name: str, ns: dict) -> InterfaceDef:
    """Extracts Methods (Operations) from a Client-Server Interface."""
    logger.success(f"Found CLIENT-SERVER-INTERFACE: {name}")
    
    interface_def = InterfaceDef(name=name, interface_type="CLIENT-SERVER")
    
    # In ARXML, methods are stored under OPERATIONS as CLIENT-SERVER-OPERATION
    operations = node.xpath(".//ar:OPERATIONS/ar:CLIENT-SERVER-OPERATION", namespaces=ns)
    
    for op in operations:
        short_name_node = op.xpath("./ar:SHORT-NAME", namespaces=ns)
        if short_name_node:
            signal_name = short_name_node[0].text
            interface_def.signals.append(SignalDef(name=signal_name, signal_type="Method"))
            
    return interface_def


# --- Execution Example ---
if __name__ == "__main__":
    arxml_file = "ETH_CAN.arxml"
    
    # Testing with the interface name from your Notepad++ output
    target_interface = "SomeIpproducerLoadEventInterface"
    
    result = get_signals_for_interface(arxml_file, target_interface)
    if result:
        print(result.model_dump_json(indent=2))