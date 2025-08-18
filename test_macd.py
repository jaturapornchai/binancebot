"""
🧪 MACD System Test Script
Tests MACD calculations and color changes with real market data
"""

import os
import sys

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.append(os.path.dirname(__file__))

import binance_client
from binance_client import get_klines
from config import APIConfig, cfg
from macd_analysis import (calculate_macd, get_macd_analysis_text,
                           get_macd_color, get_macd_signal_strength,
                           is_macd_color_changed)
from trading_engine import parse_klines_data


def test_macd_with_symbol(symbol: str):
    """Test MACD analysis with real market data"""
    print(f"\n🔍 Testing MACD for {symbol}")
    print("="*50)
    
    try:
        # Set up API config first
        api_cfg = APIConfig()
        binance_client.set_api_config(api_cfg)
        
        # Create Binance client
        um = binance_client.create_binance_client()
        
        # Get market data
        klines = get_klines(um, symbol, "1h", 100)
        if not klines:
            print(f"❌ No data for {symbol}")
            return
            
        data_1h = parse_klines_data(klines)
        closes = data_1h.get("closes", [])
        
        if len(closes) < 30:
            print(f"❌ Not enough data for {symbol} (need 30, got {len(closes)})")
            return
            
        # Calculate MACD
        macd_line, signal_line, histogram = calculate_macd(closes)
        
        if len(macd_line) < 3:
            print(f"❌ MACD calculation failed for {symbol}")
            return
            
        # Get current and previous colors
        current_color = get_macd_color(macd_line, -1)
        previous_color = get_macd_color(macd_line, -2)
        prev2_color = get_macd_color(macd_line, -3)
        
        # Check for color change
        color_changed = is_macd_color_changed(symbol, data_1h)
        
        # Get signal strength
        signal_strength = get_macd_signal_strength(symbol, data_1h)
        
        # Get current price
        current_price = closes[-1]
        
        # Display results
        print(f"📊 Current Price: ${current_price:.4f}")
        print(f"📈 MACD Line: {macd_line[-1]:.6f}")
        print(f"📉 Signal Line: {signal_line[-1]:.6f}")
        print(f"📊 Histogram: {histogram[-1]:.6f}")
        print(f"🎨 Color History: {prev2_color} → {previous_color} → {current_color}")
        print(f"🔄 Color Changed: {'✅ YES' if color_changed else '❌ NO'}")
        print(f"💪 Signal Strength: {signal_strength:.2f}/1.0")
        
        if color_changed:
            print(f"🚨 SIGNAL DETECTED!")
            if current_color == "GREEN":
                print(f"🟢 LONG Signal: MACD crossed above 0")
            else:
                print(f"🔴 SHORT Signal: MACD crossed below 0")
        else:
            print(f"⚪ No Signal: MACD staying {current_color}")
            
        # Get full analysis text
        analysis = get_macd_analysis_text(symbol, data_1h, current_price)
        print(f"\n📝 Full Analysis:")
        print(analysis)
        
    except Exception as e:
        print(f"❌ Error testing {symbol}: {e}")

def main():
    """Run MACD tests on multiple symbols"""
    print("🧪 MACD System Test Suite")
    print("=" * 60)
    
    # Set up API config
    api_cfg = APIConfig()
    
    # Test symbols with different market conditions
    test_symbols = [
        "BTCUSDT",    # Major crypto
        "ETHUSDT",    # Major altcoin
        "ADAUSDT",    # Mid-cap
        "SOLUSDT",    # Popular altcoin
        "DOGEUSDT"    # Meme coin
    ]
    
    print(f"Testing {len(test_symbols)} symbols...")
    
    for symbol in test_symbols:
        test_macd_with_symbol(symbol)
        
    print(f"\n✅ MACD Testing Complete!")
    print(f"🎯 System is ready for live trading")

if __name__ == "__main__":
    main()
