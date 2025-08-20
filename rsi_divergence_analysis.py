"""
RSI Divergence Analysis System
Based on Pine Script by Charles Edwards, 2019
Detects RSI divergence tops and bottoms with 12-timeframe lookback
"""

from typing import List, Dict, Optional

class RSIDivergenceAnalyzer:
    def __init__(self, 
                 rsi_period: int = 14,
                 overbought_level: float = 70.0,
                 oversold_level: float = 30.0,
                 top_rsi_threshold: float = 60.0,
                 bottom_rsi_threshold: float = 40.0):
        """
        Initialize RSI Divergence analyzer
        
        Args:
            rsi_period: RSI calculation period (default: 14)
            overbought_level: Overbought level (default: 70.0)
            oversold_level: Oversold level (default: 30.0)
            top_rsi_threshold: RSI threshold for top detection (default: 60.0)
            bottom_rsi_threshold: RSI threshold for bottom detection (default: 40.0)
        """
        self.rsi_period = rsi_period
        self.overbought_level = overbought_level
        self.oversold_level = oversold_level
        self.top_rsi_threshold = top_rsi_threshold
        self.bottom_rsi_threshold = bottom_rsi_threshold

    def calculate_rsi(self, prices: List[float], period: int) -> List[float]:
        """Calculate RSI (Relative Strength Index) using RMA method"""
        if len(prices) < period + 1:
            return []
        
        changes = []
        for i in range(1, len(prices)):
            changes.append(prices[i] - prices[i-1])
        
        gains = [max(change, 0) for change in changes]
        losses = [max(-change, 0) for change in changes]
        
        # Calculate RMA (Running Moving Average) - equivalent to Pine Script rma()
        rsi_values = []
        
        # Initial average
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        for i in range(period, len(gains)):
            if avg_loss == 0:
                rsi_values.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                rsi_values.append(rsi)
            
            # Update RMA
            alpha = 1.0 / period
            avg_gain = alpha * gains[i] + (1 - alpha) * avg_gain
            avg_loss = alpha * losses[i] + (1 - alpha) * avg_loss
        
        return rsi_values

    def detect_tops_bottoms(self, rsi_values: List[float]) -> Dict:
        """Detect RSI tops and bottoms based on Pine Script logic"""
        if len(rsi_values) < 5:
            return {'tops': [], 'bottoms': []}
        
        tops = []
        bottoms = []
        
        for i in range(4, len(rsi_values)):
            # RSI top detection logic (from Pine Script)
            # top := avg(rsi[4],rsi[3]) < rsi[2] 
            #        and avg(rsi,rsi[1]) < rsi[2] 
            #        and rsi[2] > 60
            #        and top[1] == false
            
            if i >= 4:
                avg_rsi_43 = (rsi_values[i-4] + rsi_values[i-3]) / 2
                avg_rsi_10 = (rsi_values[i] + rsi_values[i-1]) / 2
                rsi_2 = rsi_values[i-2]
                
                # Check if it's a top
                is_top = (avg_rsi_43 < rsi_2 and 
                         avg_rsi_10 < rsi_2 and 
                         rsi_2 > self.top_rsi_threshold)
                
                # Avoid consecutive tops
                if is_top and (not tops or i - tops[-1]['index'] > 1):
                    tops.append({
                        'index': i,
                        'rsi_value': rsi_2,
                        'bars_ago': len(rsi_values) - 1 - i
                    })
            
            # RSI bottom detection logic (from Pine Script)
            # bottom := avg(rsi[4],rsi[3]) > rsi[2] 
            #           and avg(rsi,rsi[1]) > rsi[2] 
            #           and rsi[2] < 40
            #           and bottom[1] == false
            
            if i >= 4:
                avg_rsi_43 = (rsi_values[i-4] + rsi_values[i-3]) / 2
                avg_rsi_10 = (rsi_values[i] + rsi_values[i-1]) / 2
                rsi_2 = rsi_values[i-2]
                
                # Check if it's a bottom
                is_bottom = (avg_rsi_43 > rsi_2 and 
                            avg_rsi_10 > rsi_2 and 
                            rsi_2 < self.bottom_rsi_threshold)
                
                # Avoid consecutive bottoms
                if is_bottom and (not bottoms or i - bottoms[-1]['index'] > 1):
                    bottoms.append({
                        'index': i,
                        'rsi_value': rsi_2,
                        'bars_ago': len(rsi_values) - 1 - i
                    })
        
        return {'tops': tops, 'bottoms': bottoms}

    def detect_divergence(self, rsi_values: List[float], prices: List[float], 
                         tops: List[Dict], bottoms: List[Dict]) -> Dict:
        """Detect RSI divergence signals"""
        buy_signals = []
        sell_signals = []
        
        # Detect sell signals (bearish divergence)
        # sell := top == true 
        #      and rsi[2] < valuewhen(top==true,rsi[2],1)
        #      and close[2] > valuewhen(top==true,close[2],1)
        
        for i, current_top in enumerate(tops[1:], 1):  # Start from second top
            prev_top = tops[i-1]
            current_idx = current_top['index']
            prev_idx = prev_top['index']
            
            current_rsi = rsi_values[current_idx-2]  # rsi[2] from current top
            prev_rsi = rsi_values[prev_idx-2]       # rsi[2] from previous top
            
            current_price = prices[current_idx-2]   # close[2] from current top
            prev_price = prices[prev_idx-2]         # close[2] from previous top
            
            # Bearish divergence: RSI makes lower high, price makes higher high
            if current_rsi < prev_rsi and current_price > prev_price:
                sell_signals.append({
                    'index': current_idx,
                    'bars_ago': len(rsi_values) - 1 - current_idx,
                    'price': current_price,
                    'rsi': current_rsi,
                    'prev_rsi': prev_rsi,
                    'prev_price': prev_price,
                    'type': 'BEARISH_DIVERGENCE'
                })
        
        # Detect buy signals (bullish divergence)
        # buy := bottom == true 
        #     and rsi[2] > valuewhen(bottom==true,rsi[2],1)
        #     and close[2] < valuewhen(bottom==true,close[2],1)
        
        for i, current_bottom in enumerate(bottoms[1:], 1):  # Start from second bottom
            prev_bottom = bottoms[i-1]
            current_idx = current_bottom['index']
            prev_idx = prev_bottom['index']
            
            current_rsi = rsi_values[current_idx-2]  # rsi[2] from current bottom
            prev_rsi = rsi_values[prev_idx-2]        # rsi[2] from previous bottom
            
            current_price = prices[current_idx-2]    # close[2] from current bottom
            prev_price = prices[prev_idx-2]          # close[2] from previous bottom
            
            # Bullish divergence: RSI makes higher low, price makes lower low
            if current_rsi > prev_rsi and current_price < prev_price:
                buy_signals.append({
                    'index': current_idx,
                    'bars_ago': len(rsi_values) - 1 - current_idx,
                    'price': current_price,
                    'rsi': current_rsi,
                    'prev_rsi': prev_rsi,
                    'prev_price': prev_price,
                    'type': 'BULLISH_DIVERGENCE'
                })
        
        return {'buy_signals': buy_signals, 'sell_signals': sell_signals}

    def analyze_symbol(self, kline_data: List[Dict]) -> Dict:
        """
        Main analysis function for RSI Divergence detection
        ตรวจสอบ RSI Divergence ย้อนหลัง 12 timeframes (12 ชั่วโมง)
        
        Args:
            kline_data: List of kline data dictionaries
            
        Returns:
            Dict with analysis results
        """
        try:
            if len(kline_data) < self.rsi_period + 20:
                return {
                    'has_signal': False,
                    'signal_type': 'INSUFFICIENT_DATA',
                    'reason': f'ต้องการข้อมูลอย่างน้อย {self.rsi_period + 20} แท่ง'
                }
            
            # Extract price data
            closes = [float(k['close']) for k in kline_data]
            
            # Calculate RSI
            rsi_values = self.calculate_rsi(closes, self.rsi_period)
            
            if len(rsi_values) < 12:
                return {
                    'has_signal': False,
                    'signal_type': 'INSUFFICIENT_RSI_DATA',
                    'reason': 'ข้อมูล RSI ไม่เพียงพอสำหรับการวิเคราะห์'
                }
            
            # Detect tops and bottoms
            tops_bottoms = self.detect_tops_bottoms(rsi_values)
            tops = tops_bottoms['tops']
            bottoms = tops_bottoms['bottoms']
            
            # Detect divergence signals
            divergence = self.detect_divergence(rsi_values, closes, tops, bottoms)
            buy_signals = divergence['buy_signals']
            sell_signals = divergence['sell_signals']
            
            # Filter signals within last 12 timeframes
            lookback_periods = 12
            recent_buy_signals = [s for s in buy_signals if s['bars_ago'] <= lookback_periods]
            recent_sell_signals = [s for s in sell_signals if s['bars_ago'] <= lookback_periods]
            
            # Determine if there's a signal
            has_signal = len(recent_buy_signals) > 0 or len(recent_sell_signals) > 0
            signal_type = 'NO_SIGNAL'
            latest_signal = None
            
            if recent_buy_signals:
                latest_signal = recent_buy_signals[-1]  # Most recent buy signal
                signal_type = 'BUY_DIVERGENCE'
            elif recent_sell_signals:
                latest_signal = recent_sell_signals[-1]  # Most recent sell signal
                signal_type = 'SELL_DIVERGENCE'
            
            # Get current values
            current_price = closes[-1]
            current_rsi = rsi_values[-1]
            
            reason = self._generate_reason(signal_type, current_price, current_rsi, 
                                         recent_buy_signals, recent_sell_signals, latest_signal)
            
            result = {
                'has_signal': has_signal,
                'signal_type': signal_type,
                'reason': reason,
                'current_price': current_price,
                'current_rsi': current_rsi,
                'buy_signal': len(recent_buy_signals) > 0,
                'sell_signal': len(recent_sell_signals) > 0,
                'recent_buy_signals': recent_buy_signals,
                'recent_sell_signals': recent_sell_signals,
                'all_tops': tops,
                'all_bottoms': bottoms,
                'lookback_periods': lookback_periods,
                'parameters': {
                    'rsi_period': self.rsi_period,
                    'overbought_level': self.overbought_level,
                    'oversold_level': self.oversold_level,
                    'top_rsi_threshold': self.top_rsi_threshold,
                    'bottom_rsi_threshold': self.bottom_rsi_threshold
                }
            }
            
            return result
            
        except Exception as e:
            return {
                'has_signal': False,
                'signal_type': 'ERROR',
                'reason': f'เกิดข้อผิดพลาดในการวิเคราะห์ RSI Divergence: {str(e)}'
            }

    def _generate_reason(self, signal_type: str, current_price: float, current_rsi: float,
                        buy_signals: List, sell_signals: List, latest_signal: Dict = None) -> str:
        """Generate explanation for the RSI Divergence signals"""
        if signal_type == 'BUY_DIVERGENCE' and latest_signal:
            bars_ago = latest_signal['bars_ago']
            signal_price = latest_signal['price']
            signal_rsi = latest_signal['rsi']
            return f'🟢 RSI Bullish Divergence: สัญญาณซื้อ {bars_ago} แท่งที่แล้ว (ราคา ${signal_price:.4f}, RSI {signal_rsi:.1f}) - RSI higher low vs Price lower low'
        elif signal_type == 'SELL_DIVERGENCE' and latest_signal:
            bars_ago = latest_signal['bars_ago']
            signal_price = latest_signal['price']
            signal_rsi = latest_signal['rsi']
            return f'🔴 RSI Bearish Divergence: สัญญาณขาย {bars_ago} แท่งที่แล้ว (ราคา ${signal_price:.4f}, RSI {signal_rsi:.1f}) - RSI lower high vs Price higher high'
        else:
            total_signals = len(buy_signals) + len(sell_signals)
            if total_signals > 0:
                return f'⚪ RSI Divergence: พบ {total_signals} สัญญาณใน 12 แท่งที่แล้ว - ปัจจุบัน RSI {current_rsi:.1f}, ราคา ${current_price:.4f}'
            return f'⚪ RSI Divergence: ไม่มีสัญญาณใน 12 แท่งย้อนหลัง - ปัจจุบัน RSI {current_rsi:.1f}, ราคา ${current_price:.4f}'


