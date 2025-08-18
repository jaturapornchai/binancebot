"""
⚡ Trading Engine - Core trading execution logic
Handles position management and order execution
"""

import json
from typing import Dict, List, Optional

from binance.um_futures import UMFutures
from config import cfg
from binance_client import (
    get_mark_price, set_margin_type, set_leverage, 
    calculate_quantity, place_order, get_open_orders, cancel_order, close_position
)
from utils import safe_float


def execute_trade(um: UMFutures, symbol: str, ai_decision: Dict, 
                 margin_usdt: float, leverage: int, 
                 filters: Dict[str, Dict]) -> Optional[Dict]:
    """
    Execute trade based on AI decision with Stop Loss and Take Profit
    Returns trade result or None if failed
    """
    try:
        if not ai_decision.get('buy_signal') and not ai_decision.get('sell_signal'):
            return None
        
        # Validate mandatory SL/TP before proceeding
        stop_loss = ai_decision.get('stop_loss')
        take_profit = ai_decision.get('take_profit')
        
        if not stop_loss or not isinstance(stop_loss, (int, float)) or stop_loss <= 0:
            print(f"! {symbol}: Missing or invalid Stop Loss - Trade execution aborted")
            return None
            
        if not take_profit or not isinstance(take_profit, (int, float)) or take_profit <= 0:
            print(f"! {symbol}: Missing or invalid Take Profit - Trade execution aborted")
            return None
        
        current_price = get_mark_price(um, symbol)
        if current_price <= 0:
            print(f"! Invalid price for {symbol}: {current_price}")
            return None
        
        # Set margin type and leverage
        set_margin_type(um, symbol, "ISOLATED")
        set_leverage(um, symbol, leverage)
        
        # Calculate quantity
        quantity = calculate_quantity(um, symbol, margin_usdt, current_price, leverage, filters)
        if quantity <= 0:
            print(f"! Invalid quantity for {symbol}: {quantity}")
            return None
        
        # Determine side
        side = "BUY" if ai_decision.get('buy_signal') else "SELL"
        
        # Place main order
        order_result = place_order(um, symbol, side, quantity, "MARKET")
        if not order_result:
            print(f"! Failed to place {side} order for {symbol}")
            return None
        
        print(f"- Placed {side} {symbol} qty={quantity} -> status={order_result.get('status', 'UNKNOWN')} avg=${safe_float(order_result.get('avgPrice', '0')):.6f}")
        
        # Use validated SL/TP levels from AI decision
        print(f"   📉 Stop Loss: ${stop_loss:.6f}")
        print(f"   📈 Take Profit: ${take_profit:.6f}")
        
        # Place Stop Loss and Take Profit orders
        sl_tp_result = place_sl_tp_orders(um, symbol, side, quantity, stop_loss, take_profit)
        
        trade_result = {
            "symbol": symbol,
            "side": side.replace("BUY", "LONG").replace("SELL", "SHORT"),
            "price": safe_float(order_result.get('avgPrice', '0')),
            "sl_tp": sl_tp_result
        }
        
        print(f"🎯 AI-recommended SL/TP placed for {trade_result['side']} {symbol}: {sl_tp_result}")
        print(json.dumps(trade_result, separators=(',', ':')))
        
        return trade_result
        
    except Exception as e:
        print(f"! Error executing trade for {symbol}: {e}")
        return None


def place_sl_tp_orders(um: UMFutures, symbol: str, side: str, quantity: float, 
                      stop_loss: Optional[float], take_profit: Optional[float]) -> str:
    """
    Place Stop Loss and Take Profit orders
    Returns status string
    """
    try:
        orders_placed = []
        
        if stop_loss:
            # For LONG position: SL is SELL STOP order below entry
            # For SHORT position: SL is BUY STOP order above entry
            sl_side = "SELL" if side == "BUY" else "BUY"
            
            sl_order = place_order(um, symbol, sl_side, quantity, "STOP_MARKET", stop_loss)
            if sl_order:
                orders_placed.append("SL")
        
        if take_profit:
            # For LONG position: TP is SELL LIMIT order above entry
            # For SHORT position: TP is BUY LIMIT order below entry
            tp_side = "SELL" if side == "BUY" else "BUY"
            
            tp_order = place_order(um, symbol, tp_side, quantity, "TAKE_PROFIT_MARKET", take_profit)
            if tp_order:
                orders_placed.append("TP")
        
        if orders_placed:
            return "/".join(orders_placed)
        else:
            return "none"
            
    except Exception as e:
        print(f"! Error placing SL/TP orders for {symbol}: {e}")
        return "error"


