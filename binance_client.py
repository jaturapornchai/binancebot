"""
💼 Binance Futures API client functions
Handles all Binance Futures API interactions
"""

import json
import math
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
    """Place order with proper parameters"""
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
        
        result = retry_call(um.new_order, **params)
        return result
    except Exception as e:
        print(f"! Error placing {side} order for {symbol}: {e}")
        return None


def set_margin_type(um: UMFutures, symbol: str, margin_type: str = "ISOLATED"):
    """Set margin type for symbol"""
    try:
        retry_call(um.change_margin_type, symbol=symbol, marginType=margin_type)
        print(f"- Set {symbol} to {margin_type} margin")
    except Exception as e:
        print(f"! change_margin_type failed for {symbol}: {e}")


def set_leverage(um: UMFutures, symbol: str, leverage: int):
    """Set leverage for symbol"""
    try:
        retry_call(um.change_leverage, symbol=symbol, leverage=leverage)
        print(f"- Set {symbol} leverage to {leverage}x")
    except Exception as e:
        print(f"! change_leverage failed for {symbol}: {e}")


def get_open_orders(um: UMFutures, symbol: str = None) -> List[Dict]:
    """Get open orders for symbol or all symbols"""
    try:
        if symbol:
            orders = retry_call(um.get_orders, symbol=symbol)
        else:
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
    """Calculate proper quantity based on margin, price, and leverage"""
    try:
        # Calculate notional value we can trade
        notional_usdt = margin_usdt * leverage
        
        # Calculate raw quantity
        raw_qty = notional_usdt / current_price
        
        # Apply LOT_SIZE filter
        symbol_filters = filters.get(symbol, {})
        lot_filter = symbol_filters.get("LOT_SIZE", {})
        
        if lot_filter:
            step_size = safe_float(lot_filter.get("stepSize", "1"))
            min_qty = safe_float(lot_filter.get("minQty", "0"))
            
            # Round to step size
            if step_size > 0:
                raw_qty = math.floor(raw_qty / step_size) * step_size
            
            # Ensure minimum quantity
            raw_qty = max(raw_qty, min_qty)
        
        return raw_qty
        
    except Exception as e:
        print(f"! Error calculating quantity for {symbol}: {e}")
        return 0.0
