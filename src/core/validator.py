from logger import log

class SignalValidator:
    """Quality gate for parsed signals."""
    
    @staticmethod
    def validate_signal(signal_data: dict) -> bool:
        """Ensures signal has required fields (e.g., length, data type)."""
        required_keys = {"name", "length", "type"}
        if not required_keys.issubset(signal_data.keys()):
            log.warning(f"Validation failed for signal: {signal_data.get('name', 'UNKNOWN')}")
            return False
        return True