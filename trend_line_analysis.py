"""
HarryBot Trend Line Analysis - Python Implementation
Based on Pine Script by HarryBot
© 2025 - Trend Line Detection and Crossing Analysis
"""

import math
from typing import List, Dict, Tuple, Optional

class TrendLineAnalyzer:
    def __init__(self, limit=100, segment=55, term=15):
        self.limit = limit      # Bars Limit
        self.segment = segment  # Segment Range  
        self.term = term       # Fractals Period
        self.mid = int(term / 2) + 1
        
    def calculate_angle(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Calculate angle between two points (Pine Script cal function)"""
        try:
            return math.atan((y2 - y1) / (x2 - x1)) / (math.pi) * 180
        except ZeroDivisionError:
            return 0.0
    
    def find_fractals(self, highs: List[float], lows: List[float]) -> Tuple[List[int], List[int]]:
        """Find fractal highs and lows"""
        if len(highs) < self.term or len(lows) < self.term:
            return [], []
            
        fractal_highs = []
        fractal_lows = []
        
        # Check for fractals (similar to ta.highest/ta.lowest in Pine Script)
        for i in range(self.mid, len(highs) - self.mid):
            # Check for fractal high
            is_high = True
            for j in range(i - self.mid, i + self.mid + 1):
                if j != i and highs[j] >= highs[i]:
                    is_high = False
                    break
            if is_high:
                fractal_highs.append(i)
                
            # Check for fractal low  
            is_low = True
            for j in range(i - self.mid, i + self.mid + 1):
                if j != i and lows[j] <= lows[i]:
                    is_low = False
                    break
            if is_low:
                fractal_lows.append(i)
                
        return fractal_highs, fractal_lows
    
    def find_trend_line(self, data: List[float], fractal_indices: List[int], is_upper: bool) -> Optional[Dict]:
        """Find best trend line from fractals (Pine Script draw function)"""
        if len(fractal_indices) < 2 or len(data) < self.segment:
            return None
            
        best_line = None
        min_angle = 90.0
        
        # Get recent data within limit
        recent_start = max(0, len(data) - self.limit)
        
        for i, frac_idx in enumerate(fractal_indices):
            if frac_idx < recent_start:
                continue
                
            for j in range(min(self.segment, len(data) - frac_idx)):
                current_idx = len(data) - 1 - j
                if current_idx <= frac_idx:
                    break
                    
                # Calculate angle
                angle = self.calculate_angle(frac_idx, data[frac_idx], current_idx, data[current_idx])
                angle = angle if is_upper else -angle
                
                if angle < min_angle:
                    min_angle = angle
                    best_line = {
                        'x1': frac_idx,
                        'y1': data[frac_idx], 
                        'x2': current_idx,
                        'y2': data[current_idx],
                        'angle': angle
                    }
                    
        return best_line
    
    def get_line_price_at_index(self, line: Dict, index: int) -> float:
        """Get trend line price at specific index"""
        if not line:
            return 0.0
            
        x1, y1, x2, y2 = line['x1'], line['y1'], line['x2'], line['y2']
        
        if x2 == x1:
            return y1
            
        # Linear interpolation/extrapolation
        slope = (y2 - y1) / (x2 - x1)
        return y1 + slope * (index - x1)
    
    def check_line_crossing(self, closes: List[float], line: Dict) -> bool:
        """Check if candle crossed the trend line (HarryBot Alert condition)"""
        if not line or len(closes) < 2:
            return False
            
        current_idx = len(closes) - 1
        prev_idx = current_idx - 1
        
        # Get trend line prices
        current_line_price = self.get_line_price_at_index(line, current_idx)
        prev_line_price = self.get_line_price_at_index(line, prev_idx)
        
        # Get candle closes
        current_close = closes[current_idx]
        prev_close = closes[prev_idx]
        
        # Check crossing conditions (from Pine Script alertcondition)
        cross_up = prev_close < prev_line_price and current_close > current_line_price
        cross_down = prev_close > prev_line_price and current_close < current_line_price
        
        return cross_up or cross_down
    
    def analyze_symbol(self, kline_data: List[Dict]) -> Dict:
        """Main analysis function for a symbol"""
        if len(kline_data) < self.term * 2:
            return {'has_signal': False, 'reason': 'Insufficient data'}
            
        # Extract OHLC data
        opens = [float(k['open']) for k in kline_data]
        highs = [float(k['high']) for k in kline_data]  
        lows = [float(k['low']) for k in kline_data]
        closes = [float(k['close']) for k in kline_data]
        
        # Find fractals
        fractal_highs, fractal_lows = self.find_fractals(highs, lows)
        
        if not fractal_highs and not fractal_lows:
            return {'has_signal': False, 'reason': 'No fractals found'}
            
        # Find trend lines
        upper_line = None
        lower_line = None
        
        if fractal_highs:
            upper_line = self.find_trend_line(highs, fractal_highs, True)
            
        if fractal_lows:
            lower_line = self.find_trend_line(lows, fractal_lows, False)
            
        # Check for crossings
        upper_cross = False
        lower_cross = False
        
        if upper_line:
            upper_cross = self.check_line_crossing(closes, upper_line)
            
        if lower_line:
            lower_cross = self.check_line_crossing(closes, lower_line)
            
        has_signal = upper_cross or lower_cross
        
        result = {
            'has_signal': has_signal,
            'upper_line_cross': upper_cross,
            'lower_line_cross': lower_cross,
            'upper_line': upper_line,
            'lower_line': lower_line,
            'fractal_highs_count': len(fractal_highs),
            'fractal_lows_count': len(fractal_lows),
            'reason': 'Trend line crossing detected' if has_signal else 'No trend line crossing'
        }
        
        return result

def is_trend_line_signal_valid(symbol: str, kline_data) -> bool:
    """
    🎯 Check if trend line crossing signal is valid
    Pre-filter before AI analysis to save API calls
    """
    try:
        # Handle different input formats
        klines_list = []
        
        if isinstance(kline_data, dict) and 'opens' in kline_data:
            # Format from parse_klines_data (dict with arrays)
            opens = kline_data.get('opens', [])
            highs = kline_data.get('highs', [])
            lows = kline_data.get('lows', [])
            closes = kline_data.get('closes', [])
            volumes = kline_data.get('volumes', [])
            
            for i in range(len(opens)):
                klines_list.append({
                    'open': str(opens[i]),
                    'high': str(highs[i]),
                    'low': str(lows[i]),
                    'close': str(closes[i]),
                    'volume': str(volumes[i])
                })
        elif isinstance(kline_data, list):
            # Check if it's raw Binance format (list of lists)
            if len(kline_data) > 0 and isinstance(kline_data[0], list):
                # Raw Binance format: [timestamp, open, high, low, close, volume, ...]
                for kline in kline_data:
                    klines_list.append({
                        'open': str(kline[1]),
                        'high': str(kline[2]),
                        'low': str(kline[3]),
                        'close': str(kline[4]),
                        'volume': str(kline[5])
                    })
            else:
                # Already in dict format
                klines_list = kline_data
        
        if not klines_list:
            return False
            
        analyzer = TrendLineAnalyzer()
        result = analyzer.analyze_symbol(klines_list)
        return result['has_signal']
        
    except Exception as e:
        print(f"❌ Error analyzing trend line for {symbol}: {e}")
        return False

def get_trend_line_analysis_text(symbol: str, kline_data, current_price: float) -> str:
    """Generate trend line analysis text for AI prompt"""
    try:
        # Handle different input formats - same as is_trend_line_signal_valid
        klines_list = []
        
        if isinstance(kline_data, dict) and 'opens' in kline_data:
            opens = kline_data.get('opens', [])
            highs = kline_data.get('highs', [])
            lows = kline_data.get('lows', [])
            closes = kline_data.get('closes', [])
            volumes = kline_data.get('volumes', [])
            
            for i in range(len(opens)):
                klines_list.append({
                    'open': str(opens[i]),
                    'high': str(highs[i]),
                    'low': str(lows[i]),
                    'close': str(closes[i]),
                    'volume': str(volumes[i])
                })
        elif isinstance(kline_data, list):
            if len(kline_data) > 0 and isinstance(kline_data[0], list):
                # Raw Binance format
                for kline in kline_data:
                    klines_list.append({
                        'open': str(kline[1]),
                        'high': str(kline[2]),
                        'low': str(kline[3]),
                        'close': str(kline[4]),
                        'volume': str(kline[5])
                    })
            else:
                klines_list = kline_data
        
        if not klines_list:
            return f"\n❌ No data for {symbol}\n"
            
        analyzer = TrendLineAnalyzer()
        result = analyzer.analyze_symbol(klines_list)
        
        text = f"\n📈 TREND LINE ANALYSIS - {symbol}\n"
        text += f"Current Price: ${current_price}\n"
        text += f"Status: {result['reason']}\n"
        
        if result['has_signal']:
            text += f"🔴 SIGNAL: Trend Line Crossing Detected!\n"
            if result['upper_line_cross']:
                text += f"  - Upper trend line crossed\n"
            if result['lower_line_cross']:
                text += f"  - Lower trend line crossed\n"
        
        text += f"📊 Fractals: Highs({result['fractal_highs_count']}) Lows({result['fractal_lows_count']})\n"
        
        return text
        
    except Exception as e:
        return f"\n❌ Error generating trend line analysis for {symbol}: {e}\n"
