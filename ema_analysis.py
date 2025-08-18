"""
📊 EMA Analysis and Color Detection
Handles EMA calculations and Robert Nance Pine Script color logic
"""

import math
from typing import Dict, List, Optional, Tuple


def calculate_ema(values: List[float], period: int) -> List[float]:
    """
    📈 Calculate Exponential Moving Average (EMA)
    Returns list of EMA values with same length as input
    """
    if not values or period <= 0:
        return []
    
    ema_values = []
    multiplier = 2.0 / (period + 1)
    
    # First EMA is SMA of first 'period' values
    if len(values) < period:
        return [0.0] * len(values)
    
    sma = sum(values[:period]) / period
    ema_values.append(sma)
    
    # Calculate remaining EMA values
    for i in range(period, len(values)):
        ema = (values[i] * multiplier) + (ema_values[-1] * (1 - multiplier))
        ema_values.append(ema)
    
    # Pad beginning with zeros to match input length
    return [0.0] * (period - 1) + ema_values


def get_ema_color(ema_values: List[float], index: int = -1) -> str:
    """
    🎨 Determine EMA color based on Robert Nance Pine Script logic
    Exact implementation of: mycolor = up ? green : down ? red : blue
    where up = out > out[1] and down = out < out[1]
    GREEN = Rising (Bullish)
    RED = Falling (Bearish) 
    BLUE = Sideways/Equal (Neutral)
    """
    if len(ema_values) < 2:
        return "BLUE"  # Default to BLUE if insufficient data
    
    if index == -1:
        index = len(ema_values) - 1
    
    if index < 1:
        return "BLUE"  # Default to BLUE if insufficient data
    
    current = ema_values[index]      # out
    previous = ema_values[index - 1] # out[1]
    
    # Exact Pine Script logic: up = out > out[1], down = out < out[1]
    up = current > previous
    down = current < previous
    
    # mycolor = up ? green : down ? red : blue
    if up:
        return "GREEN"
    elif down:
        return "RED"
    else:
        return "BLUE"  # Equal values = sideways


def is_ema_color_changed(symbol: str, data_1h: Dict) -> bool:
    """
    🎨 EMA Color Change Detection: ตรวจสอบการเปลี่ยนสี EMA8 เท่านั้น
    Returns True if EMA8 color changed (any color change)
    """
    try:
        closes = data_1h.get("closes", [])
        if len(closes) < 10:  # Need at least 10 candles for EMA8
            return False
        
        # คำนวณ EMA8
        ema8_values = calculate_ema(closes, 8)
        if len(ema8_values) < 2:
            return False
        
        # เช็คสี EMA8 ล่าสุด 2 แท่ง
        current_color = get_ema_color(ema8_values, -1)
        previous_color = get_ema_color(ema8_values, -2)
        
        # ตรวจสอบการเปลี่ยนสี (GREEN/RED/BLUE เท่านั้น)
        if current_color != previous_color:
            print(f"    🎨 EMA8 Color Change {symbol}: {previous_color} → {current_color}")
            print(f"       EMA Values: {ema8_values[-2]:.4f} → {ema8_values[-1]:.4f}")
            return True
        
        return False
        
    except Exception as e:
        print(f"! Error in EMA color detection for {symbol}: {e}")
        return False


def get_ema_analysis_text(symbol: str, data_1h: Dict, current_price: float) -> str:
    """
    Generate EMA analysis text for AI prompt
    Returns formatted text describing EMA color signals
    """
    try:
        closes = data_1h.get("closes", [])
        if len(closes) < 10:
            return "\n🎨 EMA8 COLOR: ข้อมูลไม่เพียงพอ\n"
        
        # คำนวณ EMA8
        ema8_values = calculate_ema(closes, 8)
        if len(ema8_values) < 3:
            return "\n🎨 EMA8 COLOR: ข้อมูลไม่เพียงพอ\n"
        
        # เช็คสี EMA8
        current_color = get_ema_color(ema8_values, -1)
        previous_color = get_ema_color(ema8_values, -2)
        
        ema_color_info = ""
        
        if current_color != previous_color:
            # มีการเปลี่ยนสี
            ema_color_info += f"\n🎨 EMA8 COLOR SIGNAL: {previous_color} → {current_color}\n"
            ema_color_info += "สัญญาณเปลี่ยนสี EMA8 ตามแนวคิด Pine Script ของ Robert Nance\n"
            
            if current_color == "GREEN":
                ema_color_info += "EMA กำลังขาขึ้น (Bullish Momentum)\n"
            elif current_color == "RED":
                ema_color_info += "EMA กำลังขาลง (Bearish Momentum)\n"
            elif current_color == "BLUE":
                ema_color_info += "EMA กำลัง sideways (Neutral Momentum)\n"
        else:
            ema_color_info = "\n🎨 EMA8 COLOR: ไม่มีการเปลี่ยนสี (No Signal)\n"
        
        return ema_color_info
        
    except Exception as e:
        return f"\n🎨 EMA8 COLOR: Error - {e}\n"


def format_ohlcv_data(data_1h: Dict) -> str:
    """
    Format OHLCV data for AI analysis prompt
    Returns formatted string with 1H timeframe data
    """
    ohlcv_data = ""
    
    try:
        # 1h data only
        ohlcv_data += "=== 1H TIMEFRAME ===\n"
        h1_opens = data_1h.get("opens", [])
        h1_highs = data_1h.get("highs", [])
        h1_lows = data_1h.get("lows", [])
        h1_closes = data_1h.get("closes", [])
        h1_volumes = data_1h.get("volumes", [])
        
        min_len = min(len(h1_opens), len(h1_highs), len(h1_lows), len(h1_closes), len(h1_volumes))
        for i in range(min_len):
            ohlcv_data += f"H{i+1}[{h1_opens[i]},{h1_highs[i]},{h1_lows[i]},{h1_closes[i]}]V{int(h1_volumes[i])}"
            if (i + 1) % 10 == 0:
                ohlcv_data += "\n"
            else:
                ohlcv_data += " "
        ohlcv_data += "\n\n"
        
    except Exception as e:
        ohlcv_data = f"Error formatting OHLCV data: {e}\n\n"
    
    return ohlcv_data
