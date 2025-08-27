"""
⚡ Trading Engine - Core trading execution logic  
Handles position management and order execution with Triangle Pattern Analysis
"""

import json
import time
from typing import Dict, List, Optional

from binance.um_futures import UMFutures

from binance_client import (calculate_quantity, get_mark_price,
                            get_open_orders, place_order, set_leverage, set_margin_type,
                            cancel_all_sl_tp_orders, check_and_cleanup_position,
                            cleanup_orphaned_orders, check_and_create_position_protection,
                            cancel_all_orders_for_symbol)
from config import cfg
from linear_regression_analyzer import LinearRegressionChannelAnalyzer
from utils import safe_float


def execute_trade(um: UMFutures, symbol: str, ai_decision: Dict, 
                 margin_usdt: float, leverage: int, 
                 filters: Dict[str, Dict]) -> Optional[Dict]:
    """
    Execute trade based on AI decision with comprehensive validation
    AI will manage position closure through analysis
    Returns trade result or None if failed
    """
    try:
        if not ai_decision.get('buy_signal') and not ai_decision.get('sell_signal'):
            return None
        
        current_price = get_mark_price(um, symbol)
        if current_price <= 0:
            print(f"❌ {symbol}: Invalid price: {current_price}")
            return None
        
        # Check available balance
        from binance_client import get_available_usdt
        available_usdt = get_available_usdt(um)
        print(f"💰 {symbol}: Available balance: ${available_usdt:.2f}, Required margin: ${margin_usdt}")
        
        if available_usdt < margin_usdt:
            print(f"❌ {symbol}: Insufficient balance ${available_usdt:.2f} < ${margin_usdt} required")
            return None
        
        # Set margin type and leverage
        print(f"⚙️ {symbol}: Setting CROSSED margin and {leverage}x leverage")
        set_margin_type(um, symbol, "CROSSED")
        set_leverage(um, symbol, leverage)
        
        # Calculate quantity with detailed logging
        print(f"🧮 {symbol}: Calculating quantity...")
        quantity = calculate_quantity(um, symbol, margin_usdt, current_price, leverage, filters)
        if quantity <= 0:
            print(f"❌ {symbol}: Invalid quantity calculated: {quantity}")
            return None
        
        # Determine side
        side = "BUY" if ai_decision.get('buy_signal') else "SELL"
        
        # Final validation before placing order
        notional_value = quantity * current_price
        print(f"📋 {symbol}: Final order details - {side} {quantity:.6f} @ ${current_price:.4f} (${notional_value:.2f})")
        
        # Place main order
        order_result = place_order(um, symbol, side, quantity, "MARKET")
        if not order_result:
            print(f"! Failed to place {side} order for {symbol}")
            return None

        print(f"- Placed {side} {symbol} qty={quantity} -> status={order_result.get('status', 'UNKNOWN')} avg=${safe_float(order_result.get('avgPrice', '0')):.6f}")
        
        # Use actual execution data from order result
        executed_qty = safe_float(order_result.get('executedQty', '0'))
        avg_price = safe_float(order_result.get('avgPrice', '0'))
        order_status = order_result.get('status', 'UNKNOWN')
        order_id = order_result.get('orderId')
        
        # Check if order is filled immediately
        if order_status != 'FILLED' or executed_qty <= 0:
            print(f"⏳ {symbol}: Order pending - status: {order_status}, executed: {executed_qty}")
            
            # Wait up to 10 seconds for fill
            max_wait_time = 10
            wait_interval = 1
            total_waited = 0
            
            while total_waited < max_wait_time and order_status != 'FILLED':
                time.sleep(wait_interval)
                total_waited += wait_interval
                
                try:
                    # Check order status directly
                    from binance_client import get_order_status
                    order_info = get_order_status(um, symbol, order_id)
                    
                    if order_info:
                        order_status = order_info.get('status', 'UNKNOWN')
                        executed_qty = safe_float(order_info.get('executedQty', '0'))
                        avg_price = safe_float(order_info.get('avgPrice', '0'))
                        print(f"⏳ {symbol}: Checking order... status={order_status}, executed={executed_qty}")
                        
                        # If filled, break out
                        if order_status == 'FILLED' and executed_qty > 0:
                            break
                        
                except Exception as e:
                    print(f"⚠️ {symbol}: Error checking order status: {e}")
                    break
            
            # Final check
            if order_status != 'FILLED' or executed_qty <= 0:
                print(f"❌ {symbol}: Order timeout - status: {order_status}, executed: {executed_qty} after {total_waited}s")
                # Cancel the unfilled order
                try:
                    from binance_client import cancel_order
                    cancel_order(um, symbol, order_id)
                    print(f"🗑️ {symbol}: Cancelled unfilled order {order_id}")
                except:
                    pass
                return None
        
        print(f"📊 Order executed: {symbol} {side} qty={executed_qty:.6f} @ avg=${avg_price:.6f}")
        
        # Position will be protected by cleanup system in next cycle
        print(f"🛡️ Position protection will be handled by cleanup system in next cycle")
        
        trade_result = {
            "symbol": symbol,
            "side": side.replace("BUY", "LONG").replace("SELL", "SHORT"),
            "price": avg_price,
            "quantity": executed_qty,
            "order_id": order_result.get('orderId'),
            "reasoning": ai_decision.get('reasoning', '')
        }
        
        print(f"🎯 {trade_result['side']} {symbol} position opened - cleanup system will protect it")
        print(json.dumps(trade_result, separators=(',', ':'), ensure_ascii=False))
        
        return trade_result
        
    except Exception as e:
        print(f"! Error executing trade for {symbol}: {e}")
        return None


