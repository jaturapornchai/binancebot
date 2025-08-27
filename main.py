#!/usr/bin/env python3
"""
Main application entry point - simplified trailing stop loss disabled
"""

import json
import os
from datetime import datetime, timedelta

# Add the project directory to the path to handle imports
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from binance.um_futures import UMFutures

# Import configurations and clients
import ai_client
import binance_client
from binance_client import (close_position, get_available_usdt,
                            get_current_positions, get_exchange_filters,
                            get_high_volume_symbols, get_klines, get_mark_price,
                            get_open_orders, setup_trading_mode)
# Import all modules
from config import APIConfig, cfg
from breakout_analysis import is_breakout_signal_valid
from trading_engine import (parse_klines_data,
                            print_scan_summary, scan_symbols_for_signals,
                            cleanup_all_positions)
from utils import countdown_sleep, get_thailand_time

# Initialize API config after loading environment
api_cfg = APIConfig()

# Set API config for other modules
binance_client.set_api_config(api_cfg)
ai_client.set_api_config(api_cfg)


def check_and_update_existing_positions(um):
    """Check existing positions and update SL/TP if needed"""
    print("=== LOOP2: Updating existing positions stop losses ===")
    
    from binance_client import get_current_positions, get_exchange_filters
    
    positions = get_current_positions(um)
    
    if not positions:
        print("📊 No existing positions found")
        # If no positions but there might be orphaned orders, clean them up
        cleanup_result = cleanup_all_positions(um)
        if cleanup_result['cleanup_performed'] > 0:
            print(f"🧹 Cleaned up {cleanup_result['cleanup_performed']} orphaned orders (no positions found)")
        return
    
    print(f"📊 Found {len(positions)} open position(s)")
    filters = get_exchange_filters(um)
    
    for pos in positions:
        symbol = pos.get("symbol", "UNKNOWN")
        size = float(pos.get("positionAmt", "0"))
        entry_price = float(pos.get("entryPrice", "0"))
        mark_price = float(pos.get("markPrice", "0"))
        pnl = float(pos.get("unRealizedProfit", "0"))
        
        side = "LONG" if size > 0 else "SHORT"
        pnl_percent = (pnl / (abs(size) * entry_price) * 100) if entry_price and abs(size * entry_price) > 1e-12 else 0
        
        print(f"📊 Position: {symbol} {side} ${entry_price:.6f} → ${mark_price:.6f} PNL=${pnl:.2f} ({pnl_percent:+.2f}%)")
        
        # Position protection is handled by cleanup system
        print(f"🛡️ {symbol}: Position protection managed by cleanup system")


def main_trading_loop():
    """Main trading loop with integrated cleanup"""
    print("🚀 Binance Futures bot started with Auto Cleanup")
    print("   - Automatic order cleanup")
    print("   - Position management")
    print(json.dumps(cfg.to_dict(), indent=2))
    
    # Initialize Binance client
    um = binance_client.create_binance_client()
    setup_trading_mode(um)
    
    # Initial cleanup before starting
    print("\n🧹 Performing initial cleanup...")
    initial_cleanup_result = cleanup_all_positions(um)
    print(f"✅ Initial cleanup completed: {initial_cleanup_result['cleanup_performed']} symbols cleaned")
    
    # Get exchange filters once
    filters = get_exchange_filters(um)
    
    first_run = True
    
    while True:
        try:
            # Check and update existing positions (disabled - no trailing stop loss)
            check_and_update_existing_positions(um)
            
            # Quick cleanup check for orphaned orders
            orphaned_check = cleanup_all_positions(um)
            if orphaned_check['cleanup_performed'] > 0:
                print(f"🧹 Cleaned up {orphaned_check['cleanup_performed']} orphaned orders during position check")
            
            # Check balance before scanning for new positions
            available_usdt = get_available_usdt(um)
            
            if available_usdt < cfg.min_balance_usdt:
                print(f"💰 Insufficient balance: ${available_usdt:.2f} < ${cfg.min_balance_usdt}")
                print("⏰ Waiting until next hour...")
                
                # Calculate next hour timing
                thailand_now = get_thailand_time()
                next_hour = (thailand_now.hour + 1) % 24
                next_target = thailand_now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
                if next_hour == 0:
                    next_target = next_target.replace(day=next_target.day + 1)
                
                target_time = next_target
                
                wait_seconds = (target_time - thailand_now).total_seconds()
                
                if wait_seconds > 0:
                    countdown_sleep(int(wait_seconds), next_hour, "💰 Insufficient balance")
                else:
                    print("⏰ Already past the target time, continuing immediately")
                continue
            
            print("=== LOOP3: Checking coins for new positions ===")
            print(f"Available USDT: {available_usdt:.2f}")
            
            # Dynamic coin discovery
            dynamic_symbols = get_high_volume_symbols(um, cfg.min_volume_usdt)
            print(f"🎲 Shuffled all {len(dynamic_symbols)} symbols for trading")
            
            # Scan all symbols for opportunities
            scan_results = scan_symbols_for_signals(
                um, dynamic_symbols, filters,
                get_klines, is_breakout_signal_valid, ai_client.analyze_with_deepseek
            )
            
            # Print scan summary
            print_scan_summary(scan_results, um)
            
            # Periodic cleanup every cycle
            print("\n🧹 Performing periodic cleanup...")
            cleanup_result = cleanup_all_positions(um)
            if cleanup_result['cleanup_performed'] > 0:
                print(f"🗑️ Cleaned up {cleanup_result['cleanup_performed']} orphaned orders")
            else:
                print("✅ No cleanup needed - all orders are valid")
            
            # Show current position summary
            print("\n📊 === CURRENT PORTFOLIO STATUS ===")
            current_positions = get_current_positions(um)
            if current_positions:
                total_pnl = 0
                for pos in current_positions:
                    symbol = pos.get('symbol', 'N/A')
                    size = float(pos.get('positionAmt', 0))
                    entry = float(pos.get('entryPrice', 0))
                    pnl = float(pos.get('unRealizedProfit', 0))
                    side = "LONG" if size > 0 else "SHORT"
                    total_pnl += pnl
                    print(f"  {symbol}: {side} Entry=${entry:.6f} PnL=${pnl:.2f}")
                print(f"💰 Total Unrealized PnL: ${total_pnl:.2f}")
            else:
                print("  No open positions")
            print("=" * 40)
            
            # Wait until next hour
            print("\n=== Cycle complete - waiting until next hour's first minute ===")
            thailand_now = get_thailand_time()
            print(f"🇹🇭 Current Thailand time: {thailand_now.strftime('%Y-%m-%d %H:%M:%S')}")
            
            next_hour = (thailand_now.hour + 1) % 24
            next_target = thailand_now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
            if next_hour == 0:
                next_target = next_target.replace(day=next_target.day + 1)
                
            target_time = next_target
            wait_seconds = (target_time - thailand_now).total_seconds()
            
            print(f"⏰ Waiting {wait_seconds/60:.1f} minutes until {target_time.strftime('%H:%M:%S')} Thailand time")
            
            if wait_seconds > 0:
                countdown_sleep(int(wait_seconds), next_hour, "Next cycle")
            else:
                print("⏰ Already past the target time, continuing immediately")
        
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user")
            break
        except Exception as e:
            print(f"❌ Main loop error: {e}")
            print("⏰ Waiting 60 seconds before retry...")
            
            import time
            time.sleep(60)


if __name__ == "__main__":
    main_trading_loop()

