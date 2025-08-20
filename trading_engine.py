"""
⚡ Trading Engine - Core trading execution logic
Handles position management and order execution
"""

import json
from typing import Dict, List, Optional

from binance.um_futures import UMFutures

from binance_client import (calculate_quantity, get_mark_price,
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
            
            # Get data (288 candles = 12 วัน สำหรับ EMA99 analysis)
            klines = get_klines_func(um, symbol, cfg.timeframe, 288)
            if not klines or len(klines) < 100:  # Need at least 100 candles for EMA99
                print(f"❌ {symbol}: Insufficient data for EMA99 (klines: {len(klines) if klines else 0})")
                continue
            
            # Parse klines data
            data = parse_klines_data(klines)
            if not data["closes"]:
                print(f"❌ {symbol}: Failed to parse klines data")
                continue
            
            # Check for RSI Divergence signal (ตรวจหา Bullish/Bearish Divergence ใน 12 แท่งย้อนหลัง)
            if not is_signal_func(symbol, klines):
                # แสดงสถานะ RSI Divergence ปัจจุบันสำหรับ debug (แสดงแค่ 5 เหรียญแรก)
                if symbols_checked <= 5:
                    try:
                        from rsi_divergence_analysis import RSIDivergenceAnalyzer
                        analyzer = RSIDivergenceAnalyzer()
                        
                        # Convert raw klines to proper format
                        klines_list = []
                        for kline in klines:
                            klines_list.append({
                                'open': str(kline[1]),
                                'high': str(kline[2]),
                                'low': str(kline[3]),
                                'close': str(kline[4]),
                                'volume': str(kline[5])
                            })
                        
                        result = analyzer.analyze_symbol(klines_list)
                        current_rsi = result.get('current_rsi', 0)
                        signal_type = result.get('signal_type', 'NO_SIGNAL')
                        recent_signals = len(result.get('recent_buy_signals', [])) + len(result.get('recent_sell_signals', []))
                        print(f"⚪ {symbol}: No RSI Divergence signal (RSI: {current_rsi:.1f}, Recent signals: {recent_signals}, Status: {signal_type})")
                    except Exception as e:
                        print(f"⚪ {symbol}: No RSI Divergence signal")
                else:
                    print(f"⚪ {symbol}: No RSI Divergence signal")
                continue
            
            # Signal detected!
            print(f"🎯 SIGNAL DETECTED: {symbol} - Processing with AI...")
            symbols_with_signals += 1
            
            # Get current price
            current_price = get_mark_price(um, symbol)
            if current_price <= 0:
                print(f"❌ {symbol}: Invalid price: {current_price}")
                continue
            
            # Analyze with AI (with retry)
            ai_decision = None
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    ai_decision = analyze_func(symbol, data, current_price)
                    if ai_decision:
                        break
                    else:
                        if attempt < max_retries - 1:
                            print(f"🔄 {symbol}: AI attempt {attempt + 1} failed, retrying...")
                            import time
                            time.sleep(2)  # Wait 2 seconds before retry
                except Exception as e:
                    print(f"❌ {symbol}: AI analysis error attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(2)
            
            if not ai_decision:
                print(f"❌ {symbol}: AI analysis failed after {max_retries} attempts")
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
        "symbols_skipped": symbols_skipped,
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


def print_scan_summary(results: Dict, um=None):
    """Print final scan summary with balance info"""
    print("=" * 60)
    print(f"📊 SCAN COMPLETE:")
    print(f"   Total symbols available: {results['total_symbols']}")  
    print(f"   Symbols scanned: {results['symbols_checked']}")
    print(f"   Symbols skipped (existing positions): {results.get('symbols_skipped', 0)}")
    print(f"   Signals detected: {results['signals_found']}")
    print(f"   Completion rate: {results['completion_rate']:.1f}%")
    
    # Show balance status
    if um:
        try:
            from binance_client import get_available_usdt
            from config import cfg
            available_usdt = get_available_usdt(um)
            print(f"   Current balance: ${available_usdt:.2f} (Min required: ${cfg.min_balance_usdt})")
            if available_usdt < cfg.min_balance_usdt:
                print(f"   ⚠️ Balance below minimum - trading suspended")
        except Exception as e:
            print(f"   ❌ Could not fetch balance: {e}")
    
    print("=" * 60)
