"""
💼 Binance Futures API client functions
Handles all Binance Futures API interactions
"""

import json
import math
import os
import random
from typing import Any, Dict, List, Optional

from binance.um_futures import UMFutures
from utils import retry_call, safe_float

# Global API config - will be set by main
api_cfg = None

def set_api_config(config):
    """Set API configuration from main"""
    global api_cfg
    api_cfg = config


def create_binance_client() -> UMFutures:
    """Create and configure Binance Futures client"""
    if not api_cfg or not api_cfg.has_binance_credentials:
        raise ValueError("Missing Binance API credentials in environment variables")
    return UMFutures(key=api_cfg.binance_api_key, secret=api_cfg.binance_secret)


def setup_trading_mode(um: UMFutures):
    """
    🔧 Setup trading mode: One-way positions (not hedge mode)
    """
    try:
        mode = retry_call(um.get_position_mode)
        if isinstance(mode, dict):
            dual = bool(mode.get("dualSidePosition", False))
            if dual:
                retry_call(um.change_position_mode, dualSidePosition=False)
                print("- Switched position mode to One-way")
    except Exception as e:
        # Non-fatal
        print(f"! Could not verify/set position mode: {e}")


def get_available_usdt(um: UMFutures) -> float:
    """Get available USDT balance from futures account"""
    bals = retry_call(um.balance)
    if not isinstance(bals, list):
        return 0.0
    for b in bals:
        if isinstance(b, dict) and b.get("asset") == "USDT":
            try:
                return float(b.get("availableBalance", b.get("balance", 0.0)))
            except Exception:
                try:
                    return float(b.get("balance", 0.0))
                except Exception:
                    return 0.0
    return 0.0


def get_mark_price(um: UMFutures, symbol: str) -> float:
    """Get current mark price for symbol"""
    data = retry_call(um.mark_price, symbol=symbol)
    try:
        if isinstance(data, dict):
            mp = data.get("markPrice", 0.0)
            return float(mp if mp is not None else 0.0)
    except Exception:
        pass
    # Fallback via ticker price if needed
    ticker = retry_call(um.ticker_price, symbol=symbol)
    if isinstance(ticker, dict):
        return float(ticker.get("price", 0.0))
    return 0.0


def get_exchange_filters(um: UMFutures) -> Dict[str, Dict[str, Any]]:
    """Get exchange filters for all symbols"""
    info = retry_call(um.exchange_info)
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(info, dict):
        return out
    for s in info.get("symbols", []) or []:
        sym = s.get("symbol")
        filters_list = s.get("filters", []) or []
        filt: Dict[str, Any] = {str(f.get("filterType")): f for f in filters_list if isinstance(f, dict) and isinstance(f.get("filterType"), str)}
        if isinstance(sym, str) and sym:
            out[sym] = filt
    return out


def get_high_volume_symbols(um: UMFutures, min_volume_usdt: float = 10_000_000) -> List[str]:
    """
    🔍 Dynamic Coin Discovery: ค้นหาเหรียญใน Binance Futures ที่มี 24h volume > $10,000,000
    🎲 Random Shuffling: สับไพ่เหรียญที่ผ่านเกณฑ์เพื่อกระจายโอกาส
    """
    try:
        # ดึงข้อมูล 24h ticker statistics
        tickers = retry_call(um.ticker_24hr_price_change)
        if not isinstance(tickers, list):
            print("! Failed to get 24h ticker data, no symbols available")
            return []
        
        high_volume_symbols = []
        
        for ticker in tickers:
            if not isinstance(ticker, dict):
                continue
                
            symbol = ticker.get("symbol", "")
            quote_volume = ticker.get("quoteVolume", "0")
            
            try:
                # ตรวจสอบว่าเป็น USDT pair และ volume สูงกว่าเกณฑ์
                if (symbol.endswith("USDT") and 
                    float(quote_volume) >= min_volume_usdt and
                    symbol not in ["USDCUSDT", "BUSDUSDT", "TUSDUSDT"]):  # หลีกเลี่ยง stablecoin pairs
                    
                    high_volume_symbols.append(symbol)
                    
            except (ValueError, TypeError):
                continue  # Skip invalid volume data
        
        # 🎲 สุ่มลำดับเพื่อกระจายโอกาส
        random.shuffle(high_volume_symbols)
        
        print(f"🔍 Found {len(high_volume_symbols)} symbols with volume > ${min_volume_usdt:,.0f}")
        return high_volume_symbols
        
    except Exception as e:
        print(f"! Error getting high volume symbols: {e}")
        return []


def get_klines(um: UMFutures, symbol: str, interval: str = "1h", limit: int = 200) -> List[List]:
    """Get klines data for symbol"""
    try:
        data = retry_call(um.klines, symbol=symbol, interval=interval, limit=limit)
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"! Error getting klines for {symbol}: {e}")
    return []


def get_current_positions(um: UMFutures) -> List[Dict[str, Any]]:
    """Get current open positions"""
    try:
        positions = retry_call(um.get_position_risk)
        if isinstance(positions, list):
            return [p for p in positions if isinstance(p, dict) and safe_float(p.get("positionAmt", "0")) != 0.0]
    except Exception as e:
        print(f"! Error getting positions: {e}")
    return []