def scan_symbols_for_signals(um: UMFutures, symbols: List[str], filters: Dict, 
                           get_klines_func, is_signal_func, analyze_func) -> Dict:
    """
    Scan symbols for trading signals and execute trades
    Returns summary statistics
    """
    symbols_checked = 0
    symbols_with_signals = 0
    
    print(f"🐛 Debug - All {len(symbols)} symbols: {symbols}")
    
    for i, symbol in enumerate(symbols):
        try:
            symbols_checked += 1
            
            # Get 1h data (288 candles = 12 days of 1h data)
            klines_1h = get_klines_func(um, symbol, "1h", 288)
            if not klines_1h or len(klines_1h) < 50:
                print(f"❌ {symbol}: Insufficient data (klines: {len(klines_1h) if klines_1h else 0})")
                continue
            
            # Parse klines data
            data_1h = parse_klines_data(klines_1h)
            if not data_1h["closes"]:
                print(f"❌ {symbol}: Failed to parse klines data")
                continue
            
            # Check for EMA color change signal
            if not is_signal_func(symbol, data_1h):
                # แสดงสี EMA ปัจจุบันสำหรับ debug (แสดงแค่ 5 เหรียญแรก)
                if symbols_checked <= 5:
                    closes = data_1h.get("closes", [])
                    if len(closes) >= 10:
                        from ema_analysis import calculate_ema, get_ema_color
                        ema8_values = calculate_ema(closes, 8)
                        if len(ema8_values) >= 3:
                            current_color = get_ema_color(ema8_values, -1)
                            previous_color = get_ema_color(ema8_values, -2)
                            print(f"⚪ {symbol}: No EMA signal ({previous_color}→{current_color})")
                        else:
                            print(f"⚪ {symbol}: No EMA signal")
                    else:
                        print(f"⚪ {symbol}: No EMA signal")
                else:
                    print(f"⚪ {symbol}: No EMA signal")
                continue
            
            # Signal detected!
            print(f"🎯 SIGNAL DETECTED: {symbol} - Processing with AI...")
            symbols_with_signals += 1
            
            # Get current price
            current_price = get_mark_price(um, symbol)
            if current_price <= 0:
                print(f"❌ {symbol}: Invalid price: {current_price}")
                continue
            
            # Analyze with AI
            ai_decision = analyze_func(symbol, data_1h, current_price)
            if not ai_decision:
                print(f"❌ {symbol}: AI analysis failed")
                continue
            
            # Execute trade if AI recommends action AND provides valid SL/TP
            if ai_decision.get('buy_signal') or ai_decision.get('sell_signal'):
                action = "BUY" if ai_decision.get('buy_signal') else "SELL"
                
                # Validate mandatory Stop Loss and Take Profit
                stop_loss = ai_decision.get('stop_loss')
                take_profit = ai_decision.get('take_profit')
                
                if not stop_loss or not isinstance(stop_loss, (int, float)) or stop_loss <= 0:
                    print(f"❌ {symbol}: Invalid or missing Stop Loss (SL={stop_loss}) - Trade rejected")
                    continue
                
                if not take_profit or not isinstance(take_profit, (int, float)) or take_profit <= 0:
                    print(f"❌ {symbol}: Invalid or missing Take Profit (TP={take_profit}) - Trade rejected")
                    continue
                
                # Additional validation: SL/TP direction and risk/reward ratio
                if action == "BUY":  # LONG position
                    if stop_loss >= current_price:
                        print(f"❌ {symbol}: Stop Loss must be below entry price for LONG (SL={stop_loss:.6f}, Price={current_price:.6f}) - Trade rejected")
                        continue
                    if take_profit <= current_price:
                        print(f"❌ {symbol}: Take Profit must be above entry price for LONG (TP={take_profit:.6f}, Price={current_price:.6f}) - Trade rejected")
                        continue
                    
                    # Calculate risk/reward ratio for LONG
                    risk = current_price - stop_loss  # How much we can lose
                    reward = take_profit - current_price  # How much we can gain
                    
                else:  # SHORT position
                    if stop_loss <= current_price:
                        print(f"❌ {symbol}: Stop Loss must be above entry price for SHORT (SL={stop_loss:.6f}, Price={current_price:.6f}) - Trade rejected")
                        continue
                    if take_profit >= current_price:
                        print(f"❌ {symbol}: Take Profit must be below entry price for SHORT (TP={take_profit:.6f}, Price={current_price:.6f}) - Trade rejected")
                        continue
                    
                    # Calculate risk/reward ratio for SHORT
                    risk = stop_loss - current_price  # How much we can lose
                    reward = current_price - take_profit  # How much we can gain
                
                # Check minimum risk/reward ratio (1:1.5 minimum)
                if risk <= 0 or reward <= 0:
                    print(f"❌ {symbol}: Invalid risk/reward calculation (Risk={risk:.6f}, Reward={reward:.6f}) - Trade rejected")
                    continue
                
                risk_reward_ratio = reward / risk
                if risk_reward_ratio < 1.5:
                    print(f"❌ {symbol}: Risk/Reward ratio too low ({risk_reward_ratio:.2f}:1, minimum 1.5:1) - Trade rejected")
                    continue
                
                print(f"✅ {symbol}: AI recommended {action} with valid SL/TP (R/R: {risk_reward_ratio:.2f}:1) - Executing trade")
                print(f"   📍 Entry: ${current_price:.6f} | SL: ${stop_loss:.6f} | TP: ${take_profit:.6f}")
                execute_trade(um, symbol, ai_decision, cfg.margin_per_trade_usdt, 
                            cfg.leverage, filters)
            else:
                print(f"⏸️ {symbol}: No trade recommendation from AI")
            
            # Progress update every 50 symbols
            if (i + 1) % 50 == 0:
                print(f"\n📊 Progress: {i+1}/{len(symbols)} symbols checked, {symbols_with_signals} signals found\n")
        
        except Exception as e:
            print(f"❌ {symbol}: Error - {e}")
            # No sleep after error per user request
    
    return {
        "total_symbols": len(symbols),
        "symbols_checked": symbols_checked,
        "signals_found": symbols_with_signals,
        "completion_rate": (symbols_checked / len(symbols) * 100) if symbols else 0
    }


