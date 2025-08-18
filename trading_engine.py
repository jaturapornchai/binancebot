"""
⚡ Trading Engine - Core trading execution logic
Handles position management and order execution
"""

import json
from typing import Dict, List, Optional

from binance.um_futures import UMFutures

from binance_client import (calculate_quantity, cancel_order, get_mark_price,
                            get_open_orders, place_order, set_leverage,
                            set_margin_type)
from config import cfg
from utils import safe_float


def execute_trade(um: UMFutures, symbol: str, ai_decision: Dict, 
                 margin_usdt: float, leverage: int, 
                 filters: Dict[str, Dict]) -> Optional[Dict]:
    """
    Execute trade based on AI decision without automatic SL/TP
    AI will manage position closure through analysis
    Returns trade result or None if failed
    """
    try:
        if not ai_decision.get('buy_signal') and not ai_decision.get('sell_signal'):
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
        
        # No automatic SL/TP - AI will manage position closure
        print(f"🤖 AI will manage this position - no automatic SL/TP")
        print(f"   Confidence Level: {ai_decision.get('confidence', 'N/A')}")
        
        trade_result = {
            "symbol": symbol,
            "side": side.replace("BUY", "LONG").replace("SELL", "SHORT"),
            "price": safe_float(order_result.get('avgPrice', '0')),
            "confidence": ai_decision.get('confidence', 'N/A'),
            "reasoning": ai_decision.get('reasoning', '')
        }
        
        print(f"🎯 {trade_result['side']} {symbol} position opened - AI will decide when to close")
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
            
            # Check for MACD color change signal
            if not is_signal_func(symbol, data_1h):
                # แสดงสี MACD ปัจจุบันสำหรับ debug (แสดงแค่ 5 เหรียญแรก)
                if symbols_checked <= 5:
                    closes = data_1h.get("closes", [])
                    if len(closes) >= 30:
                        from macd_analysis import (calculate_macd,
                                                   get_macd_color)
                        macd_line, _, _ = calculate_macd(closes)
                        if len(macd_line) >= 2:
                            current_color = get_macd_color(macd_line, -1)
                            previous_color = get_macd_color(macd_line, -2)
                            print(f"⚪ {symbol}: No MACD signal ({previous_color}→{current_color})")
                        else:
                            print(f"⚪ {symbol}: No MACD signal")
                    else:
                        print(f"⚪ {symbol}: No MACD signal")
                else:
                    print(f"⚪ {symbol}: No MACD signal")
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
            
            # Execute trade if AI recommends action
            if ai_decision.get('buy_signal') or ai_decision.get('sell_signal'):
                action = "BUY" if ai_decision.get('buy_signal') else "SELL"
                confidence = ai_decision.get('confidence', 'N/A')
                
                print(f"✅ {symbol}: AI recommended {action} (Confidence: {confidence}/10) - Executing trade")
                print(f"   💡 Reasoning: {ai_decision.get('reasoning', 'N/A')}")
                
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
    🧹 Clean up positions and orders:
    - Cancel orphaned orders that don't have corresponding positions
    - Leave existing positions for AI to manage
    """
    cleanup_stats = {
        "positions_checked": 0,
        "positions_closed": 0,
        "orders_cancelled": 0,
        "errors": 0
    }
    
    print("\n🧹 === CLEANUP: Checking positions and orders ===")
    
    # Get all open orders (for all symbols)
    all_open_orders = get_open_orders(um, None)
    
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
            
            # Since we're no longer using automatic SL/TP, just cancel any orphaned orders
            # but leave positions for AI to manage
            if order_count > 0:
                print(f"🧹 {symbol}: Cancelling {order_count} orphaned orders (AI will manage position)")
                
                # Cancel existing orders to prevent interference with AI decisions
                for order in symbol_orders:
                    order_id = order.get("orderId")
                    if order_id:
                        if cancel_order(um, symbol, str(order_id)):
                            cleanup_stats["orders_cancelled"] += 1
                
                print(f"✅ {symbol}: Orphaned orders cancelled, position will be managed by AI")
            else:
                print(f"✅ {symbol}: Clean position, ready for AI management")
                
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
