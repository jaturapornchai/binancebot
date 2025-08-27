"""
Breakout Detection System - Pure Breakout Analysis (No EMA)
Detects price near breakout levels or already broken out
Based on resistance/support levels from last 3 timeframes
"""

from typing import List, Dict, Optional


class BreakoutAnalyzer:
    def __init__(self, 
                 lookback_frames: int = 3,           # ย้อนหลัง 3 timeframes สำหรับหา breakout
                 breakout_threshold: float = 0.01,   # 1% threshold สำหรับ "ใกล้ breakout"
                 volume_multiplier: float = 1.5):    # ตรวจจับ volume spike
        """
        Initialize Breakout analyzer (NO EMA System)
        
        Args:
            lookback_frames: ย้อนหลัง 3 timeframes สำหรับหา support/resistance
            breakout_threshold: Percentage threshold สำหรับ "ใกล้ breakout" 
            volume_multiplier: Volume multiplier สำหรับตรวจจับ volume spike
        """
        self.lookback_frames = lookback_frames
        self.breakout_threshold = breakout_threshold
        self.volume_multiplier = volume_multiplier

    def find_resistance_support_levels_12_frames(self, highs: List[float], 
                                               lows: List[float], 
                                               closes: List[float]) -> Dict:
        """หา resistance/support levels จาก 3 timeframes ล่าสุด"""
        if len(highs) < self.lookback_frames or len(lows) < self.lookback_frames:
            return {
                'resistance': None, 
                'support': None, 
                'current_price': None,
                'long_take_profit': None,
                'short_take_profit': None
            }
        
        # ใช้ 3 timeframes ล่าสุด
        recent_highs = highs[-self.lookback_frames:]
        recent_lows = lows[-self.lookback_frames:]
        
        # Find resistance (highest ใน 3 frames)
        resistance = max(recent_highs)
        
        # Find support (lowest ใน 3 frames)  
        support = min(recent_lows)
        
        # Current price
        current_price = closes[-1] if closes else None
        
        # Calculate take profit levels
        if current_price:
            # Take profit: 2% สำหรับ LONG/SHORT
            long_take_profit = resistance * 1.02  # 2% above resistance
            short_take_profit = support * 0.98    # 2% below support
        else:
            long_take_profit = short_take_profit = None
        
        return {
            'resistance': resistance,
            'support': support,
            'current_price': current_price,
            'long_take_profit': long_take_profit,
            'short_take_profit': short_take_profit
        }

    def detect_breakout_signal(self, ohlcv_data: List) -> Dict:
        """Detect breakout signals ย้อนหลัง 6 timeframes - Pure Breakout Analysis"""
        try:
            if len(ohlcv_data) < self.lookback_frames + 2:
                return {
                    'has_signal': False,
                    'signal_type': 'INSUFFICIENT_DATA',
                    'reason': f'ต้องการข้อมูล OHLCV อย่างน้อย {self.lookback_frames + 2} แท่ง'
                }
            
            # Extract OHLCV data
            highs = [float(candle[2]) for candle in ohlcv_data]
            lows = [float(candle[3]) for candle in ohlcv_data] 
            closes = [float(candle[4]) for candle in ohlcv_data]
            volumes = [float(candle[5]) for candle in ohlcv_data]
            
            # Find resistance/support levels ย้อนหลัง 12 frames
            levels = self.find_resistance_support_levels_12_frames(highs, lows, closes)
            
            if not levels['resistance'] or not levels['support'] or not levels['current_price']:
                return {
                    'has_signal': False,
                    'signal_type': 'LEVEL_CALCULATION_ERROR',
                    'reason': 'ไม่สามารถคำนวณ resistance/support levels ได้'
                }
            
            current_price = levels['current_price']
            resistance = levels['resistance']
            support = levels['support']
            
            # Check for breakout conditions
            resistance_breakout_threshold = resistance * (1 - self.breakout_threshold)  # ใกล้จะทะลุ resistance
            support_breakout_threshold = support * (1 + self.breakout_threshold)      # ใกล้จะทะลุ support
            
            # LONG Signal: ราคาทะลุ หรือ ใกล้จะทะลุ resistance
            if current_price >= resistance or current_price >= resistance_breakout_threshold:
                return {
                    'has_signal': True,
                    'signal_type': 'LONG',
                    'buy_signal': True,
                    'sell_signal': False,
                    'current_price': current_price,
                    'resistance': resistance,
                    'support': support,
                    'stop_loss': support * 0.97,  # Stop loss = support - 3%
                    'take_profit': levels['long_take_profit'],
                    'reason': f'Bullish Breakout: Price ${current_price:.4f} {"broke above" if current_price >= resistance else "near"} resistance ${resistance:.4f}'
                }
            
            # SHORT Signal: ราคาทะลุ หรือ ใกล้จะทะลุ support
            elif current_price <= support or current_price <= support_breakout_threshold:
                return {
                    'has_signal': True,
                    'signal_type': 'SHORT',
                    'buy_signal': False,
                    'sell_signal': True,
                    'current_price': current_price,
                    'resistance': resistance,
                    'support': support,
                    'stop_loss': resistance * 1.03,  # Stop loss = resistance + 3%
                    'take_profit': levels['short_take_profit'],
                    'reason': f'Bearish Breakout: Price ${current_price:.4f} {"broke below" if current_price <= support else "near"} support ${support:.4f}'
                }
            
            # HOLD: ไม่มี breakout signal ชัดเจน
            else:
                return {
                    'has_signal': True,
                    'signal_type': 'HOLD',
                    'buy_signal': False,
                    'sell_signal': False,
                    'current_price': current_price,
                    'resistance': resistance,
                    'support': support,
                    'reason': f'No clear breakout: Price ${current_price:.4f} between support ${support:.4f} and resistance ${resistance:.4f}'
                }
                
        except Exception as e:
            return {
                'has_signal': False,
                'signal_type': 'ERROR',
                'reason': f'Breakout analysis error: {str(e)}'
            }