def parse_klines_data(klines: List[List]) -> Dict[str, List]:
    """
    Parse klines data into OHLCV format
    Returns dictionary with opens, highs, lows, closes, volumes
    """
    data = {
        "opens": [],
        "highs": [],
        "lows": [],
        "closes": [],
        "volumes": []
    }
    
    try:
        for kline in klines:
            if len(kline) >= 6:
                data["opens"].append(float(kline[1]))    # Open price
                data["highs"].append(float(kline[2]))    # High price  
                data["lows"].append(float(kline[3]))     # Low price
                data["closes"].append(float(kline[4]))   # Close price
                data["volumes"].append(float(kline[5]))  # Volume
    except Exception as e:
        print(f"! Error parsing klines data: {e}")
    
    return data


def cleanup_positions_and_orders(um: UMFutures, positions: List[Dict]) -> Dict:
    """
    🧹 ทำความสะอาด positions และ orders:
    - ปิด positions ที่มี orders ไม่ครบ 2 orders (SL + TP)
    - ลบ orders ที่ไม่มี position
    """
    cleanup_stats = {
        "positions_checked": 0,
        "positions_closed": 0,
        "orders_cancelled": 0,
        "errors": 0
    }
    
    print("\n🧹 === CLEANUP: Checking positions and orders ===")
    
    # Get all open orders
    all_open_orders = get_open_orders(um)
    
    # Group orders by symbol
    orders_by_symbol = {}
    for order in all_open_orders:
        symbol = order.get("symbol", "")
        if symbol not in orders_by_symbol:
            orders_by_symbol[symbol] = []
        orders_by_symbol[symbol].append(order)
    
    # Check each position
    for pos in positions:
        try:
            cleanup_stats["positions_checked"] += 1
            symbol = pos.get("symbol", "")
            position_size = safe_float(pos.get("positionAmt", "0"))
            
            if position_size == 0:
                continue
            
            # Count orders for this symbol
            symbol_orders = orders_by_symbol.get(symbol, [])
            order_count = len(symbol_orders)
            
            print(f"📊 {symbol}: Position={position_size:.6f}, Orders={order_count}")
            
            # If position has less than 2 orders (should have SL + TP), close it
            if order_count < 2:
                print(f"⚠️ {symbol}: Only {order_count} orders (expected 2 for SL+TP)")
                print(f"🚫 Closing {symbol} position...")
                
                # Cancel existing orders first
                for order in symbol_orders:
                    order_id = order.get("orderId")
                    if order_id:
                        if cancel_order(um, symbol, str(order_id)):
                            cleanup_stats["orders_cancelled"] += 1
                
                # Close position
                if close_position(um, symbol, position_size):
                    cleanup_stats["positions_closed"] += 1
                    print(f"✅ {symbol}: Position closed successfully")
                else:
                    cleanup_stats["errors"] += 1
                    print(f"❌ {symbol}: Failed to close position")
            else:
                print(f"✅ {symbol}: Has {order_count} orders (OK)")
                
        except Exception as e:
            cleanup_stats["errors"] += 1
            print(f"! Error checking {symbol}: {e}")
    
    # Check for orphaned orders (orders without positions)
    position_symbols = {pos.get("symbol") for pos in positions if safe_float(pos.get("positionAmt", "0")) != 0}
    
    for symbol, orders in orders_by_symbol.items():
        if symbol not in position_symbols:
            print(f"🗑️ {symbol}: Found {len(orders)} orphaned orders (no position)")
            for order in orders:
                order_id = order.get("orderId")
                if order_id:
                    if cancel_order(um, symbol, str(order_id)):
                        cleanup_stats["orders_cancelled"] += 1
    
    # Print cleanup summary
    print(f"\n📊 CLEANUP SUMMARY:")
    print(f"   Positions checked: {cleanup_stats['positions_checked']}")
    print(f"   Positions closed: {cleanup_stats['positions_closed']}")
    print(f"   Orders cancelled: {cleanup_stats['orders_cancelled']}")
    print(f"   Errors: {cleanup_stats['errors']}")
    print("=" * 60)
    
def print_scan_summary(results: Dict):
    """Print final scan summary"""
    print("=" * 60)
    print(f"📊 SCAN COMPLETE:")
    print(f"   Total symbols available: {results['total_symbols']}")  
    print(f"   Symbols scanned: {results['symbols_checked']}")
    print(f"   Signals detected: {results['signals_found']}")
    print(f"   Completion rate: {results['completion_rate']:.1f}%")
    print("=" * 60)