def scan_symbols_for_signals(um: UMFutures, symbols: List[str], filters: Dict, 
                           get_klines_func, is_signal_func, analyze_func) -> Dict:
    """
    Scan symbols for trading signals and execute trades
    Returns summary statistics
    """
    symbols_checked = 0
    symbols_with_signals = 0
    symbols_skipped = 0
    
    # Get current open positions to avoid duplicate trades
    from binance_client import get_current_positions
    current_positions = get_current_positions(um)
    existing_symbols = {pos.get("symbol") for pos in current_positions if abs(float(pos.get("positionAmt", "0"))) > 1e-12}
    
    if existing_symbols:
        print(f"🔒 Existing positions: {len(existing_symbols)} symbols - {list(existing_symbols)}")
    
    print(f"🐛 Debug - All {len(symbols)} symbols: {symbols}")
    
    for i, symbol in enumerate(symbols):
        try:
            symbols_checked += 1
            
            # Check available balance before processing each symbol
            from binance_client import get_available_usdt
            available_usdt = get_available_usdt(um)
            
            if available_usdt < cfg.min_balance_usdt:
                print(f"💰 Balance check: ${available_usdt:.2f} < ${cfg.min_balance_usdt} minimum")
                print(f"⏸️ Insufficient balance - stopping scan and waiting for next cycle")
                break
            
            # Skip symbols that already have open positions
            if symbol in existing_symbols:
                symbols_skipped += 1
                print(f"⏭️ {symbol}: Skipped (existing position)")
                continue
            
            # Get data for Linear Regression Channel analysis
            klines = get_klines_func(um, symbol, cfg.timeframe, 500)
            if not klines or len(klines) < 112:  # Need at least 112 candles for Linear Regression analysis (100 + 12 breakout)
                print(f"❌ {symbol}: Insufficient data for Linear Regression analysis (klines: {len(klines) if klines else 0})")
                continue
            
            # Parse klines data
            data = parse_klines_data(klines)
            if not data["closes"]:
                print(f"❌ {symbol}: Failed to parse klines data")
                continue
            
            # Analyze Linear Regression Channels
            channel_analyzer = LinearRegressionChannelAnalyzer(length=100, deviation_multiplier=2.0)
            detected_channels = channel_analyzer.analyze_channels(data)
            channel_signals = channel_analyzer.get_trading_signals(detected_channels)
            
            # Generate channel summary for logging
            channel_summary = channel_analyzer.generate_summary(detected_channels)
            print(f"� {symbol}: {channel_summary}")
            
            # Check if we have a valid channel signal
            if channel_signals['signal'] == 'HOLD':
                print(f"⏸️ {symbol}: No channel breakout detected - HOLD")
                continue
                
            # Send channel analysis to AI for final decision
            ai_analysis_data = {
                "symbol": symbol,
                "current_price": data["closes"][-1], 
                "channels": channel_signals['channels'],
                "signal": channel_signals['signal'],
                "reason": channel_signals['reason'],
                "target_price": channel_signals.get('target_price'),
                "stop_loss_price": channel_signals.get('stop_loss_price')
            }
            
            print(f"🎯 CHANNEL SIGNAL: {symbol} - {channel_signals['signal']} (Confidence: {channel_signals['confidence']:.1%})")
            
            # Check confidence threshold before sending to AI
            confidence_pct = channel_signals['confidence'] * 100  # Convert to percentage
            if confidence_pct < 25:
                print(f"⏸️ {symbol}: Confidence {confidence_pct:.1f}% too low (< 25%) - Skipping AI analysis")
                continue
            
            print(f"📊 Sending channel analysis to AI for final decision...")
            symbols_with_signals += 1
            
            # Get AI decision based on linear regression channel analysis
            from ai_client import get_ai_decision_channel_pattern
            ai_decision = get_ai_decision_channel_pattern(symbol, ai_analysis_data)
            
            if not ai_decision:
                print(f"❌ {symbol}: AI analysis failed")
                continue
                
            print(f"🤖 {symbol}: AI Decision - {ai_decision.get('position', 'HOLD')} (Confidence: {ai_decision.get('confidence', 0)}%)")
            
            # Execute trade if AI recommends action
            if ai_decision.get('position') in ['LONG', 'SHORT']:
                action = ai_decision.get('position')  # LONG or SHORT
                
                print(f"✅ {symbol}: AI recommended {action} - Executing triangle breakout trade")
                print(f"   💡 Reasoning: {ai_decision.get('reasoning', 'N/A')}")
                
                # Convert triangle AI decision to trading engine format
                trade_decision = {
                    'buy_signal': action == 'LONG',
                    'sell_signal': action == 'SHORT',
                    'reasoning': ai_decision.get('reasoning'),
                    'entry_reason': ai_decision.get('entry_reason'),
                    'risk_management': ai_decision.get('risk_management')
                }
                
                execute_trade(um, symbol, trade_decision, cfg.margin_per_trade_usdt, 
                            cfg.leverage, filters)
            else:
                print(f"⏸️ {symbol}: AI recommended HOLD - No trade executed")
            
            # Progress update every 100 symbols
            if (i + 1) % 100 == 0:
                print(f"📊 Progress: {i+1}/{len(symbols)} checked, {symbols_with_signals} signals")
        
        except Exception as e:
            print(f"❌ {symbol}: Error - {e}")
            # No sleep after error per user request
    
    return {
        "total_symbols": len(symbols),
        "symbols_checked": symbols_checked,
        "symbols_skipped": symbols_skipped,
        "signals_found": symbols_with_signals,
        "completion_rate": (symbols_checked / len(symbols) * 100) if symbols else 0
    }


