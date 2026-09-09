import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> None:
        return None

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
CURRENTS_API_KEY = os.getenv("CURRENTS_API_KEY")

def get_api_key(provider: str) -> str:
    """Get API key for the given provider."""
    if provider == "finnhub":
        return FINNHUB_API_KEY
    elif provider == "alpha_vantage":
        return ALPHA_VANTAGE_API_KEY
    elif provider == "currents":
        return CURRENTS_API_KEY
    else:
        raise ValueError(f"Unknown provider: {provider}")