def place_order(um: UMFutures, symbol: str, side: str, quantity: float, order_type: str = "MARKET", 
                price: Optional[float] = None, time_in_force: Optional[str] = None) -> Optional[Dict]:
    """Place order with detailed error handling"""
    try:
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity
        }
        
        if order_type == "LIMIT" and price is not None:
            params["price"] = price
            params["timeInForce"] = time_in_force or "GTC"
        
        print(f"🔄 Placing {side} order for {symbol}: qty={quantity}")
        result = retry_call(um.new_order, **params)
        print(f"✅ Order placed successfully for {symbol}")
        return result
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Failed to place {side} order for {symbol}")
        print(f"   Error: {error_msg}")
        print(f"   Quantity: {quantity}")
        
        # Check common error patterns
        if "LOT_SIZE" in error_msg:
            print(f"   💡 Possible fix: Check minimum quantity requirements")
        elif "MIN_NOTIONAL" in error_msg:
            print(f"   💡 Possible fix: Order value too small, increase quantity")
        elif "INSUFFICIENT_BALANCE" in error_msg:
            print(f"   💡 Possible fix: Not enough margin balance")
        elif "MARKET_CLOSED" in error_msg:
            print(f"   💡 Possible fix: Market is closed or suspended")
        
        return None


def set_margin_type(um: UMFutures, symbol: str, margin_type: str = "CROSSED"):
    """Set margin type for symbol with better error handling"""
    try:
        retry_call(um.change_margin_type, symbol=symbol, marginType=margin_type)
        print(f"✅ {symbol}: Set to {margin_type} margin")
    except Exception as e:
        error_msg = str(e)
        if "No need to change margin type" in error_msg:
            print(f"ℹ️ {symbol}: Already in {margin_type} margin mode")
        else:
            print(f"⚠️ {symbol}: Failed to set margin type - {error_msg}")


def set_leverage(um: UMFutures, symbol: str, leverage: int):
    """Set leverage for symbol with better error handling"""
    try:
        retry_call(um.change_leverage, symbol=symbol, leverage=leverage)
        print(f"✅ {symbol}: Set leverage to {leverage}x")
    except Exception as e:
        error_msg = str(e)
        if "leverage not modified" in error_msg:
            print(f"ℹ️ {symbol}: Already at {leverage}x leverage")
        else:
            print(f"⚠️ {symbol}: Failed to set leverage - {error_msg}")
    except Exception as e:
        print(f"! change_leverage failed for {symbol}: {e}")


def get_open_orders(um: UMFutures, symbol: str = None) -> List[Dict]:
    """Get open orders for symbol or all symbols"""
    try:
        if symbol:
            # Try different methods to get open orders for a specific symbol
            try:
                orders = retry_call(um.get_open_orders, symbol=symbol, recvWindow=60000)
            except:
                # Fallback: get recent orders and filter for open status
                try:
                    all_orders = retry_call(um.get_all_orders, symbol=symbol, limit=10)
                    orders = [order for order in all_orders if order.get('status') == 'NEW']
                except:
                    orders = []
        else:
            # This might not work for all API versions
            orders = retry_call(um.get_open_orders)
        
        if isinstance(orders, list):
            return orders
    except Exception as e:
        print(f"! Error getting open orders: {e}")
    return []


def cancel_order(um: UMFutures, symbol: str, order_id: str) -> bool:
    """Cancel specific order"""
    try:
        result = retry_call(um.cancel_order, symbol=symbol, orderId=order_id)
        print(f"✅ Cancelled order {order_id} for {symbol}")
        return True
    except Exception as e:
        print(f"! Error cancelling order {order_id} for {symbol}: {e}")
        return False


def get_order_status(um: UMFutures, symbol: str, order_id: str) -> Optional[Dict]:
    """Get specific order status"""
    try:
        result = retry_call(um.query_order, symbol=symbol, orderId=order_id)
        return result
    except Exception as e:
        print(f"! Error getting order status {order_id} for {symbol}: {e}")
        return None


def find_nearest_support_resistance(ohlc_data: List, current_price: float, is_long: bool) -> float:
    """Find nearest support (for LONG) or resistance (for SHORT) level"""
    try:
        if len(ohlc_data) < 10:
            # Fallback to percentage-based if insufficient data
            return current_price * 0.97 if is_long else current_price * 1.03
        
        # Extract highs and lows from OHLC data (last 30 candles for better accuracy)
        recent_candles = ohlc_data[-30:] if len(ohlc_data) >= 30 else ohlc_data
        highs = [float(candle[2]) for candle in recent_candles]
        lows = [float(candle[3]) for candle in recent_candles]
        
        if is_long:
            # For LONG: find nearest support (below current price with safety margin)
            # Look for significant lows that are at least 1% below current price
            min_distance = current_price * 0.99  # At least 1% below
            support_candidates = [low for low in lows if low < min_distance]
            
            if support_candidates:
                # Find the highest support (closest to current price but still safe)
                nearest_support = max(support_candidates)
                # Ensure it's at least 2% below current price for safety
                safe_support = min(nearest_support, current_price * 0.98)
                print(f"📊 {current_price:.4f} → Support found at {safe_support:.4f}")
                return safe_support
            else:
                # No suitable support found, use 3% below
                fallback = current_price * 0.97
                print(f"📊 No support found, using 3% below: {fallback:.4f}")
                return fallback
        else:
            # For SHORT: find nearest resistance (above current price with safety margin)
            # Look for significant highs that are at least 1% above current price
            max_distance = current_price * 1.01  # At least 1% above
            resistance_candidates = [high for high in highs if high > max_distance]
            
            if resistance_candidates:
                # Find the lowest resistance (closest to current price but still safe)
                nearest_resistance = min(resistance_candidates)
                # Ensure it's at least 2% above current price for safety
                safe_resistance = max(nearest_resistance, current_price * 1.02)
                print(f"📊 {current_price:.4f} → Resistance found at {safe_resistance:.4f}")
                return safe_resistance
            else:
                # No suitable resistance found, use 3% above
                fallback = current_price * 1.03
                print(f"📊 No resistance found, using 3% above: {fallback:.4f}")
                return fallback
                
    except Exception as e:
        print(f"⚠️ Error finding S/R levels: {e}")
        # Safe fallback
        return current_price * 0.97 if is_long else current_price * 1.03