def parse_klines_data(klines: List[List]) -> Dict[str, List]:
    """
    Parse klines data into OHLCV format with timestamps
    Returns dictionary with timestamps, opens, highs, lows, closes, volumes
    """
    data = {
        "timestamps": [],
        "opens": [],
        "highs": [],
        "lows": [],
        "closes": [],
        "volumes": []
    }
    
    try:
        for kline in klines:
            if len(kline) >= 6:
                data["timestamps"].append(int(kline[0]))  # Timestamp
                data["opens"].append(float(kline[1]))     # Open price
                data["highs"].append(float(kline[2]))     # High price  
                data["lows"].append(float(kline[3]))      # Low price
                data["closes"].append(float(kline[4]))    # Close price
                data["volumes"].append(float(kline[5]))   # Volume
    except Exception as e:
        print(f"! Error parsing klines data: {e}")
    
    return data


def print_scan_summary(results: Dict, um=None):
    """Print final scan summary with balance info"""
    print(f"✅ SCAN COMPLETE: {results['symbols_checked']}/{results['total_symbols']} symbols, {results['signals_found']} signals, {results['completion_rate']:.1f}%")


def cleanup_all_positions(um: UMFutures) -> Dict:
    """Check all positions, cleanup orphaned orders, and create missing protection"""
    try:
        print("🧹 Starting position cleanup process...")
        result = {
            'total_checked': 0,
            'positions_found': 0,
            'cleanup_performed': 0,
            'protection_created': 0,
            'symbols': []
        }
        
        # Run general cleanup for orphaned orders
        cleanup_success = cleanup_orphaned_orders(um)
        if cleanup_success:
            print("✅ General cleanup completed")
        
        # Get current positions to check for protection
        from binance_client import get_current_positions, get_exchange_filters, check_and_create_position_protection
        
        positions = get_current_positions(um)
        if not positions:
            print("📊 No positions found for protection check")
            return result
        
        filters = get_exchange_filters(um)
        
        for pos in positions:
            symbol = pos.get("symbol", "UNKNOWN")
            size = float(pos.get("positionAmt", "0"))
            
            if abs(size) < 1e-12:  # Skip empty positions
                continue
            
            result['total_checked'] += 1
            result['positions_found'] += 1
            
            # Check and create protection if missing
            protection_result = check_and_create_position_protection(um, symbol, filters)
            result['symbols'].append(protection_result)
            
            if protection_result.get('protection_created'):
                result['protection_created'] += 1
                print(f"🛡️ {symbol}: Protection created successfully")
            elif protection_result.get('already_protected'):
                print(f"✅ {symbol}: Already has protection")
            else:
                error = protection_result.get('error', 'Unknown error')
                print(f"⚠️ {symbol}: Protection not created - {error}")
        
        print(f"🧹 Cleanup summary: {result['total_checked']} checked, {result['positions_found']} with positions, {result['protection_created']} protection created")
        return result
        
    except Exception as e:
        print(f"❌ Error in cleanup_all_positions: {e}")
        return {
            'total_checked': 0,
            'positions_found': 0,
            'cleanup_performed': 0,
            'protection_created': 0,
            'symbols': [],
            'error': str(e)
        }
