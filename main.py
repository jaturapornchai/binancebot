"""
🤖 Binance Futures Trading Bot with AI Analysis
Main application entry point - simplified and modular
"""

import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add current directory to Python path for module imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ai_client
import binance_client
from binance_client import (close_position, get_available_usdt,
                            get_current_positions, get_exchange_filters,
                            get_high_volume_symbols, get_klines,
                            setup_trading_mode)
# Import all modules
from config import APIConfig, cfg
from trend_line_analysis import is_trend_line_signal_valid
from trading_engine import (parse_klines_data,
                            print_scan_summary, scan_symbols_for_signals)
from utils import countdown_sleep, get_thailand_time

# Initialize API config after loading environment
api_cfg = APIConfig()

# Set API config for other modules
binance_client.set_api_config(api_cfg)
ai_client.set_api_config(api_cfg)


def check_and_analyze_existing_positions(um):
    """Check existing positions and analyze with AI for potential closure"""
    print("=== LOOP2: Analyzing existing positions with AI ===")
    positions = get_current_positions(um)
    
    if not positions:
        print("📊 No existing positions found")
        return
    
    for pos in positions:
        symbol = pos.get("symbol", "UNKNOWN")
        size = float(pos.get("positionAmt", "0"))
        entry_price = float(pos.get("entryPrice", "0"))
        mark_price = float(pos.get("markPrice", "0"))
        pnl = float(pos.get("unRealizedProfit", "0"))
        
        side = "LONG" if size > 0 else "SHORT"
        pnl_percent = (pnl / (abs(size) * entry_price) * 100) if entry_price and abs(size * entry_price) > 1e-12 else 0
        
        print(f"📊 Analyzing {symbol}: {side} size={abs(size):.6f} entry=${entry_price:.6f} mark=${mark_price:.6f} PNL=${pnl:.2f} ({pnl_percent:+.2f}%)")
        
        # Get klines data for AI analysis (144 candles = 6 days of 1h data)  
        klines_data = get_klines(um, symbol, cfg.timeframe, 144)
        if not klines_data or len(klines_data) < 50:
            print(f"❌ {symbol}: Insufficient klines data for analysis")
            continue
            
        # Parse klines data
        from trading_engine import parse_klines_data
        data = parse_klines_data(klines_data)
        if not data["closes"]:
            print(f"❌ {symbol}: Failed to parse klines data")
            continue
        
        # Analyze position with AI
        ai_decision = ai_client.analyze_with_deepseek(
            symbol, data, mark_price, current_position=size, pnl=pnl, entry_price=entry_price
        )
        
        if not ai_decision:
            print(f"❌ {symbol}: AI analysis failed")
            continue
            
        action = ai_decision.get('action', '').upper()
        if action == 'CLOSE':
            print(f"🤖 AI recommends CLOSING {symbol} position")
            print(f"   Reasoning: {ai_decision.get('reasoning', 'N/A')}")
            print(f"   Confidence: {ai_decision.get('confidence', 'N/A')}/10")
            
            # Close the position
            if close_position(um, symbol, size):
                print(f"✅ {symbol}: Position closed successfully")
            else:
                print(f"❌ {symbol}: Failed to close position")
        else:
            print(f"🤖 AI recommends HOLDING {symbol} position")
            print(f"   Reasoning: {ai_decision.get('reasoning', 'N/A')}")
            print(f"   Confidence: {ai_decision.get('confidence', 'N/A')}/10")


def main_trading_loop():
    """Main trading loop"""
    print("Binance Futures bot started")
    print(json.dumps(cfg.to_dict(), indent=2))
    
    # Initialize Binance client
    um = binance_client.create_binance_client()
    setup_trading_mode(um)
    
    # Get exchange filters once
    filters = get_exchange_filters(um)
    
    first_run = True
    
    while True:
        try:
            # LOOP1: Time sync - align to hour (minute 0) if not first run
            if not first_run:
                thailand_now = get_thailand_time()
                print(f"🇹🇭 Current Thailand time: {thailand_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                if thailand_now.minute != 0:
                    print("Not at hour start (minute 0); sleeping 30s before LOOP1 checks…")
                    countdown_sleep(30, thailand_now.hour + 1, "Waiting for hour start")
                    continue
                    
            first_run = False
            
            # LOOP2: Check and analyze existing positions with AI
            check_and_analyze_existing_positions(um)
            
            # LOOP3: Scan for new trading opportunities
            print("=== LOOP3: Checking coins for new positions ===")
            available_usdt = get_available_usdt(um)
            print(f"Available USDT: {available_usdt:.2f}")
            
            if available_usdt < cfg.min_balance_usdt:
                print(f"💰 Insufficient balance: ${available_usdt:.2f} < ${cfg.min_balance_usdt}")
                print("⏰ Waiting until next hour...")
                
                thailand_now = get_thailand_time()
                next_hour = (thailand_now.hour + 1) % 24
                target_time = thailand_now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
                if next_hour == 0:
                    target_time = target_time.replace(day=target_time.day + 1)
                
                wait_seconds = (target_time - thailand_now).total_seconds()
                
                if wait_seconds > 0:
                    countdown_sleep(int(wait_seconds), next_hour, "💰 Insufficient balance")
                else:
                    print("⏰ Already past the target time, continuing immediately")
                continue
            
            # Dynamic coin discovery
            dynamic_symbols = get_high_volume_symbols(um, cfg.min_volume_usdt)
            print(f"🎲 Shuffled all {len(dynamic_symbols)} symbols for trading")
            
            # Scan all symbols for opportunities
            scan_results = scan_symbols_for_signals(
                um, dynamic_symbols, filters,
                get_klines, is_trend_line_signal_valid, ai_client.analyze_with_deepseek
            )
            
            # Print scan summary
            print_scan_summary(scan_results)
            
            # Wait until next hour
            print("=== Cycle complete - waiting until next hour's first minute ===")
            thailand_now = get_thailand_time()
            print(f"🇹🇭 Current Thailand time: {thailand_now.strftime('%Y-%m-%d %H:%M:%S')}")
            
            next_hour = (thailand_now.hour + 1) % 24
            next_target = thailand_now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
            if next_hour == 0:
                next_target = next_target.replace(day=next_target.day + 1)
            
            wait_seconds = (next_target - thailand_now).total_seconds()
            
            if wait_seconds > 0:
                countdown_sleep(int(wait_seconds), next_hour, "⏰ Cycle complete")
            else:
                print("⏰ Already past the target time, continuing immediately")
            
        except Exception as e:
            print(f"! Main loop error: {e}")
            # No sleep after main loop error per user request


def run():
    """Application entry point"""
    try:
        main_trading_loop()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"! Fatal error: {e}")


if __name__ == "__main__":
    run()