def cancel_all_sl_tp_orders(um: UMFutures, symbol: str) -> bool:
    """Cancel all SL/TP orders for a symbol (cleanup function)"""
    try:
        orders = get_open_orders(um, symbol)
        cancelled_count = 0
        
        for order in orders:
            order_type = order.get('type', '')
            reduce_only = order.get('reduceOnly', False)
            
            # Cancel all reduce-only orders (SL/TP orders)
            if reduce_only and order_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET', 'LIMIT']:
                try:
                    result = retry_call(um.cancel_order, 
                                      symbol=symbol, 
                                      orderId=order.get('orderId'))
                    if result:
                        cancelled_count += 1
                        print(f"🗑️ Cancelled {order_type} order {order.get('orderId')} for {symbol}")
                except Exception as e:
                    print(f"❌ Failed to cancel order {order.get('orderId')}: {e}")
        
        if cancelled_count > 0:
            print(f"✅ {symbol}: Cancelled {cancelled_count} SL/TP orders")
            return True
        
        return True  # No orders to cancel is also success
        
    except Exception as e:
        print(f"! Error cancelling SL/TP orders for {symbol}: {e}")
        return False


def place_stop_loss_order(um: UMFutures, symbol: str, position_side: str, position_size: float, 
                         stop_price: float, filters: Dict[str, Dict[str, Any]], 
                         ohlc_data: List = None) -> bool:
    """Place stop loss order for existing position"""
    try:
        if position_size == 0:
            return True
        
        # Get current market price for validation
        try:
            current_price = get_mark_price(um, symbol)
            if current_price <= 0:
                print(f"❌ {symbol}: Cannot get current price for stop loss validation")
                return False
        except Exception as e:
            print(f"❌ {symbol}: Error getting current price: {e}")
            return False
        
        # Validate and adjust stop loss price using S/R levels if AI price is invalid
        is_long = position_side == "LONG"
        side = "SELL" if is_long else "BUY"
        
        if is_long:
            # LONG position: stop loss should be BELOW current price
            if stop_price >= current_price:
                print(f"❌ {symbol}: Invalid AI stop loss for LONG - ${stop_price:.4f} >= current ${current_price:.4f}")
                # Use nearest support level instead
                if ohlc_data:
                    stop_price = find_nearest_support_resistance(ohlc_data, current_price, True)
                    print(f"🔄 {symbol}: Auto-corrected to nearest support: ${stop_price:.4f}")
                else:
                    stop_price = current_price * 0.97  # 3% below as fallback
                    print(f"🔄 {symbol}: Auto-corrected to 3% below: ${stop_price:.4f}")
            
            # Double-check: ensure stop is definitively below current price
            if stop_price >= current_price * 0.999:  # Must be at least 0.1% below
                print(f"⚠️ {symbol}: Stop loss still too high, forcing 3% below current price")
                stop_price = current_price * 0.97
        else:
            # SHORT position: stop loss should be ABOVE current price  
            if stop_price <= current_price:
                print(f"❌ {symbol}: Invalid AI stop loss for SHORT - ${stop_price:.4f} <= current ${current_price:.4f}")
                # Use nearest resistance level instead
                if ohlc_data:
                    stop_price = find_nearest_support_resistance(ohlc_data, current_price, False)
                    print(f"🔄 {symbol}: Auto-corrected to nearest resistance: ${stop_price:.4f}")
                else:
                    stop_price = current_price * 1.03  # 3% above as fallback
                    print(f"🔄 {symbol}: Auto-corrected to 3% above: ${stop_price:.4f}")
            
            # Double-check: ensure stop is definitively above current price
            if stop_price <= current_price * 1.001:  # Must be at least 0.1% above
                print(f"⚠️ {symbol}: Stop loss still too low, forcing 3% above current price")
                stop_price = current_price * 1.03
        
        quantity = abs(position_size)
        
        # Use the same precise quantity calculation as main trading
        symbol_filters = filters.get(symbol, {})
        final_quantity = calculate_quantity_with_precision(quantity, symbol_filters)
        
        if final_quantity <= 0:
            print(f"❌ {symbol}: Invalid stop loss quantity: {final_quantity}")
            return False
        
        # Format stop price with safe precision for stop loss
        formatted_stop_price = format_stop_loss_price_with_precision(stop_price, symbol_filters, is_long)
        
        print(f"🛡️ {symbol}: AI Stop Loss = ${stop_price:.4f} → Formatted = ${formatted_stop_price}")
        print(f"🛡️ {symbol}: Placing {side} stop loss at ${formatted_stop_price} (current: ${current_price:.4f})")
        
        # Place stop market order
        result = retry_call(
            um.new_order,
            symbol=symbol,
            side=side,
            type="STOP_MARKET",
            quantity=final_quantity,
            stopPrice=formatted_stop_price,
            timeInForce="GTC",
            reduceOnly=True
        )
        
        if result:
            print(f"✅ {symbol}: Stop loss order placed at ${formatted_stop_price} (qty: {final_quantity})")
            return True
        return False
        
    except Exception as e:
        print(f"! Error placing stop loss for {symbol}: {e}")
        return False


