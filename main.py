"""
🤖 Binance Futures Trading Bot with AI Analysis
Main application entry point - simplified and modular
"""

import json
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Add current directory to Python path for module imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import all modules
from config import cfg, APIConfig
from utils import get_thailand_time, countdown_sleep
import binance_client
import ai_client
from binance_client import (
    setup_trading_mode, get_available_usdt,
    get_exchange_filters, get_high_volume_symbols, get_klines, get_current_positions
)
from ema_analysis import is_ema_color_changed
from trading_engine import scan_symbols_for_signals, print_scan_summary, parse_klines_data, cleanup_positions_and_orders

# Initialize API config after loading environment
api_cfg = APIConfig()

# Set API config for other modules
binance_client.set_api_config(api_cfg)
ai_client.set_api_config(api_cfg)


def check_existing_positions(um):
    """Check and display existing positions"""
    print("=== LOOP2: Checking existing positions ===")
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
        print(f"📊 {symbol}: {side} size={abs(size):.6f} entry=${entry_price:.6f} mark=${mark_price:.6f} PNL=${pnl:.2f}")


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
            
            # LOOP2: Check existing positions (no AI analysis needed - SL/TP handles them)
            check_existing_positions(um)
            
            # CLEANUP: ทำความสะอาด positions และ orders ก่อนเริ่มสแกน
            current_positions = get_current_positions(um)
            if current_positions:
                cleanup_stats = cleanup_positions_and_orders(um, current_positions)
            
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
                get_klines, is_ema_color_changed, ai_client.analyze_with_deepseek
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
