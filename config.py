"""
🔧 Configuration settings for Binance trading bot
Contains all bot settings and trading parameters
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables at module level
load_dotenv()

@dataclass
class TradingConfig:
    """Trading configuration parameters"""
    timeframe: str = "1h"
    min_balance_usdt: float = 25.0
    leverage: int = 10
    margin_per_trade_usdt: float = 25.0
    min_volume_usdt: float = 10_000_000.0  # 10M USDT minimum volume
    dynamic_coin_discovery: bool = True
    force_buy: bool = False
    force_sell: bool = False
    deepseek_enabled: bool = True
    ai_model: str = "deepseek-chat"  # AI model name for triangle analysis

    def to_dict(self) -> dict:
        """Convert config to dictionary for JSON serialization"""
        return {
            "timeframe": self.timeframe,
            "min_balance_usdt": self.min_balance_usdt,
            "leverage": self.leverage,
            "margin_per_trade_usdt": self.margin_per_trade_usdt,
            "min_volume_usdt": self.min_volume_usdt,
            "dynamic_coin_discovery": self.dynamic_coin_discovery,
            "force_buy": self.force_buy,
            "force_sell": self.force_sell,
            "deepseek_enabled": self.deepseek_enabled,
            "ai_model": self.ai_model,
        }

class APIConfig:
    """API configuration"""
    def __init__(self):
        # Load environment variables
        self.binance_api_key = os.getenv("BINANCE_API_KEY")
        self.binance_secret = os.getenv("BINANCE_SECRET_KEY")  # แก้ชื่อตัวแปร
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        
        # Check if credentials are available (don't raise error - let main handle it)
        self.has_binance_credentials = bool(self.binance_api_key and self.binance_secret)
        self.has_deepseek_credentials = bool(self.deepseek_api_key)
        
        # Print debug info
        print(f"Debug: Binance API Key: {'✅' if self.binance_api_key else '❌'}")
        print(f"Debug: Binance Secret: {'✅' if self.binance_secret else '❌'}")
        print(f"Debug: DeepSeek API Key: {'✅' if self.deepseek_api_key else '❌'}")
        
        if not self.has_binance_credentials:
            raise ValueError("Missing Binance API credentials in environment variables")
        if not self.has_deepseek_credentials:
            raise ValueError("Missing DeepSeek API key in environment variables")

# Global configuration instances
cfg = TradingConfig()

# Initialize API config but don't validate credentials here
try:
    api_cfg = APIConfig()
except Exception as e:
    print(f"Warning: Could not load API configuration: {e}")
    api_cfg = None