def place_take_profit_order(um: UMFutures, symbol: str, position_side: str, position_size: float, 
                           take_profit_price: float, filters: Dict[str, Dict[str, Any]]) -> bool:
    """Place take profit order for existing position"""
    try:
        if position_size == 0:
            return True
        
        # Get current market price for validation
        try:
            current_price = get_mark_price(um, symbol)
            if current_price <= 0:
                print(f"❌ {symbol}: Cannot get current price for take profit validation")
                return False
        except Exception as e:
            print(f"❌ {symbol}: Error getting current price: {e}")
            return False
        
        # Validate and adjust take profit price
        is_long = position_side == "LONG"
        side = "SELL" if is_long else "BUY"
        
        if is_long:
            # LONG position: take profit should be ABOVE current price
            if take_profit_price <= current_price:
                print(f"❌ {symbol}: Invalid AI take profit for LONG - ${take_profit_price:.4f} <= current ${current_price:.4f}")
                # Auto-correct to 5% above current price
                take_profit_price = current_price * 1.05
                print(f"🔄 {symbol}: Auto-corrected to 5% above: ${take_profit_price:.4f}")
        else:
            # SHORT position: take profit should be BELOW current price  
            if take_profit_price >= current_price:
                print(f"❌ {symbol}: Invalid AI take profit for SHORT - ${take_profit_price:.4f} >= current ${current_price:.4f}")
                # Auto-correct to 5% below current price
                take_profit_price = current_price * 0.95
                print(f"🔄 {symbol}: Auto-corrected to 5% below: ${take_profit_price:.4f}")
        
        quantity = abs(position_size)
        
        # Use the same precise quantity calculation as main trading
        symbol_filters = filters.get(symbol, {})
        final_quantity = calculate_quantity_with_precision(quantity, symbol_filters)
        
        if final_quantity <= 0:
            print(f"❌ {symbol}: Invalid take profit quantity: {final_quantity}")
            return False
        
        # Format price with safe precision
        formatted_tp_price = format_stop_loss_price_with_precision(take_profit_price, symbol_filters, is_long)
        
        print(f"🎯 {symbol}: AI Take Profit = ${take_profit_price:.4f} → Formatted = ${formatted_tp_price}")
        print(f"🎯 {symbol}: Placing {side} take profit at ${formatted_tp_price} (current: ${current_price:.4f})")
        
        # Place take profit market order
        result = retry_call(
            um.new_order,
            symbol=symbol,
            side=side,
            type="TAKE_PROFIT_MARKET",
            quantity=final_quantity,
            stopPrice=formatted_tp_price,
            timeInForce="GTC",
            reduceOnly=True
        )
        
        if result:
            print(f"✅ {symbol}: Take profit order placed at ${formatted_tp_price} (qty: {final_quantity})")
            return True
        return False
        
    except Exception as e:
        print(f"! Error placing take profit for {symbol}: {e}")
        return False


def calculate_quantity_with_precision(quantity: float, symbol_filters: Dict[str, Any]) -> float:
    """Calculate quantity with precise decimal handling using step size"""
    try:
        if not symbol_filters:
            return quantity
        
        # Apply LOT_SIZE filter with precision
        lot_size = symbol_filters.get('LOT_SIZE', {})
        if lot_size:
            step_size = float(lot_size.get('stepSize', '0.001'))
            min_qty = float(lot_size.get('minQty', '0.001'))
            max_qty = float(lot_size.get('maxQty', '1000000'))
            
            # Calculate decimal places from step size
            step_str = str(step_size).rstrip('0').rstrip('.')
            if '.' in step_str:
                decimal_places = len(step_str.split('.')[1])
            else:
                decimal_places = 0
            
            # Round to step size with proper precision
            if step_size > 0:
                raw_qty = round(quantity / step_size) * step_size
                # Format with exact decimal places
                formatted_qty = float(f"{raw_qty:.{decimal_places}f}")
            else:
                formatted_qty = quantity
            
            # Apply min/max limits
            final_qty = max(min_qty, min(max_qty, formatted_qty))
            return final_qty
        
        return quantity
    except Exception as e:
        print(f"! Error calculating quantity precision: {e}")
        return quantity


def format_stop_loss_price_with_precision(price: float, symbol_filters: Dict[str, Any], is_long: bool) -> str:
    """Format stop loss price with precision and safe direction - Returns string to avoid scientific notation"""
    try:
        if not symbol_filters or price <= 0:
            print(f"! Warning: Invalid input - symbol_filters={bool(symbol_filters)}, price={price}")
            return f"{price:.8f}".rstrip('0').rstrip('.')
        
        # Apply PRICE_FILTER
        price_filter = symbol_filters.get('PRICE_FILTER', {})
        if price_filter:
            tick_size_str = price_filter.get('tickSize', '0.01')
            tick_size = float(tick_size_str)
            
            # DEBUG: Log the tick_size being used
            print(f"🔧 Debug: tick_size={tick_size} for price={price}")
            
            # Enhanced validation for tick_size vs price ranges
            if tick_size >= 1.0:
                if price < 1000:
                    print(f"⚠️ Warning: tick_size {tick_size} too large for price {price}, using 0.01")
                    tick_size = 0.01
            elif tick_size >= 0.1:
                if price < 100:
                    print(f"⚠️ Warning: tick_size {tick_size} too large for price {price}, using 0.001")
                    tick_size = 0.001
            elif tick_size >= 0.01:
                if price < 10:
                    print(f"⚠️ Warning: tick_size {tick_size} too large for price {price}, using 0.0001")
                    tick_size = 0.0001
            elif tick_size >= 0.001:
                if price < 1:
                    print(f"⚠️ Warning: tick_size {tick_size} too large for price {price}, using 0.00001")
                    tick_size = 0.00001
            
            if tick_size > 0:
                # Calculate decimal places from tick_size for rounding
                decimal_places = max(0, -int(math.floor(math.log10(tick_size))))
                
                # Round price to tick_size precision using decimal places
                formatted_price = round(price, decimal_places)
                
                # Ensure it aligns with tick_size boundaries
                rounded_ticks = round(formatted_price / tick_size)
                final_price = rounded_ticks * tick_size
                final_price = round(final_price, decimal_places)
                
                # Final validation: if formatted price is very different from original, keep original
                diff_percent = abs(final_price - price) / price * 100
                if diff_percent > 2:  # Stricter validation: More than 2% difference
                    print(f"⚠️ Warning: Formatted price {final_price} differs too much from {price} ({diff_percent:.1f}%), keeping original")
                    return f"{price:.8f}".rstrip('0').rstrip('.')
                
                # Ensure minimum positive price
                if final_price <= 0:
                    final_price = tick_size
                
                # Format as string with proper decimal places to avoid scientific notation
                price_str = f"{final_price:.{decimal_places}f}"
                print(f"✅ Formatted: {price} → {price_str} (tick_size={tick_size}, decimals={decimal_places})")
                return price_str
        
        # Fallback: format as string with up to 8 decimals, removing trailing zeros
        return f"{price:.8f}".rstrip('0').rstrip('.')
    except Exception as e:
        print(f"! Error formatting stop loss price precision: {e}")
        return f"{price:.8f}".rstrip('0').rstrip('.')