# Utility functions for main.py integration

def is_rsi_divergence_signal_valid(symbol: str, kline_data) -> bool:
    """
    Check if symbol has RSI Divergence signal in last 12 timeframes
    
    Args:
        symbol: Symbol name
        kline_data: Kline data in various formats
        
    Returns:
        True if RSI divergence signal detected
    """
    try:
        # Handle different input formats
        klines_list = []
        
        if isinstance(kline_data, dict) and 'opens' in kline_data:
            # Dict format with separate arrays
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
                    'volume': str(volumes[i]) if i < len(volumes) else '0'
                })
        elif isinstance(kline_data, list):
            if len(kline_data) > 0 and isinstance(kline_data[0], list):
                # Raw Binance format [[timestamp, open, high, low, close, volume, ...], ...]
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
        
        # Check for data quality - filter out suspicious data (check last 20 candles from 288)
        recent_klines = klines_list[-20:]  # Check last 20 candles from 288 timeframes
        suspicious_count = 0
        
        for kline in recent_klines:
            open_price = float(kline['open'])
            high_price = float(kline['high'])
            low_price = float(kline['low'])
            close_price = float(kline['close'])
            volume = float(kline['volume'])
            
            # Check if OHLC are all the same and volume is 0 (suspicious)
            if (open_price == high_price == low_price == close_price and volume == 0):
                suspicious_count += 1
        
        # If more than 70% of recent candles are suspicious, skip this symbol
        if suspicious_count > len(recent_klines) * 0.7:
            print(f"⚠️  {symbol}: Skipping - suspicious data quality ({suspicious_count}/{len(recent_klines)} candles with OHLC=same, V=0)")
            return False
            
        # Use RSI Divergence analyzer
        analyzer = RSIDivergenceAnalyzer()
        result = analyzer.analyze_symbol(klines_list)
        return result['has_signal']
        
    except Exception as e:
        print(f"❌ Error analyzing RSI Divergence for {symbol}: {e}")
        return False

