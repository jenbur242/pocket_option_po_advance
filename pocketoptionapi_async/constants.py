"""
Constants and configuration for the PocketOption API
"""

from typing import Dict, List
import random

# Asset mappings with their corresponding IDs - Corrected API format
ASSETS: Dict[str, int] = {
    # OTC Currency Pairs
    "AEDCNY_otc": 1,
    "AUDCAD_otc": 2,
    "AUDCHF_otc": 3,
    "AUDJPY_otc": 4,
    "AUDNZD_otc": 5,
    "AUDUSD_otc": 6,
    "BHDCNY_otc": 7,
    "CADCHF_otc": 8,
    "CADJPY_otc": 9,
    "CHFJPY_otc": 10,
    "CHFNOK_otc": 11,
    "EURCHF_otc": 12,
    "EURGBP_otc": 13,
    "EURHUF_otc": 14,
    "EURJPY_otc": 15,
    "EURNZD_otc": 16,
    "EURRUB_otc": 55,
    "EURTRY_otc": 17,
    "EURUSD_otc": 18,
    "GBPAUD_otc": 19,
    "GBPJPY_otc": 20,
    "GBPUSD_otc": 21,
    "JODCNY_otc": 22,
    "KESUSD_otc": 23,
    "LBPUSD_otc": 24,
    "MADUSD_otc": 25,
    "NGNUSD_otc": 26,
    "NZDJPY_otc": 27,
    "NZDUSD_otc": 28,
    "OMRCNY_otc": 29,
    "QARCNY_otc": 30,
    "SARCNY_otc": 31,
    "TNDUSD_otc": 32,
    "UAHUSD_otc": 33,
    "USDARS_otc": 34,
    "USDBDT_otc": 35,
    "USDBRL_otc": 36,
    "USDCAD_otc": 37,
    "USDCHF_otc": 38,
    "USDCLP_otc": 39,
    "USDCNH_otc": 40,
    "USDCOP_otc": 41,
    "USDDZD_otc": 42,
    "USDEGP_otc": 43,
    "USDIDR_otc": 44,
    "USDINR_otc": 45,
    "USDJPY_otc": 46,
    "USDMXN_otc": 47,
    "USDMYR_otc": 48,
    "USDPHP_otc": 49,
    "USDPKR_otc": 50,
    "USDRUB_otc": 51,
    "USDSGD_otc": 52,
    "USDTHB_otc": 53,
    "USDVND_otc": 56,
    "YERUSD_otc": 57,
    "ZARUSD_otc": 54,

    # Regular Currency Pairs (Non-OTC)
    "AUDCAD": 58,
    "AUDCHF": 59,
    "AUDJPY": 60,
    "AUDUSD": 61,
    "CADCHF": 62,
    "CADJPY": 63,
    "CHFJPY": 64,
    "EURAUD": 65,
    "EURCAD": 66,
    "EURCHF": 67,
    "EURGBP": 68,
    "EURJPY": 69,
    "EURUSD": 70,
    "GBPAUD": 71,
    "GBPCAD": 72,
    "GBPCHF": 73,
    "GBPJPY": 74,
    "GBPUSD": 75,
    "USDCAD": 76,
    "USDCHF": 77,
    "USDJPY": 78,
}


# WebSocket regions with their URLs
class Regions:
    """WebSocket region endpoints"""

    _REGIONS = {
        "EUROPA": "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "SEYCHELLES": "wss://api-sc.po.market/socket.io/?EIO=4&transport=websocket",
        "HONGKONG": "wss://api-hk.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER1": "wss://api-spb.po.market/socket.io/?EIO=4&transport=websocket",
        "FRANCE2": "wss://api-fr2.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES4": "wss://api-us4.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES3": "wss://api-us3.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES2": "wss://api-us2.po.market/socket.io/?EIO=4&transport=websocket",
        "DEMO": "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "DEMO_2": "wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES": "wss://api-us-north.po.market/socket.io/?EIO=4&transport=websocket",
        "RUSSIA": "wss://api-msk.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER2": "wss://api-l.po.market/socket.io/?EIO=4&transport=websocket",
        "INDIA": "wss://api-in.po.market/socket.io/?EIO=4&transport=websocket",
        "FRANCE": "wss://api-fr.po.market/socket.io/?EIO=4&transport=websocket",
        "FINLAND": "wss://api-fin.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER3": "wss://api-c.po.market/socket.io/?EIO=4&transport=websocket",
        "ASIA": "wss://api-asia.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER4": "wss://api-us-south.po.market/socket.io/?EIO=4&transport=websocket",
    }

    @classmethod
    def get_all(cls, randomize: bool = True) -> List[str]:
        """Get all region URLs"""
        urls = list(cls._REGIONS.values())
        if randomize:
            random.shuffle(urls)
        return urls

    @classmethod
    def get_all_regions(cls) -> Dict[str, str]:
        """Get all regions as a dictionary"""
        return cls._REGIONS.copy()

    from typing import Optional

    @classmethod
    def get_region(cls, region_name: str) -> Optional[str]:
        """Get specific region URL"""
        return cls._REGIONS.get(region_name.upper())

    @classmethod
    def get_demo_regions(cls) -> List[str]:
        """Get demo region URLs"""
        return [url for name, url in cls._REGIONS.items() if "DEMO" in name]


# Global constants
REGIONS = Regions()

# Timeframes (in seconds)
TIMEFRAMES = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}

# Connection settings
CONNECTION_SETTINGS = {
    "ping_interval": 20,  # seconds
    "ping_timeout": 10,  # seconds
    "close_timeout": 10,  # seconds
    "max_reconnect_attempts": 5,
    "reconnect_delay": 5,  # seconds
    "message_timeout": 30,  # seconds
}

# API Limits
API_LIMITS = {
    "min_order_amount": 1.0,
    "max_order_amount": 50000.0,
    "min_duration": 5,  # seconds
    "max_duration": 43200,  # 12 hours in seconds
    "max_concurrent_orders": 10,
    "rate_limit": 100,  # requests per minute
}

# Default headers
DEFAULT_HEADERS = {
    "Origin": "https://pocketoption.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}