def format_price_with_precision(price: float, symbol_filters: Dict[str, Any]) -> float:
    """Format price with proper precision using PRICE_FILTER"""
    try:
        if not symbol_filters:
            return price
        
        # Apply PRICE_FILTER
        price_filter = symbol_filters.get('PRICE_FILTER', {})
        if price_filter:
            tick_size = float(price_filter.get('tickSize', '0.01'))
            
            # Calculate decimal places from tick size
            tick_str = str(tick_size).rstrip('0').rstrip('.')
            if '.' in tick_str:
                decimal_places = len(tick_str.split('.')[1])
            else:
                decimal_places = 0
            
            # Round to tick size with proper precision
            if tick_size > 0:
                raw_price = round(price / tick_size) * tick_size
                formatted_price = float(f"{raw_price:.{decimal_places}f}")
                return formatted_price
        
        return price
    except Exception as e:
        print(f"! Error formatting price precision: {e}")
        return price


def close_position(um: UMFutures, symbol: str, position_size: float) -> bool:
    """Close position by placing opposite market order"""
    try:
        if position_size == 0:
            return True
        
        # Determine side for closing
        side = "SELL" if position_size > 0 else "BUY"
        quantity = abs(position_size)
        
        result = place_order(um, symbol, side, quantity, "MARKET")
        if result:
            print(f"✅ Closed {symbol} position: {side} {quantity}")
            return True
        return False
        
    except Exception as e:
        print(f"! Error closing position for {symbol}: {e}")
        return False


def calculate_quantity(um: UMFutures, symbol: str, margin_usdt: float, current_price: float, 
                      leverage: int, filters: Dict[str, Dict[str, Any]]) -> float:
    """Calculate proper quantity based on margin, price, and leverage with precise decimal handling"""
    try:
        # Calculate notional value we can trade
        notional_usdt = margin_usdt * leverage
        print(f"📊 {symbol}: Notional=${notional_usdt:.2f} (${margin_usdt} × {leverage}x)")
        
        # Calculate raw quantity
        raw_qty = notional_usdt / current_price
        print(f"📊 {symbol}: Raw quantity={raw_qty:.8f} (${notional_usdt}/{current_price})")
        
        # Apply LOT_SIZE filter
        symbol_filters = filters.get(symbol, {})
        lot_filter = symbol_filters.get("LOT_SIZE", {})
        
        if lot_filter:
            step_size = safe_float(lot_filter.get("stepSize", "1"))
            min_qty = safe_float(lot_filter.get("minQty", "0"))
            max_qty = safe_float(lot_filter.get("maxQty", "999999"))
            
            print(f"📊 {symbol}: LOT_SIZE filter - min={min_qty}, step={step_size}, max={max_qty}")
            
            # Round to step size with proper precision handling
            if step_size > 0:
                # Count decimal places in step_size to determine precision
                step_str = f"{step_size:.10f}".rstrip('0').rstrip('.')
                if '.' in step_str:
                    decimal_places = len(step_str.split('.')[1])
                else:
                    decimal_places = 0
                
                # Round down to step size and apply precision
                raw_qty = math.floor(raw_qty / step_size) * step_size
                raw_qty = round(raw_qty, decimal_places)
                print(f"📊 {symbol}: After step size rounding={raw_qty:.{decimal_places}f} (precision: {decimal_places})")
            
            # Ensure minimum quantity
            if raw_qty < min_qty:
                print(f"⚠️ {symbol}: Quantity {raw_qty:.8f} < minimum {min_qty}, adjusting to minimum")
                raw_qty = min_qty
                # Re-apply precision to minimum quantity
                if step_size > 0:
                    step_str = f"{step_size:.10f}".rstrip('0').rstrip('.')
                    if '.' in step_str:
                        decimal_places = len(step_str.split('.')[1])
                        raw_qty = round(raw_qty, decimal_places)
            
            # Check maximum quantity
            if raw_qty > max_qty:
                print(f"⚠️ {symbol}: Quantity {raw_qty:.8f} > maximum {max_qty}, adjusting to maximum")
                raw_qty = max_qty
        else:
            print(f"⚠️ {symbol}: No LOT_SIZE filter found in exchange info")
        
        # Check MIN_NOTIONAL filter
        min_notional_filter = symbol_filters.get("MIN_NOTIONAL", {})
        if min_notional_filter:
            min_notional = safe_float(min_notional_filter.get("notional", "0"))
            calculated_notional = raw_qty * current_price
            print(f"📊 {symbol}: MIN_NOTIONAL={min_notional}, calculated=${calculated_notional:.2f}")
            
            if calculated_notional < min_notional:
                print(f"⚠️ {symbol}: Order value ${calculated_notional:.2f} < minimum ${min_notional}")
                # Adjust quantity to meet minimum notional
                raw_qty = min_notional / current_price
                if step_size > 0:
                    # Apply step size rounding up to meet minimum notional
                    raw_qty = math.ceil(raw_qty / step_size) * step_size
                    # Re-apply precision
                    step_str = f"{step_size:.10f}".rstrip('0').rstrip('.')
                    if '.' in step_str:
                        decimal_places = len(step_str.split('.')[1])
                        raw_qty = round(raw_qty, decimal_places)
                print(f"📊 {symbol}: Adjusted quantity to {raw_qty:.8f} for MIN_NOTIONAL")
        
        print(f"✅ {symbol}: Final quantity={raw_qty:.8f}")
        return raw_qty
        
    except Exception as e:
        print(f"❌ Error calculating quantity for {symbol}: {e}")
        return 0.0