def get_rsi_divergence_analysis_text(symbol: str, kline_data, current_price: float) -> str:
    """Generate RSI Divergence analysis text for AI prompt (with 12-bar lookback)"""
    try:
        # Handle different input formats - same as is_rsi_divergence_signal_valid
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
                    'volume': str(volumes[i]) if i < len(volumes) else '0'
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
            
        analyzer = RSIDivergenceAnalyzer()
        result = analyzer.analyze_symbol(klines_list)
        
        text = f"\n📈 RSI DIVERGENCE ANALYSIS - {symbol} (12-Hour Lookback)\n"
        text += f"Current Price: ${current_price:.4f}\n"
        text += f"Current RSI: {result.get('current_rsi', 0):.1f}\n"
        text += f"Status: {result['reason']}\n"
        
        if result['has_signal']:
            signal_type = result['signal_type']
            text += f"🎯 SIGNAL: {signal_type} detected!\n"
            
            recent_buy_signals = result.get('recent_buy_signals', [])
            recent_sell_signals = result.get('recent_sell_signals', [])
            
            if recent_buy_signals:
                latest_buy = recent_buy_signals[-1]
                bars_ago = latest_buy['bars_ago']
                signal_price = latest_buy['price']
                signal_rsi = latest_buy['rsi']
                text += f"  - Bullish Divergence {bars_ago} แท่งที่แล้ว (${signal_price:.4f}, RSI {signal_rsi:.1f})\n"
                text += f"  - RSI made higher low while price made lower low\n"
                
            if recent_sell_signals:
                latest_sell = recent_sell_signals[-1]
                bars_ago = latest_sell['bars_ago']
                signal_price = latest_sell['price']
                signal_rsi = latest_sell['rsi']
                text += f"  - Bearish Divergence {bars_ago} แท่งที่แล้ว (${signal_price:.4f}, RSI {signal_rsi:.1f})\n"
                text += f"  - RSI made lower high while price made higher high\n"
                
            total_signals = len(recent_buy_signals) + len(recent_sell_signals)
            if total_signals > 1:
                text += f"  - รวมพบ {total_signals} สัญญาณ divergence ใน 12 แท่งย้อนหลัง\n"
        
        params = result.get('parameters', {})
        text += f"📊 Settings: RSI Period={params.get('rsi_period', 14)}, "
        text += f"Top Threshold={params.get('top_rsi_threshold', 60)}, "
        text += f"Bottom Threshold={params.get('bottom_rsi_threshold', 40)}, Lookback=12 bars\n"
        
        return text
        
    except Exception as e:
        return f"\n❌ Error generating RSI Divergence analysis for {symbol}: {e}\n"