def is_breakout_signal_valid(ohlcv_data: List, symbol: str = "") -> Dict:
    """
    🎯 Main function สำหรับตรวจจับ breakout signals
    
    Args:
        ohlcv_data: OHLCV data ย้อนหลัง (ควรมีอย่างน้อย 144 timeframes)
        symbol: Symbol name สำหรับ logging
    
    Returns:
        Dict: ผลลัพธ์การวิเคราะห์ breakout
    """
    if not ohlcv_data or len(ohlcv_data) < 8:
        print(f"❌ {symbol}: Insufficient OHLCV data for breakout analysis")
        return {
            'has_signal': False,
            'signal_type': 'INSUFFICIENT_DATA',
            'reason': 'Not enough OHLCV data for analysis'
        }
    
    # Initialize analyzer
    analyzer = BreakoutAnalyzer(
        lookback_frames=6,        # ย้อนหลัง 6 timeframes
        breakout_threshold=0.01,  # 1% threshold
        volume_multiplier=1.5     # Volume spike detection
    )
    
    # Detect breakout signal
    result = analyzer.detect_breakout_signal(ohlcv_data)
    
    # Logging
    if result.get('has_signal'):
        signal_type = result.get('signal_type', 'UNKNOWN')
        reason = result.get('reason', 'No reason provided')
        print(f"🎯 {symbol}: Breakout Analysis → {signal_type}")
        print(f"   Reason: {reason}")
        
        if signal_type in ['LONG', 'SHORT']:
            current_price = result.get('current_price', 0)
            resistance = result.get('resistance', 0)
            support = result.get('support', 0)
            stop_loss = result.get('stop_loss', 0)
            take_profit = result.get('take_profit', 0)
            
            print(f"   Current: ${current_price:.4f}")
            print(f"   Resistance: ${resistance:.4f} | Support: ${support:.4f}")
            print(f"   Stop Loss: ${stop_loss:.4f} | Take Profit: ${take_profit:.4f}")
    else:
        print(f"❌ {symbol}: No breakout signal - {result.get('reason', 'Unknown')}")
    
    return result