def cleanup_orphaned_orders(um: UMFutures, symbol: str = None) -> bool:
    """Clean up all orders that don't have corresponding positions (Auto Trading System)"""
    try:
        # Get all positions using existing function
        try:
            positions_response = retry_call(um.get_position_risk)
            if not positions_response:
                return True
        except Exception as e:
            print(f"! Error getting positions: {e}")
            return False
            
        active_symbols = set()
        
        for pos in positions_response:
            if abs(float(pos.get('positionAmt', 0))) > 1e-12:
                active_symbols.add(pos.get('symbol'))
        
        # Get all orders using direct REST API (more reliable than SDK)
        import requests
        import hmac
        import hashlib
        import time
        
        try:
            api_key = os.environ.get('BINANCE_API_KEY')
            secret_key = os.environ.get('BINANCE_SECRET_KEY')
            base_url = 'https://fapi.binance.com'
            
            timestamp = int(time.time() * 1000)
            query_string = f'timestamp={timestamp}'
            signature = hmac.new(
                secret_key.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            headers = {'X-MBX-APIKEY': api_key}
            params = {
                'timestamp': timestamp,
                'signature': signature
            }
            
            response = requests.get(f'{base_url}/fapi/v1/openOrders', headers=headers, params=params)
            if response.status_code != 200:
                print(f"! API Error getting orders: {response.text}")
                return False
            
            orders = response.json()
            
            # Group orders by symbol
            orders_by_symbol = {}
            for order in orders:
                symbol_name = order.get('symbol')
                if symbol_name not in orders_by_symbol:
                    orders_by_symbol[symbol_name] = []
                orders_by_symbol[symbol_name].append(order)
            
            # Find orphaned symbols (have orders but no positions)
            orphaned_symbols = set(orders_by_symbol.keys()) - active_symbols
            
            if not orphaned_symbols:
                print("✅ No orphaned orders found")
                return True
            
            print(f"🧹 Auto-cleanup: Found {len(orphaned_symbols)} symbols with orphaned orders")
            
            # Auto-cancel orphaned orders (no user confirmation needed for auto trading)
            canceled_count = 0
            for symbol_name in orphaned_symbols:
                orders_list = orders_by_symbol[symbol_name]
                print(f"   🗑️ Auto-canceling {len(orders_list)} orphaned orders for {symbol_name}")
                
                for order in orders_list:
                    order_id = str(order.get('orderId'))
                    try:
                        success = cancel_order(um, symbol_name, order_id)
                        if success:
                            canceled_count += 1
                    except Exception as e:
                        print(f"      ❌ Error canceling {order_id}: {e}")
            
            print(f"✅ Auto-cleanup completed: {canceled_count} orphaned orders removed from {len(orphaned_symbols)} symbols")
            return True
            
        except Exception as e:
            print(f"! Error in orphaned orders cleanup: {e}")
            return False
        
    except Exception as e:
        print(f"! Error in cleanup_orphaned_orders: {e}")
        return False
        
        # If specific symbol provided, check only that symbol
        if symbol:
            symbols_to_check = [symbol]
        else:
            # Since get_open_orders() requires symbol parameter, we need to check specific symbols
            all_orders = []
            symbols_to_check_for_orders = set()
            
            # Add symbols with active positions (they should have orders)
            for pos in positions_response:
                sym = pos.get('symbol')
                if sym:
                    symbols_to_check_for_orders.add(sym)
            
            # Add symbols that commonly have orphaned orders
            # Based on common trading pairs and user's trading history
            commonly_traded = [
                'WLDUSDT', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT', 'XRPUSDT', 
                'DOTUSDT', 'LINKUSDT', 'UNIUSDT', 'LTCUSDT', 'BCHUSDT', 'XLMUSDT', 'VETUSDT',
                'TRXUSDT', 'EOSUSDT', 'ATOMUSDT', 'MKRUSDT', 'COMPUSDT', 'AAVEUSDT',
                'DOGEUSDT', 'SHIBUSDT', 'PEPEUSDT', 'FLOKIUSDT', 'WIFUSDT', 'BONKUSDT',
                'SUIUSDT', 'APTUSDT', 'OPUSDT', 'ARBUSDT', 'MATICUSDT', 'AVAXUSDT'
            ]
            
            for sym in commonly_traded:
                symbols_to_check_for_orders.add(sym)
            
            print(f"� Checking {len(symbols_to_check_for_orders)} symbols for orders...")
            
            symbols_with_orders = set()
            total_orders_found = 0
            
            for sym in symbols_to_check_for_orders:
                try:
                    # Try different API methods to get orders
                    symbol_orders = []
                    
                    # Method 1: Try with recvWindow parameter
                    try:
                        symbol_orders = um.get_open_orders(symbol=sym, recvWindow=60000)
                    except:
                        # Method 2: Try get_all_orders with limit and filter for open orders
                        try:
                            all_orders = um.get_all_orders(symbol=sym, limit=10)
                            symbol_orders = [order for order in all_orders if order.get('status') == 'NEW']
                        except:
                            symbol_orders = []
                    
                    if symbol_orders:
                        symbols_with_orders.add(sym)
                        all_orders.extend(symbol_orders)
                        total_orders_found += len(symbol_orders)
                        print(f"   📝 {sym}: {len(symbol_orders)} orders")
                except Exception as e:
                    # Skip symbols that error out (normal for symbols with no orders)
                    continue
            
            print(f"🔍 Found {total_orders_found} total orders across {len(symbols_with_orders)} symbols")
            
            if not all_orders:
                print("📝 No open orders found")
                return True
            
            # Get all symbols that have any open orders and categorize them
            order_details = {}
            
            for order in all_orders:
                sym = order.get('symbol')
                if sym:
                    if sym not in order_details:
                        order_details[sym] = []
                    order_details[sym].append({
                        'orderId': order.get('orderId'),
                        'type': order.get('type'),
                        'side': order.get('side'),
                        'reduceOnly': order.get('reduceOnly', False)
                    })
            
            symbols_to_check = list(symbols_with_orders)
            
            if order_details:
                print(f"� Order Summary:")
                for sym, orders in order_details.items():
                    order_types = [f"{o['type']}({o['side']})" for o in orders]
                    print(f"   {sym}: {order_types}")
        
        cleaned_count = 0
        total_orders_cancelled = 0
        
        for sym in symbols_to_check:
            # If symbol has no active position, cancel ALL orders for that symbol
            if sym not in active_symbols:
                print(f"🗑️ {sym}: No position found, cancelling all orders...")
                
                # Cancel all orders for this symbol
                orders_cancelled = cancel_all_orders_for_symbol(um, sym)
                if orders_cancelled > 0:
                    cleaned_count += 1
                    total_orders_cancelled += orders_cancelled
                    print(f"✅ {sym}: Cancelled {orders_cancelled} orphaned orders")
            else:
                print(f"✅ {sym}: Has position - keeping orders")
        
        if cleaned_count > 0:
            print(f"🧹 Cleaned up {cleaned_count} symbols, cancelled {total_orders_cancelled} total orphaned orders")
        else:
            print("✅ No orphaned orders found")
        
        return True
        
    except Exception as e:
        print(f"! Error cleaning up orphaned orders: {e}")
        return False


def cancel_all_orders_for_symbol(um: UMFutures, symbol: str) -> int:
    """Cancel ALL orders for a symbol (not just SL/TP)"""
    try:
        orders = get_open_orders(um, symbol)
        cancelled_count = 0
        
        for order in orders:
            try:
                result = retry_call(um.cancel_order, 
                                  symbol=symbol, 
                                  orderId=order.get('orderId'))
                if result:
                    cancelled_count += 1
                    order_type = order.get('type', 'UNKNOWN')
                    order_side = order.get('side', 'UNKNOWN')
                    reduce_only = order.get('reduceOnly', False)
                    print(f"🗑️ Cancelled {order_type} {order_side} order {order.get('orderId')} {'(reduce-only)' if reduce_only else ''}")
            except Exception as e:
                print(f"❌ Failed to cancel order {order.get('orderId')}: {e}")
        
        return cancelled_count
        
    except Exception as e:
        print(f"! Error cancelling orders for {symbol}: {e}")
        return 0


def check_and_create_position_protection(um: UMFutures, symbol: str, filters: Dict) -> Dict:
    """Check if position has SL/TP protection and create if missing using AI"""
    try:
        # Get position data
        position_response = retry_call(um.get_position_risk, symbol=symbol)
        if not position_response:
            return {
                'symbol': symbol,
                'has_position': False,
                'protection_created': False,
                'error': 'No position data'
            }
        
        position = position_response[0] if position_response else {}
        position_size = float(position.get('positionAmt', 0))
        
        # If no position, return
        if position_size == 0:
            return {
                'symbol': symbol,
                'has_position': False,
                'protection_created': False
            }
        
        # Check if already has SL/TP orders
        orders = get_open_orders(um, symbol)
        sl_count = 0
        tp_count = 0
        
        for order in orders:
            if order.get('reduceOnly'):
                order_type = order.get('type', '')
                if order_type in ['STOP_MARKET', 'STOP']:
                    sl_count += 1
                elif order_type in ['TAKE_PROFIT_MARKET', 'TAKE_PROFIT', 'LIMIT']:
                    tp_count += 1
        
        # If already has both SL and TP (at least 1 of each)
        if sl_count >= 1 and tp_count >= 1:
            print(f"✅ {symbol}: Already has SL/TP protection ({sl_count} SL, {tp_count} TP)")
            return {
                'symbol': symbol,
                'has_position': True,
                'protection_created': False,
                'already_protected': True
            }
        
        # If has excess orders, clean them up first
        if sl_count > 1 or tp_count > 1:
            print(f"🧹 {symbol}: Excess protection orders detected ({sl_count} SL, {tp_count} TP) - cleaning up...")
            
            # Get orders again for cleanup
            excess_cleaned = 0
            
            # Clean excess SL orders (keep newest)
            if sl_count > 1:
                sl_orders = [o for o in orders if o.get('reduceOnly') and o.get('type') in ['STOP_MARKET', 'STOP']]
                sl_orders.sort(key=lambda x: int(x.get('time', 0)))  # Sort by time
                for old_order in sl_orders[:-1]:  # Cancel all except newest
                    try:
                        um.cancel_order(symbol=symbol, orderId=old_order.get('orderId'))
                        excess_cleaned += 1
                        print(f"🗑️ Cancelled excess SL order {old_order.get('orderId')}")
                    except:
                        pass
            
            # Clean excess TP orders (keep newest)  
            if tp_count > 1:
                tp_orders = [o for o in orders if o.get('reduceOnly') and o.get('type') in ['TAKE_PROFIT_MARKET', 'TAKE_PROFIT', 'LIMIT']]
                tp_orders.sort(key=lambda x: int(x.get('time', 0)))  # Sort by time
                for old_order in tp_orders[:-1]:  # Cancel all except newest
                    try:
                        um.cancel_order(symbol=symbol, orderId=old_order.get('orderId'))
                        excess_cleaned += 1
                        print(f"🗑️ Cancelled excess TP order {old_order.get('orderId')}")
                    except:
                        pass
            
            if excess_cleaned > 0:
                print(f"✅ {symbol}: Cleaned {excess_cleaned} excess orders")
            
            # After cleanup, we should have protection
            return {
                'symbol': symbol,
                'has_position': True,
                'protection_created': False,
                'already_protected': True,
                'cleaned_excess': excess_cleaned
            }
        
        # Get position details
        entry_price = float(position.get('entryPrice', 0))
        mark_price = float(position.get('markPrice', 0))
        pnl = float(position.get('unRealizedProfit', 0))
        side = "LONG" if position_size > 0 else "SHORT"
        
        pnl_percent = (pnl / (abs(position_size) * entry_price) * 100) if entry_price and abs(position_size * entry_price) > 1e-12 else 0
        
        print(f"🛡️ {symbol}: Missing protection - requesting from AI...")
        print(f"   Position: {side} {abs(position_size):.6f} @ ${entry_price:.6f}")
        print(f"   Current: ${mark_price:.6f}, PNL: ${pnl:.2f} ({pnl_percent:+.2f}%)")
        
        # Get OHLCV data for AI analysis
        from binance_client import get_klines
        from trading_engine import parse_klines_data
        
        klines = get_klines(um, symbol, "1h", 500)
        if not klines or len(klines) < 10:
            print(f"❌ {symbol}: Insufficient data for AI analysis")
            return {
                'symbol': symbol,
                'has_position': True,
                'protection_created': False,
                'error': 'Insufficient data'
            }
        
        data = parse_klines_data(klines)
        if not data["closes"]:
            print(f"❌ {symbol}: Failed to parse price data")
            return {
                'symbol': symbol,
                'has_position': True,
                'protection_created': False,
                'error': 'Data parsing failed'
            }
        
        # Get protection levels from AI
        from ai_client import get_position_protection_from_ai
        
        protection = get_position_protection_from_ai(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            current_price=mark_price,
            position_size=abs(position_size),
            pnl=pnl,
            pnl_percent=pnl_percent,
            data=data
        )
        
        if not protection:
            print(f"❌ {symbol}: Failed to get protection from AI")
            return {
                'symbol': symbol,
                'has_position': True,
                'protection_created': False,
                'error': 'AI protection failed'
            }
        
        stop_loss = protection['stop_loss']
        take_profit = protection['take_profit']
        
        # Validate prices
        if side == "LONG":
            if stop_loss >= entry_price or take_profit <= entry_price:
                print(f"❌ {symbol}: Invalid AI prices for LONG - SL={stop_loss}, TP={take_profit}, Entry={entry_price}")
                return {
                    'symbol': symbol,
                    'has_position': True,
                    'protection_created': False,
                    'error': 'Invalid AI prices'
                }
        else:  # SHORT
            if stop_loss <= entry_price or take_profit >= entry_price:
                print(f"❌ {symbol}: Invalid AI prices for SHORT - SL={stop_loss}, TP={take_profit}, Entry={entry_price}")
                return {
                    'symbol': symbol,
                    'has_position': True,
                    'protection_created': False,
                    'error': 'Invalid AI prices'
                }
        
        # Create missing SL/TP orders
        sl_success = False
        tp_success = False
        
        needs_sl = sl_count == 0
        needs_tp = tp_count == 0
        
        if needs_sl:
            sl_success = place_stop_loss_order(
                um, symbol, side, abs(position_size), stop_loss, filters
            )
            
        if needs_tp:
            tp_success = place_take_profit_order(
                um, symbol, side, abs(position_size), take_profit, filters
            )
        
        protection_created = (needs_sl and sl_success) or (needs_tp and tp_success)
        
        if protection_created:
            print(f"✅ {symbol}: Protection created - SL: ${stop_loss:.6f}, TP: ${take_profit:.6f}")
            print(f"💡 Reasoning: {protection.get('reasoning', 'N/A')}")
        
        return {
            'symbol': symbol,
            'has_position': True,
            'protection_created': protection_created,
            'stop_loss_created': needs_sl and sl_success,
            'take_profit_created': needs_tp and tp_success,
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
        
    except Exception as e:
        print(f"❌ Error creating protection for {symbol}: {e}")
        return {
            'symbol': symbol,
            'has_position': False,
            'protection_created': False,
            'error': str(e)
        }


def check_and_cleanup_position(um: UMFutures, symbol: str) -> Dict:
    """Check position status and cleanup orders if position is closed"""
    try:
        # Get position using existing method
        position_response = retry_call(um.get_position_risk, symbol=symbol)
        if not position_response:
            return {
                'symbol': symbol,
                'has_position': False,
                'position_size': 0,
                'cleanup_performed': False,
                'error': 'No position data'
            }
        
        position = position_response[0] if position_response else {}
        position_size = float(position.get('positionAmt', 0))
        
        result = {
            'symbol': symbol,
            'has_position': position_size != 0,
            'position_size': position_size,
            'cleanup_performed': False
        }
        
        # If no position exists, cleanup all SL/TP orders
        if position_size == 0:
            cleanup_success = cancel_all_sl_tp_orders(um, symbol)
            result['cleanup_performed'] = cleanup_success
            
            if cleanup_success:
                print(f"🔄 {symbol}: No position found, cleaned up pending orders")
        
        return result
        
    except Exception as e:
        print(f"! Error checking position for {symbol}: {e}")
        return {
            'symbol': symbol,
            'has_position': False,
            'position_size': 0,
            'cleanup_performed': False,
            'error': str(e)
        }
