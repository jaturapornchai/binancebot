"""
📊 MACD Analysis and Signal Detection
Handles MACD calculations and color-based trading signals
"""

import math
from typing import Dict, List, Optional, Tuple


def calculate_ema(values: List[float], period: int) -> List[float]:
    """
    📈 Calculate Exponential Moving Average for MACD
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


def calculate_macd(closes: List[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[List[float], List[float], List[float]]:
    """
    📊 Calculate MACD (Moving Average Convergence Divergence)
    Returns: (macd_line, signal_line, histogram)
    """
    if len(closes) < slow_period:
        return [], [], []
    
    # Calculate EMAs
    ema_fast = calculate_ema(closes, fast_period)
    ema_slow = calculate_ema(closes, slow_period)
    
    # Calculate MACD line
    macd_line = []
    for i in range(len(closes)):
        if ema_fast[i] == 0.0 or ema_slow[i] == 0.0:
            macd_line.append(0.0)
        else:
            macd_line.append(ema_fast[i] - ema_slow[i])
    
    # Calculate Signal line (EMA of MACD)
    signal_line = calculate_ema(macd_line, signal_period)
    
    # Calculate Histogram
    histogram = []
    for i in range(len(macd_line)):
        if signal_line[i] == 0.0:
            histogram.append(0.0)
        else:
            histogram.append(macd_line[i] - signal_line[i])
    
    return macd_line, signal_line, histogram


def get_macd_color(macd_line: List[float], index: int = -1) -> str:
    """
    🎨 Determine MACD color based on position relative to zero
    GREEN = Above 0 (Long/Bullish)
    RED = Below 0 (Short/Bearish)
    """
    if not macd_line or len(macd_line) == 0:
        return "RED"  # Default to RED if no data
    
    if index == -1:
        index = len(macd_line) - 1
    
    macd_value = macd_line[index]
    
    if macd_value > 0:
        return "GREEN"  # Long signal
    else:
        return "RED"    # Short signal


def is_macd_color_changed(symbol: str, data_1h: Dict) -> bool:
    """
    🔄 Check if MACD color changed from previous candle
    Returns True if MACD crossed zero line (color change)
    """
    closes = data_1h.get("closes", [])
    
    if len(closes) < 30:  # Need enough data for MACD calculation
        return False
    
    try:
        macd_line, _, _ = calculate_macd(closes)
        
        if len(macd_line) < 2:
            return False
        
        current_color = get_macd_color(macd_line, -1)
        previous_color = get_macd_color(macd_line, -2)
        
        # Signal when color changes (MACD crosses zero line)
        return current_color != previous_color
        
    except Exception as e:
        print(f"❌ Error calculating MACD for {symbol}: {e}")
        return False


def get_macd_analysis_text(symbol: str, data_1h: Dict, current_price: float) -> str:
    """
    📝 Generate MACD analysis text for AI prompt
    """
    closes = data_1h.get("closes", [])
    
    if len(closes) < 30:
        return f"MACD: ไม่สามารถคำนวณได้ (ข้อมูลไม่เพียงพอ)"
    
    try:
        macd_line, signal_line, histogram = calculate_macd(closes)
        
        if len(macd_line) < 2:
            return f"MACD: ไม่สามารถคำนวณได้"
        
        current_macd = macd_line[-1]
        previous_macd = macd_line[-2]
        current_signal = signal_line[-1]
        current_histogram = histogram[-1]
        
        current_color = get_macd_color(macd_line, -1)
        previous_color = get_macd_color(macd_line, -2)
        
        # Trend analysis
        if current_macd > previous_macd:
            trend = "กำลังเพิ่มขึ้น"
        elif current_macd < previous_macd:
            trend = "กำลังลดลง"
        else:
            trend = "คงที่"
        
        # Color change detection
        color_change = ""
        if current_color != previous_color:
            color_change = f" (เปลี่ยนจาก {previous_color} เป็น {current_color})"
        
        return f"""MACD Analysis:
- MACD Line: {current_macd:.6f} ({trend}){color_change}
- Signal Line: {current_signal:.6f}
- Histogram: {current_histogram:.6f}
- สถานะ: {current_color} ({'Long' if current_color == 'GREEN' else 'Short'})
- ข้อมูล: MACD {'อยู่เหนือ' if current_macd > 0 else 'อยู่ใต้'} เส้นศูนย์"""
        
    except Exception as e:
        return f"MACD: เกิดข้อผิดพลาด - {e}"


def format_ohlcv_data(data_1h: Dict) -> str:
    """
    📋 Format OHLCV data for analysis (last 10 candles)
    """
    opens = data_1h.get("opens", [])
    highs = data_1h.get("highs", [])
    lows = data_1h.get("lows", [])
    closes = data_1h.get("closes", [])
    volumes = data_1h.get("volumes", [])
    
    if not all([opens, highs, lows, closes, volumes]):
        return "ไม่มีข้อมูล OHLCV"
    
    # Get last 10 candles
    last_10 = min(10, len(closes))
    result = "OHLCV ข้อมูล 10 แท่งล่าสุด:\n"
    
    for i in range(-last_10, 0):
        result += f"แท่ง{abs(i)}: O={opens[i]:.4f} H={highs[i]:.4f} L={lows[i]:.4f} C={closes[i]:.4f} V={volumes[i]:.0f}\n"
    
    return result


def get_macd_signal_strength(symbol: str, data_1h: Dict) -> float:
    """
    💪 Calculate MACD signal strength (0.0 to 1.0)
    Higher values indicate stronger signals
    """
    closes = data_1h.get("closes", [])
    
    if len(closes) < 30:
        return 0.0
    
    try:
        macd_line, signal_line, histogram = calculate_macd(closes)
        
        if len(macd_line) < 2:
            return 0.0
        
        current_macd = abs(macd_line[-1])
        current_histogram = abs(histogram[-1])
        
        # Calculate volatility for normalization
        recent_closes = closes[-20:]
        volatility = max(recent_closes) - min(recent_closes)
        
        if volatility == 0:
            return 0.0
        
        # Normalize signal strength (0.0 to 1.0)
        macd_strength = min(current_macd / (volatility * 0.01), 1.0)
        histogram_strength = min(current_histogram / (volatility * 0.01), 1.0)
        
        # Combined strength
        return (macd_strength + histogram_strength) / 2.0
        
    except Exception:
        return 0.0
