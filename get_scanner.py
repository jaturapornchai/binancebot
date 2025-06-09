#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, time, datetime, json, logging
import pandas as pd, numpy as np
import concurrent.futures
from dotenv import load_dotenv
from binance.client import Client
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn

from get_indicators import TechnicalIndicators
from get_utils import DataUtils
from get_display import DisplayManager

class AltcoinMomentumScanner:
    def __init__(self):
        try:
            # โหลด environment variables
            load_dotenv(override=True)
            self.api_key = os.getenv('BINANCE_API_KEY')
            self.secret_key = os.getenv('BINANCE_SECRET_KEY')
            
            if not self.api_key or not self.secret_key:
                raise ValueError("API keys ไม่พบในไฟล์ .env กรุณาสร้างไฟล์ .env และกำหนดค่า BINANCE_API_KEY และ BINANCE_SECRET_KEY")
            
            # เชื่อมต่อกับ Binance API
            self.client = Client(self.api_key, self.secret_key)
            self.console = Console()
            self.logger = logging.getLogger("AltcoinMomentumScanner")
            
            # สร้างอินสแตนซ์ของคลาส Helper
            self.indicators = TechnicalIndicators()
            self.utils = DataUtils()
            self.display = DisplayManager()
            
            # ตั้งค่า
            self.settings = {
                'timeframes': ['1h', '4h', '1d'], 
                'default_timeframe': '1h', 
                'higher_timeframe': '4h', 
                'max_coins': 1300,  # จำนวนเหรียญสูงสุดที่จะวิเคราะห์
                'min_daily_volume': 1000000,  # ปริมาณการซื้อขายขั้นต่ำ (USD)
                'rsi_period': 14, 
                'macd_fast': 12, 
                'macd_slow': 26, 
                'macd_signal': 9, 
                'bb_period': 20, 
                'bb_std': 2.0, 
                'atr_period': 14, 
                'volume_ma_period': 20, 
                'volume_surge_threshold': 1.5, 
                'price_change_threshold': 2.0, 
                'breakout_threshold': 0.5, 
                'breakdown_threshold': 0.5, 
                'min_score': 5.0,  # คะแนนขั้นต่ำสำหรับการแสดงเหรียญที่น่าสนใจ
                'price_momentum_weight': 0.25, 
                'volume_weight': 0.20, 
                'pattern_weight': 0.20, 
                'indicator_weight': 0.15, 
                'higher_tf_weight': 0.3, 
                'lower_tf_weight': 0.5, 
                'btc_correlation_weight': 0.2, 
                'sl_multiplier': 1.5, 
                'tp_multiplier': 2.5, 
                'atr_stop_multiplier': 1.5, 
                'tp_r_ratio': 2.0, 
                'max_score': 10.0, 
                'min_score': -10.0, 
                'fibo_levels': [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.618, 2.618, 4.236], 
                'fibo_period': 30, 
                'fibo_tp_level': 1.618, 
                'fibo_sl_level': 0.618,
                'max_display_coins': 10  # จำนวนเหรียญสูงสุดที่จะแสดง
            }
            
            # cache สำหรับเก็บข้อมูลและผลลัพธ์
            self.cache = {
                'candles': {}, 
                'tickers': {}, 
                'last_update': {}, 
                'momentum_scores': {}, 
                'last_scan': None, 
                'scan_results': {
                    'STRONG_BREAKOUT': [], 
                    'BREAKOUT': [], 
                    'BREAKDOWN': [], 
                    'STRONG_BREAKDOWN': [], 
                    'CONSOLIDATION': []
                }, 
                'btc_analysis': {}
            }
            
            # Signals
            self.terms = {
                'STRONG_BREAKOUT': '📈🔥 ทะลุแนวต้านแข็งแกร่ง', 
                'BREAKOUT': '📈 ทะลุแนวต้าน', 
                'BREAKDOWN': '📉 หลุดแนวรับ', 
                'STRONG_BREAKDOWN': '📉🔥 หลุดแนวรับแข็งแกร่ง', 
                'CONSOLIDATION': '⏸️ กำลังสะสม'
            }
            
            # คำแนะนำสำหรับแต่ละสัญญาณ
            self.advice = {
                'STRONG_BREAKOUT': 'เหมาะสำหรับการเข้า Long ด้วยปริมาณสูง - เกิดการทะลุแนวต้านที่มีปริมาณการซื้อขายสูงและตัวชี้วัดหลายตัวยืนยัน', 
                'BREAKOUT': 'พิจารณาเข้า Long ด้วยความระมัดระวัง - รอการทดสอบแนวต้านเดิมที่ทะลุไปเพื่อความมั่นใจเพิ่มเติม', 
                'BREAKDOWN': 'พิจารณาเข้า Short ด้วยความระมัดระวัง - รอการทดสอบแนวรับเดิมที่หลุดไปเพื่อความมั่นใจเพิ่มเติม', 
                'STRONG_BREAKDOWN': 'เหมาะสำหรับการเข้า Short ด้วยปริมาณสูง - เกิดการหลุดแนวรับที่มีปริมาณการซื้อขายสูงและตัวชี้วัดหลายตัวยืนยัน', 
                'CONSOLIDATION': 'รอสัญญาณที่ชัดเจน - กำลังอยู่ในช่วงสะสมที่อาจนำไปสู่การทะลุแนวต้านหรือหลุดแนวรับในอนาคต'
            }
            
            # ชื่อรูปแบบกราฟ
            self.pattern_names = {
                'Breakout ทะลุแนวต้าน': 'การทะลุแนวต้าน', 
                'Breakdown หลุดแนวรับ': 'การหลุดแนวรับ', 
                'Ascending Triangle': 'สามเหลี่ยมฐานยก', 
                'Descending Triangle': 'สามเหลี่ยมฐานต่ำ', 
                'Falling Wedge': 'ลิ่มเอียงลง', 
                'Rising Wedge': 'ลิ่มเอียงขึ้น', 
                'Bull Flag': 'ธงกระทิง', 
                'Bear Flag': 'ธงหมี', 
                'Head and Shoulders': 'หัวและไหล่', 
                'Inverse Head and Shoulders': 'หัวและไหล่กลับหัว', 
                'Double Top': 'ยอดคู่', 
                'Double Bottom': 'ฐานคู่', 
                'Hammer': 'ค้อน', 
                'Shooting Star': 'ดาวตก', 
                'Bullish Engulfing': 'แท่งเขียวกลืนแท่งแดง', 
                'Bearish Engulfing': 'แท่งแดงกลืนแท่งเขียว', 
                'Volatility Squeeze': 'บีบตัวความผันผวน', 
                'MACD Golden Cross': 'MACD ตัดขึ้น', 
                'MACD Death Cross': 'MACD ตัดลง'
            }
            
            # ชื่อระดับ Fibonacci
            self.fibo_names = {
                0: '0% (เส้นฐาน)', 
                0.236: '23.6%', 
                0.382: '38.2%', 
                0.5: '50%', 
                0.618: '61.8%', 
                0.786: '78.6%', 
                1.0: '100%', 
                1.618: '161.8%', 
                2.618: '261.8%', 
                4.236: '423.6%'
            }
            
            # เริ่มต้นระบบสำเร็จ
            self.logger.info("เริ่มต้นระบบสำเร็จ")
            self.console.print("[green]🚀 เริ่มต้นระบบ AltcoinMomentumScanner สำเร็จ[/green]")
            
        except Exception as e:
            logging.getLogger("AltcoinMomentumScanner").error(f"เกิดข้อผิดพลาด: {str(e)}")
            sys.exit(1)

    def normalize_to_10(self, score):
        """ปรับค่าคะแนนให้อยู่ในช่วง 0-10"""
        min_score = self.settings['min_score']
        max_score = self.settings['max_score']
        score_range = max_score - min_score
        normalized = ((score - min_score) / score_range) * 10.0
        return max(0, min(10, normalized))

    def translate_pattern(self, pattern):
        """แปลชื่อรูปแบบกราฟเป็นภาษาไทย"""
        return self.pattern_names.get(pattern, pattern)

    def get_klines(self, symbol, interval, limit=200):
        """ดึงข้อมูลแท่งเทียนจาก Binance"""
        try:
            # เช็คว่ามีในแคชหรือไม่
            cache_key = f"{symbol}_{interval}_{limit}"
            current_time = time.time()
            
            if cache_key in self.cache['candles'] and current_time - self.cache['last_update'].get(cache_key, 0) < 300:
                return self.utils.ensure_dataframe(self.cache['candles'][cache_key])
            
            # แปลง timeframe ให้ตรงกับ Binance API
            binance_interval = {
                '1m': Client.KLINE_INTERVAL_1MINUTE, 
                '3m': Client.KLINE_INTERVAL_3MINUTE, 
                '5m': Client.KLINE_INTERVAL_5MINUTE, 
                '15m': Client.KLINE_INTERVAL_15MINUTE, 
                '30m': Client.KLINE_INTERVAL_30MINUTE, 
                '1h': Client.KLINE_INTERVAL_1HOUR, 
                '2h': Client.KLINE_INTERVAL_2HOUR, 
                '4h': Client.KLINE_INTERVAL_4HOUR, 
                '6h': Client.KLINE_INTERVAL_6HOUR, 
                '8h': Client.KLINE_INTERVAL_8HOUR, 
                '12h': Client.KLINE_INTERVAL_12HOUR, 
                '1d': Client.KLINE_INTERVAL_1DAY, 
                '3d': Client.KLINE_INTERVAL_3DAY, 
                '1w': Client.KLINE_INTERVAL_1WEEK, 
                '1M': Client.KLINE_INTERVAL_1MONTH
            }.get(interval, Client.KLINE_INTERVAL_1HOUR)
            
            # ดึงข้อมูลจาก Binance
            klines = self.client.futures_klines(symbol=symbol, interval=binance_interval, limit=limit)
            
            if not klines or len(klines) < 30:
                self.logger.warning(
                    f"ข้อมูลแท่งเทียน {symbol} ไม่เพียงพอ: {len(klines) if klines else 0} แท่ง"
                )
                return pd.DataFrame()
            
            # แปลงข้อมูลเป็น DataFrame
            df = self.utils.prepare_dataframe(klines)
            
            # คำนวณตัวชี้วัดทางเทคนิค
            self.indicators.calculate_all_indicators(df, self.settings)
            self.indicators.identify_chart_patterns(df, self.settings)
            self.indicators.calculate_fibonacci_levels(df, self.settings)
            
            # เก็บในแคช
            self.cache['candles'][cache_key] = df
            self.cache['last_update'][cache_key] = current_time
            
            return df
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลแท่งเทียน {symbol}: {str(e)}")
            return pd.DataFrame()

    def analyze_higher_timeframe(self, symbol):
        """วิเคราะห์ timeframe ที่สูงขึ้น"""
        try:
            higher_tf = self.settings['higher_timeframe']
            df_higher = self.get_klines(symbol, higher_tf)
            
            if not isinstance(df_higher, pd.DataFrame) or df_higher.empty or len(df_higher) < 30:
                return {
                    'trend': 'NEUTRAL', 
                    'strength': 0, 
                    'support': None, 
                    'resistance': None, 
                    'patterns': [], 
                    'fibo_levels': {}
                }
            
            latest = df_higher.iloc[-1].copy()
            
            # กำหนดแนวโน้ม
            trend = 'NEUTRAL'
            if latest.get('uptrend', False): trend = 'UPTREND'
            elif latest.get('downtrend', False): trend = 'DOWNTREND'
            
            # คำนวณความแข็งแกร่งของแนวโน้ม
            trend_strength = 0
            if trend == 'UPTREND':
                if latest.get('rsi', 50) > 50: trend_strength += 1
                if latest.get('macd', 0) > 0: trend_strength += 1
                if latest.get('close', 0) > latest.get('bb_middle', 0): trend_strength += 1
                bullish_patterns = ['ascending_triangle', 'falling_wedge', 'double_bottom', 'inv_head_and_shoulders']
                for pattern in bullish_patterns:
                    if latest.get(pattern, False):
                        trend_strength += 1
                        break
            elif trend == 'DOWNTREND':
                if latest.get('rsi', 50) < 50: trend_strength += 1
                if latest.get('macd', 0) < 0: trend_strength += 1
                if latest.get('close', 0) < latest.get('bb_middle', 0): trend_strength += 1
                bearish_patterns = ['descending_triangle', 'rising_wedge', 'double_top', 'head_and_shoulders']
                for pattern in bearish_patterns:
                    if latest.get(pattern, False):
                        trend_strength += 1
                        break
            
            # รวบรวมรูปแบบกราฟที่พบ
            patterns = []
            if latest.get('breakout_up', False): patterns.append('Breakout ทะลุแนวต้าน')
            if latest.get('breakout_down', False): patterns.append('Breakdown หลุดแนวรับ')
            if latest.get('ascending_triangle', False): patterns.append('Ascending Triangle')
            if latest.get('descending_triangle', False): patterns.append('Descending Triangle')
            if latest.get('falling_wedge', False): patterns.append('Falling Wedge')
            if latest.get('rising_wedge', False): patterns.append('Rising Wedge')
            if latest.get('head_and_shoulders', False): patterns.append('Head and Shoulders')
            if latest.get('inv_head_and_shoulders', False): patterns.append('Inverse Head and Shoulders')
            if latest.get('double_top', False): patterns.append('Double Top')
            if latest.get('double_bottom', False): patterns.append('Double Bottom')
            
            translated_patterns = [self.translate_pattern(p) for p in patterns]
            
            # ดึงข้อมูล Fibonacci
            fibo_levels = {}
            try:
                if 'fibo_retracement_levels' in latest and latest['fibo_retracement_levels'] and isinstance(latest['fibo_retracement_levels'], str):
                    fibo_levels['retracement'] = json.loads(latest['fibo_retracement_levels'])
                if 'fibo_extension_levels' in latest and latest['fibo_extension_levels'] and isinstance(latest['fibo_extension_levels'], str):
                    fibo_levels['extension'] = json.loads(latest['fibo_extension_levels'])
                if 'fibo_direction' in latest:
                    fibo_levels['direction'] = latest['fibo_direction']
                if 'fibo_swing_high' in latest:
                    fibo_levels['swing_high'] = latest['fibo_swing_high']
                if 'fibo_swing_low' in latest:
                    fibo_levels['swing_low'] = latest['fibo_swing_low']
            except Exception as e:
                self.logger.error(f"เกิดข้อผิดพลาดในการดึงระดับ Fibonacci: {str(e)}")
            
            return {
                'trend': trend, 
                'strength': trend_strength, 
                'support': latest.get('nearest_support'), 
                'resistance': latest.get('nearest_resistance'), 
                'patterns': translated_patterns, 
                'fibo_levels': fibo_levels, 
                'fibo_support': latest.get('nearest_fibo_support_price'), 
                'fibo_resistance': latest.get('nearest_fibo_resistance_price'), 
                'fibo_support_level': latest.get('nearest_fibo_support_level'), 
                'fibo_resistance_level': latest.get('nearest_fibo_resistance_level')
            }
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการวิเคราะห์ timeframe ที่สูงขึ้น {symbol}: {str(e)}")
            return {
                'trend': 'NEUTRAL', 
                'strength': 0, 
                'support': None, 
                'resistance': None, 
                'patterns': [], 
                'fibo_levels': {}
            }

    def analyze_btc_trend(self, timeframes=None):
        """วิเคราะห์แนวโน้มของ Bitcoin"""
        try:
            if timeframes is None: 
                timeframes = ['1h', '4h', '1d']
            
            result = {}
            self.console.print("[cyan]กำลังวิเคราะห์แนวโน้มของ Bitcoin (BTCUSDT)...[/cyan]")
            
            # วิเคราะห์แต่ละ timeframe
            for tf in timeframes:
                df = self.get_klines('BTCUSDT', tf)
                
                if not isinstance(df, pd.DataFrame) or df.empty or len(df) < 30:
                    result[tf] = {'trend': 'NEUTRAL', 'strength': 0, 'price': 0, 'signal': 'CONSOLIDATION', 'patterns': [], 'score': 0}
                    continue
                
                latest = df.iloc[-1].copy()
                trend = 'NEUTRAL'
                price = latest['close']
                
                # กำหนดแนวโน้ม
                if latest.get('uptrend', False): trend = 'UPTREND'
                elif latest.get('downtrend', False): trend = 'DOWNTREND'
                
                # คำนวณความแข็งแกร่งของแนวโน้ม
                trend_strength = 0
                if trend == 'UPTREND':
                    if latest.get('rsi', 50) > 50: trend_strength += 1
                    if latest.get('macd', 0) > 0: trend_strength += 1
                    if latest.get('close', 0) > latest.get('bb_middle', 0): trend_strength += 1
                    bullish_patterns = ['ascending_triangle', 'falling_wedge', 'double_bottom', 'inv_head_and_shoulders']
                    for pattern in bullish_patterns:
                        if latest.get(pattern, False):
                            trend_strength += 1
                            break
                elif trend == 'DOWNTREND':
                    if latest.get('rsi', 50) < 50: trend_strength -= 1
                    if latest.get('macd', 0) < 0: trend_strength -= 1
                    if latest.get('close', 0) < latest.get('bb_middle', 0): trend_strength -= 1
                    bearish_patterns = ['descending_triangle', 'rising_wedge', 'double_top', 'head_and_shoulders']
                    for pattern in bullish_patterns:
                        if latest.get(pattern, False):
                            trend_strength -= 1
                            break
                
                # คำนวณคะแนนโมเมนตัม
                score = 0
                change_1d = latest.get('change_1d', 0)
                price_momentum = min(5, change_1d / 2) if change_1d > 0 else max(-5, change_1d / 2)
                volume_ratio = latest.get('volume_ratio', 1)
                volume_momentum = min(3, (volume_ratio - 1) * 1.5) if volume_ratio > 1.5 else 0
                
                # คำนวณคะแนนจากตัวชี้วัด
                indicator_score = 0
                rsi = latest.get('rsi', 50)
                if rsi > 70: indicator_score -= 1
                elif rsi < 30: indicator_score += 1
                elif rsi > 60: indicator_score += 0.5
                elif rsi < 40: indicator_score -= 0.5
                
                macd = latest.get('macd', 0)
                macd_signal = latest.get('macd_signal', 0)
                if macd > 0 and macd > macd_signal: indicator_score += 1
                elif macd < 0 and macd < macd_signal: indicator_score -= 1
                
                # คำนวณคะแนนจากรูปแบบกราฟ
                pattern_score = 0
                if latest.get('breakout_up', False): pattern_score += 3
                elif latest.get('breakout_down', False): pattern_score -= 3
                if latest.get('ascending_triangle', False): pattern_score += 2
                elif latest.get('descending_triangle', False): pattern_score -= 2
                if latest.get('falling_wedge', False): pattern_score += 2
                elif latest.get('rising_wedge', False): pattern_score -= 2
                if latest.get('double_bottom', False): pattern_score += 2
                elif latest.get('double_top', False): pattern_score -= 2
                if latest.get('inv_head_and_shoulders', False): pattern_score += 2.5
                elif latest.get('head_and_shoulders', False): pattern_score -= 2.5
                
                # รวมคะแนน
                score = (price_momentum * 0.4 + volume_momentum * 0.2 + indicator_score * 0.2 + pattern_score * 0.2)
                score_10 = self.normalize_to_10(score)
                
                # กำหนดสัญญาณ
                signal = 'CONSOLIDATION'
                if score >= 2: signal = 'STRONG_BREAKOUT' if score >= 4 else 'BREAKOUT'
                elif score <= -2: signal = 'STRONG_BREAKDOWN' if score <= -4 else 'BREAKDOWN'
                
                # รวบรวมรูปแบบกราฟที่พบ
                patterns = []
                if latest.get('breakout_up', False): patterns.append('Breakout ทะลุแนวต้าน')
                if latest.get('breakout_down', False): patterns.append('Breakdown หลุดแนวรับ')
                if latest.get('ascending_triangle', False): patterns.append('Ascending Triangle')
                if latest.get('descending_triangle', False): patterns.append('Descending Triangle')
                if latest.get('falling_wedge', False): patterns.append('Falling Wedge')
                if latest.get('rising_wedge', False): patterns.append('Rising Wedge')
                if latest.get('head_and_shoulders', False): patterns.append('Head and Shoulders')
                if latest.get('inv_head_and_shoulders', False): patterns.append('Inverse Head and Shoulders')
                if latest.get('double_top', False): patterns.append('Double Top')
                if latest.get('double_bottom', False): patterns.append('Double Bottom')
                if latest.get('hammer', False): patterns.append('Hammer')
                if latest.get('shooting_star', False): patterns.append('Shooting Star')
                if latest.get('bullish_engulfing', False): patterns.append('Bullish Engulfing')
                if latest.get('bearish_engulfing', False): patterns.append('Bearish Engulfing')
                
                translated_patterns = [self.translate_pattern(p) for p in patterns]
                
                # ดึงข้อมูล Fibonacci
                fibo_levels = {}
                try:
                    if 'fibo_retracement_levels' in latest and latest['fibo_retracement_levels'] and isinstance(latest['fibo_retracement_levels'], str):
                        fibo_levels['retracement'] = json.loads(latest['fibo_retracement_levels'])
                    if 'fibo_extension_levels' in latest and latest['fibo_extension_levels'] and isinstance(latest['fibo_extension_levels'], str):
                        fibo_levels['extension'] = json.loads(latest['fibo_extension_levels'])
                    if 'fibo_direction' in latest:
                        fibo_levels['direction'] = latest['fibo_direction']
                    if 'fibo_swing_high' in latest:
                        fibo_levels['swing_high'] = latest['fibo_swing_high']
                    if 'fibo_swing_low' in latest:
                        fibo_levels['swing_low'] = latest['fibo_swing_low']
                except Exception as e:
                    self.logger.error(f"เกิดข้อผิดพลาดในการดึงระดับ Fibonacci: {str(e)}")
                
                # รวมผลลัพธ์
                result[tf] = {
                    'trend': trend, 
                    'strength': trend_strength, 
                    'price': price,
                    'momentum_score': score,
                    'score_10': score_10,
                    'signal': signal,
                    'patterns': translated_patterns,
                    'fibo_levels': fibo_levels,
                    'fibo_support': latest.get('nearest_fibo_support_price'),
                    'fibo_resistance': latest.get('nearest_fibo_resistance_price'),
                    'fibo_support_level': latest.get('nearest_fibo_support_level'),
                    'fibo_resistance_level': latest.get('nearest_fibo_resistance_level'),
                    'extra': {
                        'rsi': rsi,
                        'macd': macd,
                        'volume_ratio': volume_ratio,
                        'change_1d': change_1d,
                        'nearest_support': latest.get('nearest_support'),
                        'nearest_resistance': latest.get('nearest_resistance'),
                        'squeeze_fire': latest.get('squeeze_fire', False),
                        'trend_reversal': latest.get('trend_reversal', False)
                    }
                }
            
            # วิเคราะห์แนวโน้มหลัก
            if '1h' in result and '4h' in result and '1d' in result:
                combined_score = (
                    result['1h'].get('momentum_score', 0) * 0.3 + 
                    result['4h'].get('momentum_score', 0) * 0.3 + 
                    result['1d'].get('momentum_score', 0) * 0.4
                )
                combined_score_10 = self.normalize_to_10(combined_score)
                
                primary_signal = 'CONSOLIDATION'
                if combined_score >= 2: primary_signal = 'STRONG_BREAKOUT' if combined_score >= 4 else 'BREAKOUT'
                elif combined_score <= -2: primary_signal = 'STRONG_BREAKDOWN' if combined_score <= -4 else 'BREAKDOWN'
                
                primary_trend = 'NEUTRAL'
                if (result['1h']['trend'] == 'UPTREND' and result['4h']['trend'] == 'UPTREND') or (result['4h']['trend'] == 'UPTREND' and result['1d']['trend'] == 'UPTREND'):
                    primary_trend = 'UPTREND'
                elif (result['1h']['trend'] == 'DOWNTREND' and result['4h']['trend'] == 'DOWNTREND') or (result['4h']['trend'] == 'DOWNTREND' and result['1d']['trend'] == 'DOWNTREND'):
                    primary_trend = 'DOWNTREND'
                
                result['primary'] = {
                    'trend': primary_trend,
                    'signal': primary_signal,
                    'momentum_score': combined_score,
                    'score_10': combined_score_10,
                    'price': result['1h']['price']
                }
            
            self.cache['btc_analysis'] = result
            
            # แสดงผลสรุป
            term = self.terms.get(result.get('primary', {}).get('signal', 'CONSOLIDATION'), 'กำลังสะสม')
            signal_color = "green" if "BREAKOUT" in result.get('primary', {}).get('signal', '') else "red" if "BREAKDOWN" in result.get('primary', {}).get('signal', '') else "yellow"
            score_10 = result.get('primary', {}).get('score_10', 0)
            
            self.console.print(f"[cyan]สรุปแนวโน้ม Bitcoin (BTCUSDT):[/cyan] ")
            self.console.print(f"ราคา: ${result['1h']['price']:,.2f} | สัญญาณหลัก: [{signal_color}]{term}[/{signal_color}] | คะแนน: {score_10:.1f}/10 ({result.get('primary', {}).get('momentum_score', 0):.2f})")
            self.console.print(f"แนวโน้ม 1H: [{'green' if result['1h']['trend'] == 'UPTREND' else 'red' if result['1h']['trend'] == 'DOWNTREND' else 'yellow'}]{result['1h']['trend']}[/] | "
                             f"4H: [{'green' if result['4h']['trend'] == 'UPTREND' else 'red' if result['4h']['trend'] == 'DOWNTREND' else 'yellow'}]{result['4h']['trend']}[/] | "
                             f"1D: [{'green' if result['1d']['trend'] == 'UPTREND' else 'red' if result['1d']['trend'] == 'DOWNTREND' else 'yellow'}]{result['1d']['trend']}[/]")
            
            return result
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการวิเคราะห์ Bitcoin: {str(e)}")
            return {
                '1h': {'trend': 'NEUTRAL', 'signal': 'CONSOLIDATION', 'momentum_score': 0, 'score_10': 0},
                '4h': {'trend': 'NEUTRAL', 'signal': 'CONSOLIDATION', 'momentum_score': 0, 'score_10': 0},
                '1d': {'trend': 'NEUTRAL', 'signal': 'CONSOLIDATION', 'momentum_score': 0, 'score_10': 0},
                'primary': {'trend': 'NEUTRAL', 'signal': 'CONSOLIDATION', 'momentum_score': 0, 'score_10': 0}
            }

    def calculate_correlation_with_btc(self, symbol, interval=None):
        """คำนวณค่าสหสัมพันธ์กับ Bitcoin"""
        try:
            if interval is None: 
                interval = self.settings['default_timeframe']
            
            df_coin = self.get_klines(symbol, interval)
            df_btc = self.get_klines('BTCUSDT', interval)
            
            if not isinstance(df_coin, pd.DataFrame) or df_coin.empty or len(df_coin) < 30 or not isinstance(df_btc, pd.DataFrame) or df_btc.empty or len(df_btc) < 30:
                return 0
            
            min_len = min(len(df_coin), len(df_btc))
            coin_returns = df_coin['close'].pct_change().iloc[-min_len:].fillna(0)
            btc_returns = df_btc['close'].pct_change().iloc[-min_len:].fillna(0)
            
            correlation = coin_returns.corr(btc_returns)
            return correlation
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการคำนวณความสัมพันธ์กับ BTC {symbol}: {str(e)}")
            return 0
        

















def calculate_momentum_score(self, symbol, interval=None):
        """คำนวณคะแนนโมเมนตัมของเหรียญ"""
        try:
            if interval is None: 
                interval = self.settings['default_timeframe']
            
            # ตรวจสอบการวิเคราะห์ BTC
            if not self.cache['btc_analysis']:
                self.analyze_btc_trend()
            
            btc_trend = self.cache['btc_analysis'].get('primary', {}).get('trend', 'NEUTRAL')
            btc_signal = self.cache['btc_analysis'].get('primary', {}).get('signal', 'CONSOLIDATION')
            btc_score = self.cache['btc_analysis'].get('primary', {}).get('momentum_score', 0)
            btc_analysis = self.cache['btc_analysis'].get(interval, {})
            
            # หาความสัมพันธ์กับ BTC
            correlation = self.calculate_correlation_with_btc(symbol, interval)
            
            # ดึงข้อมูลเหรียญ
            df = self.get_klines(symbol, interval)
            if not isinstance(df, pd.DataFrame) or df.empty or len(df) < 30:
                return {'symbol': symbol, 'interval': interval, 'momentum_score': 0, 'score_10': 0, 'signal': 'CONSOLIDATION', 'price': 0, 'pattern': []}
            
            # วิเคราะห์ timeframe ที่สูงขึ้น
            higher_tf_analysis = self.analyze_higher_timeframe(symbol)
            
            latest = df.iloc[-1].copy()
            
            # คำนวณโมเมนตัมของราคา
            price_momentum = 0
            change_1d = latest.get('change_1d', 0)
            change_3d = latest.get('change_3d', 0)
            change_7d = latest.get('change_7d', 0)
            
            acceleration = abs(change_1d) > abs(change_3d) / 3 * 1.2
            if change_1d > 0:
                price_momentum = min(5, (change_1d * 0.5 + change_3d * 0.3 + change_7d * 0.2) / 2)
                if acceleration and change_1d > 3: price_momentum += 1
            else:
                price_momentum = max(-5, (change_1d * 0.5 + change_3d * 0.3 + change_7d * 0.2) / 2)
                if acceleration and change_1d < -3: price_momentum -= 1
            
            # คำนวณโมเมนตัมของปริมาณซื้อขาย
            volume_momentum = 0
            volume_ratio = latest.get('volume_ratio', 1)
            
            if volume_ratio > 1.5:
                volume_strength = min(3, (volume_ratio - 1) * 1.5)
                if (change_1d > 0 and latest['close'] > latest['open']) or (change_1d < 0 and latest['close'] < latest['open']):
                    volume_momentum = volume_strength
                else: volume_momentum = volume_strength * 0.3
            
            # คำนวณคะแนนจากรูปแบบกราฟ
            pattern_score = 0
            pattern_list = []
            
            breakout_up = latest.get('breakout_up', False)
            breakout_down = latest.get('breakout_down', False)
            
            if breakout_up:
                pattern_score += 3
                pattern_list.append('Breakout ทะลุแนวต้าน')
            elif breakout_down:
                pattern_score -= 3
                pattern_list.append('Breakdown หลุดแนวรับ')
            
            if latest.get('ascending_triangle', False):
                pattern_score += 2
                pattern_list.append('Ascending Triangle')
            elif latest.get('descending_triangle', False):
                pattern_score -= 2
                pattern_list.append('Descending Triangle')
            
            if latest.get('falling_wedge', False):
                pattern_score += 2
                pattern_list.append('Falling Wedge')
            elif latest.get('rising_wedge', False):
                pattern_score -= 2
                pattern_list.append('Rising Wedge')
            
            if latest.get('bull_flag', False):
                pattern_score += 1.5
                pattern_list.append('Bull Flag')
            elif latest.get('bear_flag', False):
                pattern_score -= 1.5
                pattern_list.append('Bear Flag')
            
            if latest.get('head_and_shoulders', False):
                pattern_score -= 2.5
                pattern_list.append('Head and Shoulders')
            elif latest.get('inv_head_and_shoulders', False):
                pattern_score += 2.5
                pattern_list.append('Inverse Head and Shoulders')
            
            if latest.get('double_top', False):
                pattern_score -= 2
                pattern_list.append('Double Top')
            elif latest.get('double_bottom', False):
                pattern_score += 2
                pattern_list.append('Double Bottom')
            
            if latest.get('hammer', False):
                pattern_score += 1
                pattern_list.append('Hammer')
            elif latest.get('shooting_star', False):
                pattern_score -= 1
                pattern_list.append('Shooting Star')
            elif latest.get('bullish_engulfing', False):
                pattern_score += 1.5
                pattern_list.append('Bullish Engulfing')
            elif latest.get('bearish_engulfing', False):
                pattern_score -= 1.5
                pattern_list.append('Bearish Engulfing')
            
            if latest.get('squeeze_fire', False):
                direction = 1 if latest['close'] > latest['open'] else -1
                pattern_score += 2 * direction
                pattern_list.append('Volatility Squeeze')
            
            # คำนวณคะแนนจากตัวชี้วัด
            indicator_score = 0
            rsi = latest.get('rsi', 50)
            
            if rsi > 70: indicator_score -= 1
            elif rsi < 30: indicator_score += 1
            elif rsi > 60: indicator_score += 0.5
            elif rsi < 40: indicator_score -= 0.5
            
            macd = latest.get('macd', 0)
            macd_signal = latest.get('macd_signal', 0)
            macd_hist = latest.get('macd_hist', 0)
            
            if macd > 0 and macd > macd_signal: indicator_score += 1
            elif macd < 0 and macd < macd_signal: indicator_score -= 1
            
            if len(df) > 2:
                macd_prev = df['macd'].iloc[-2]
                signal_prev = df['macd_signal'].iloc[-2]
                
                if macd > macd_signal and macd_prev <= signal_prev:
                    indicator_score += 1.5
                    pattern_list.append('MACD Golden Cross')
                elif macd < macd_signal and macd_prev >= signal_prev:
                    indicator_score -= 1.5
                    pattern_list.append('MACD Death Cross')
            
            bb_percent_b = latest.get('bb_percent_b', 0.5)
            if bb_percent_b > 1: indicator_score += 1 if volume_ratio > 1.5 else -0.5
            elif bb_percent_b < 0: indicator_score -= 1 if volume_ratio > 1.5 else 0.5
            
            # คำนวณคะแนนจาก timeframe ที่สูงขึ้น
            higher_tf_score = 0
            
            if higher_tf_analysis['trend'] == 'UPTREND':
                higher_tf_score = min(5, 2 + higher_tf_analysis['strength'])
                if price_momentum > 0: higher_tf_score += 1
            elif higher_tf_analysis['trend'] == 'DOWNTREND':
                higher_tf_score = max(-5, -2 - higher_tf_analysis['strength'])
                if price_momentum < 0: higher_tf_score -= 1
            
            if higher_tf_analysis['patterns']:
                for pattern in higher_tf_analysis['patterns']:
                    if pattern not in pattern_list: pattern_list.append(f"{pattern} (4H)")
            
            # คำนวณคะแนนจาก Fibonacci
            fibo_score = 0
            fibo_direction = latest.get('fibo_direction')
            nearest_fibo_resistance_level = latest.get('nearest_fibo_resistance_level')
            nearest_fibo_support_level = latest.get('nearest_fibo_support_level')
            
            if fibo_direction == 'up' and breakout_up:
                fibo_score += 1
                if nearest_fibo_resistance_level and nearest_fibo_resistance_level > 0.618:
                    fibo_score += 0.5
            elif fibo_direction == 'down' and breakout_down:
                fibo_score -= 1
                if nearest_fibo_support_level and nearest_fibo_support_level > 0.618:
                    fibo_score -= 0.5
            
            if nearest_fibo_resistance_level and nearest_fibo_resistance_level == 0.618:
                if latest['close'] > latest['open']: fibo_score += 0.5
            if nearest_fibo_support_level and nearest_fibo_support_level == 0.618:
                if latest['close'] < latest['open']: fibo_score -= 0.5
            
            # คำนวณคะแนนจากความสัมพันธ์กับ BTC
            btc_correlation_score = 0
            
            if abs(correlation) > 0.7:
                if correlation > 0:
                    if btc_signal == 'STRONG_BREAKOUT': btc_correlation_score += 2
                    elif btc_signal == 'BREAKOUT': btc_correlation_score += 1
                    elif btc_signal == 'STRONG_BREAKDOWN': btc_correlation_score -= 2
                    elif btc_signal == 'BREAKDOWN': btc_correlation_score -= 1
                else:
                    if btc_signal == 'STRONG_BREAKOUT': btc_correlation_score -= 2
                    elif btc_signal == 'BREAKOUT': btc_correlation_score -= 1
                    elif btc_signal == 'STRONG_BREAKDOWN': btc_correlation_score += 2
                    elif btc_signal == 'BREAKDOWN': btc_correlation_score += 1
            
            # รวมคะแนนทั้งหมด
            total_score = (
                price_momentum * self.settings['price_momentum_weight'] +
                volume_momentum * self.settings['volume_weight'] +
                pattern_score * self.settings['pattern_weight'] +
                indicator_score * self.settings['indicator_weight'] +
                higher_tf_score * self.settings['higher_tf_weight'] +
                fibo_score * 0.15 +
                btc_correlation_score * self.settings['btc_correlation_weight']
            )
            
            score_10 = self.normalize_to_10(total_score)
            
            # กำหนดสัญญาณ
            signal = 'CONSOLIDATION'
            if total_score >= 2: signal = 'STRONG_BREAKOUT' if total_score >= 4 else 'BREAKOUT'
            elif total_score <= -2: signal = 'STRONG_BREAKDOWN' if total_score <= -4 else 'BREAKDOWN'
            
            translated_patterns = [self.translate_pattern(p) for p in pattern_list]
            
            # คำนวณระดับเข้าเทรด
            current_price = latest['close']
            atr = latest.get('atr', current_price * 0.01)
            nearest_resistance = latest.get('nearest_resistance', None)
            nearest_support = latest.get('nearest_support', None)
            
            entry_price, stop_loss, take_profit = self.calculate_trade_levels(signal, current_price, atr, nearest_support, nearest_resistance, higher_tf_analysis)
            
            # ดึงข้อมูล Fibonacci
            fibo_levels = {}
            try:
                if 'fibo_retracement_levels' in latest and latest['fibo_retracement_levels'] and isinstance(latest['fibo_retracement_levels'], str):
                    fibo_levels['retracement'] = json.loads(latest['fibo_retracement_levels'])
                if 'fibo_extension_levels' in latest and latest['fibo_extension_levels'] and isinstance(latest['fibo_extension_levels'], str):
                    fibo_levels['extension'] = json.loads(latest['fibo_extension_levels'])
                if 'fibo_direction' in latest:
                    fibo_levels['direction'] = latest['fibo_direction']
                if 'fibo_swing_high' in latest:
                    fibo_levels['swing_high'] = latest['fibo_swing_high']
                if 'fibo_swing_low' in latest:
                    fibo_levels['swing_low'] = latest['fibo_swing_low']
            except Exception as e:
                self.logger.error(f"เกิดข้อผิดพลาดในการดึงระดับ Fibonacci: {str(e)}")
            
            # ตรวจสอบการสอดคล้องกับแนวโน้ม BTC
            btc_aligned = False
            if (btc_trend == 'UPTREND' and 'BREAKOUT' in signal) or (btc_trend == 'DOWNTREND' and 'BREAKDOWN' in signal):
                btc_aligned = True
            
            # รวมผลลัพธ์
            return {
                'symbol': symbol, 
                'interval': interval, 
                'price': current_price, 
                'momentum_score': total_score, 
                'score_10': score_10, 
                'signal': signal, 
                'strength': abs(total_score), 
                'price_momentum': price_momentum, 
                'volume_momentum': volume_momentum, 
                'pattern_score': pattern_score, 
                'indicator_score': indicator_score, 
                'higher_tf_score': higher_tf_score, 
                'fibo_score': fibo_score, 
                'btc_correlation_score': btc_correlation_score, 
                'btc_correlation': correlation, 
                'btc_aligned': btc_aligned,
                'higher_tf_trend': higher_tf_analysis['trend'], 
                'pattern': translated_patterns, 
                'entry': entry_price, 
                'stop_loss': stop_loss, 
                'take_profit': take_profit, 
                'fibo_levels': fibo_levels, 
                'fibo_support': latest.get('nearest_fibo_support_price'), 
                'fibo_resistance': latest.get('nearest_fibo_resistance_price'), 
                'fibo_support_level': latest.get('nearest_fibo_support_level'), 
                'fibo_resistance_level': latest.get('nearest_fibo_resistance_level'), 
                'extra': {
                    'price_change_1d': change_1d, 
                    'price_change_3d': change_3d, 
                    'volume_ratio': volume_ratio, 
                    'rsi': rsi, 
                    'macd': macd, 
                    'macd_hist': macd_hist, 
                    'bb_percent_b': bb_percent_b, 
                    'nearest_resistance': nearest_resistance, 
                    'nearest_support': nearest_support, 
                    'distance_to_resistance': latest.get('distance_to_resistance', None), 
                    'distance_to_support': latest.get('distance_to_support', None), 
                    'atr_pct': latest.get('atr_pct', 0), 
                    'atr': atr, 
                    'squeeze_fire': latest.get('squeeze_fire', False), 
                    'trend_reversal': latest.get('trend_reversal', False), 
                    'breakout_up': breakout_up, 
                    'breakout_down': breakout_down, 
                    'higher_tf_support': higher_tf_analysis['support'], 
                    'higher_tf_resistance': higher_tf_analysis['resistance'], 
                    'btc_trend': btc_trend, 
                    'btc_signal': btc_signal
                }
            }
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการคำนวณโมเมนตัม {symbol}: {str(e)}")
            return {'symbol': symbol, 'interval': interval, 'momentum_score': 0, 'score_10': 0, 'signal': 'CONSOLIDATION', 'price': 0, 'pattern': []}

        def calculate_trade_levels(self, signal, price, atr, support, resistance, higher_tf_analysis):
            """คำนวณระดับการเข้าเทรด (Entry, Stop Loss, Take Profit)"""
            try:
                entry_price = price
                stop_loss = None
                take_profit = None
                
                atr_multiplier = self.settings['atr_stop_multiplier']
                tp_multiplier = self.settings['tp_multiplier']
                fibo_tp_level = self.settings['fibo_tp_level']
                fibo_sl_level = self.settings['fibo_sl_level']
                
                fibo_support = higher_tf_analysis.get('fibo_support')
                fibo_resistance = higher_tf_analysis.get('fibo_resistance')
                fibo_levels = higher_tf_analysis.get('fibo_levels', {})
                fibo_direction = fibo_levels.get('direction', 'up')
                
                if 'BREAKOUT' in signal:
                    entry_price = price * 0.995
                    
                    if fibo_direction == 'up' and fibo_levels and 'extension' in fibo_levels and isinstance(fibo_levels['extension'], dict) and str(fibo_tp_level) in fibo_levels['extension']:
                        tp_level = float(fibo_levels['extension'][str(fibo_tp_level)])
                        take_profit = tp_level
                    else:
                        if support and support < price:
                            stop_loss = min(support, price - (atr * atr_multiplier))
                            if fibo_support and fibo_support < price and fibo_support > stop_loss:
                                stop_loss = fibo_support
                        else:
                            stop_loss = price - (atr * atr_multiplier)
                        
                        risk = entry_price - stop_loss
                        
                        if resistance and resistance > price:
                            take_profit = max(resistance, entry_price + (risk * tp_multiplier))
                            if fibo_resistance and fibo_resistance > price and fibo_resistance > resistance:
                                take_profit = fibo_resistance
                        else:
                            take_profit = entry_price + (risk * tp_multiplier)
                            if fibo_resistance and fibo_resistance > price:
                                take_profit = max(take_profit, fibo_resistance)
                
                elif 'BREAKDOWN' in signal:
                    entry_price = price * 1.005
                    
                    if fibo_direction == 'down' and fibo_levels and 'extension' in fibo_levels and isinstance(fibo_levels['extension'], dict) and str(fibo_tp_level) in fibo_levels['extension']:
                        tp_level = float(fibo_levels['extension'][str(fibo_tp_level)])
                        take_profit = tp_level
                    else:
                        if resistance and resistance > price:
                            stop_loss = max(resistance, price + (atr * atr_multiplier))
                            if fibo_resistance and fibo_resistance > price and fibo_resistance < stop_loss:
                                stop_loss = fibo_resistance
                        else:
                            stop_loss = price + (atr * atr_multiplier)
                        
                        risk = stop_loss - entry_price
                        
                        if support and support < price:
                            take_profit = min(support, entry_price - (risk * tp_multiplier))
                            if fibo_support and fibo_support < price and fibo_support < support:
                                take_profit = fibo_support
                        else:
                            take_profit = entry_price - (risk * tp_multiplier)
                            if fibo_support and fibo_support < price:
                                take_profit = min(take_profit, fibo_support)
                
                else:
                    return entry_price, None, None
                
                return entry_price, stop_loss, take_profit
                
            except Exception as e:
                self.logger.error(f"เกิดข้อผิดพลาดในการคำนวณระดับการเทรด: {str(e)}")
                return price, None, None        
            
            
            
        def get_potential_coins(self):
                """ดึงรายชื่อเหรียญที่มีศักยภาพจาก Binance"""
                try:
                    self.console.print("[blue]กำลังดึงข้อมูลเหรียญจาก Binance...[/blue]")
                    
                    # ดึงข้อมูลเหรียญทั้งหมดจาก Binance
                    exchange_info = self.client.futures_exchange_info()
                    symbols = [s['symbol'] for s in exchange_info['symbols'] if s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT']
                    
                    self.console.print(f"[blue]พบเหรียญทั้งหมด {len(symbols)} เหรียญ[/blue]")
                    
                    # ดึงข้อมูลราคาและปริมาณการซื้อขาย
                    tickers = self.client.futures_ticker()
                    potential_coins = []
                    
                    for ticker in tickers:
                        if ticker['symbol'] in symbols:
                            symbol = ticker['symbol']
                            price = float(ticker['lastPrice'])
                            volume = float(ticker['quoteVolume'])
                            price_change = float(ticker['priceChangePercent'])
                            
                            # คัดกรองเหรียญที่มีปริมาณการซื้อขายสูงพอ
                            if volume >= self.settings['min_daily_volume']:
                                volatility = abs(price_change)
                                volume_score = min(10, volume / 10000000)
                                initial_score = (volatility * 0.7) + (volume_score * 0.3)
                                potential_coins.append({
                                    'symbol': symbol, 
                                    'price': price, 
                                    'price_change': price_change, 
                                    'volume': volume, 
                                    'initial_score': initial_score
                                })
                    
                    # เรียงลำดับเหรียญตามคะแนนเบื้องต้น
                    potential_coins.sort(key=lambda x: x['initial_score'], reverse=True)
                    selected_coins = potential_coins[:self.settings['max_coins']]
                    
                    self.console.print(f"[green]เลือก {len(selected_coins)} เหรียญเพื่อวิเคราะห์โมเมนตัม[/green]")
                    
                    return selected_coins
                    
                except Exception as e:
                    self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงข้อมูลเหรียญ: {str(e)}[/red]")
                    self.logger.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลเหรียญ: {str(e)}")
                    return []

            def scan_for_momentum(self, timeframe=None):
                """สแกนหาเหรียญที่มีโมเมนตัมสูง"""
                try:
                    start_time = time.time()
                    timeframe = timeframe or self.settings['default_timeframe']
                    
                    self.console.print(f"[blue]🔍 กำลังสแกนหาเหรียญที่มีโมเมนตัมสูง (timeframe: {timeframe} ร่วมกับ {self.settings['higher_timeframe']})...[/blue]")
                    
                    # วิเคราะห์ BTC ก่อน
                    btc_analysis = self.analyze_btc_trend()
                    btc_trend = btc_analysis.get('primary', {}).get('trend', 'NEUTRAL')
                    btc_signal = btc_analysis.get('primary', {}).get('signal', 'CONSOLIDATION')
                    btc_score = btc_analysis.get('primary', {}).get('momentum_score', 0)
                    btc_score_10 = btc_analysis.get('primary', {}).get('score_10', 0)
                    
                    if btc_trend == 'UPTREND':
                        self.console.print(f"[green]📈 ตลาดอยู่ในแนวโน้มขาขึ้น - เน้นหาสัญญาณ BREAKOUT (คะแนน BTC: {btc_score_10:.1f}/10)[/green]")
                    elif btc_trend == 'DOWNTREND':
                        self.console.print(f"[red]📉 ตลาดอยู่ในแนวโน้มขาลง - เน้นหาสัญญาณ BREAKDOWN (คะแนน BTC: {btc_score_10:.1f}/10)[/red]")
                    else:
                        self.console.print(f"[yellow]⏸️ ตลาดอยู่ในแนวโน้ม NEUTRAL - ระมัดระวังในการเทรด (คะแนน BTC: {btc_score_10:.1f}/10)[/yellow]")
                    
                    # หาเหรียญที่มีศักยภาพ
                    potential_coins = self.get_potential_coins()
                    if not potential_coins:
                        self.console.print("[red]ไม่พบเหรียญที่เหมาะสมสำหรับการวิเคราะห์[/red]")
                        return
                    
                    # เริ่มวิเคราะห์เหรียญแต่ละตัว
                    all_results = []
                    with Progress(TextColumn("[progress.description]{task.description}"), BarColumn(), TaskProgressColumn()) as progress:
                        scan_task = progress.add_task("[cyan]กำลังวิเคราะห์โมเมนตัม...", total=len(potential_coins))
                        
                        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                            futures = {executor.submit(self.calculate_momentum_score, coin['symbol'], timeframe): coin['symbol'] for coin in potential_coins}
                            
                            for future in concurrent.futures.as_completed(futures):
                                symbol = futures[future]
                                progress.update(scan_task, advance=1, description=f"[cyan]กำลังวิเคราะห์ {symbol}")
                                
                                try:
                                    result = future.result()
                                    if result and 'momentum_score' in result and result['price'] > 0:
                                        coin_data = next((c for c in potential_coins if c['symbol'] == symbol), {})
                                        result.update({
                                            'price_change_pct': coin_data.get('price_change', 0), 
                                            'volume_usd': coin_data.get('volume', 0)
                                        })
                                        all_results.append(result)
                                except Exception as e: 
                                    self.logger.error(f"เกิดข้อผิดพลาดในการวิเคราะห์ {symbol}: {str(e)}")
                    
                    # แยกผลลัพธ์ตามสัญญาณ
                    results_by_signal = {signal: [] for signal in self.terms}
                    
                    for result in all_results:
                        signal = result['signal']
                        btc_aligned = False
                        
                        if (btc_trend == 'UPTREND' and 'BREAKOUT' in signal) or (btc_trend == 'DOWNTREND' and 'BREAKDOWN' in signal):
                            btc_aligned = True
                            result['btc_aligned'] = True
                        
                        results_by_signal[signal].append(result)
                    
                    # เรียงลำดับผลลัพธ์
                    for signal in results_by_signal:
                        if 'BREAKOUT' in signal:
                            results_by_signal[signal].sort(key=lambda x: (x.get('btc_aligned', False) != True, -x.get('score_10', 0)))
                        elif 'BREAKDOWN' in signal:
                            results_by_signal[signal].sort(key=lambda x: (x.get('btc_aligned', False) != True, -x.get('score_10', 0)))
                        else:
                            results_by_signal[signal].sort(key=lambda x: -x.get('score_10', 0))
                    
                    # เก็บผลลัพธ์ไว้ใน cache
                    self.cache['momentum_scores'] = {r['symbol']: r for r in all_results}
                    self.cache['scan_results'] = results_by_signal
                    self.cache['last_scan'] = datetime.datetime.now()
                    
                    # แสดงผลสรุป
                    self.display.display_scan_summary(
                        results_by_signal, 
                        time.time() - start_time, 
                        self.cache, 
                        self.console, 
                        self.terms, 
                        self.advice, 
                        self.fibo_names
                    )
                    
                    return results_by_signal
                    
                except Exception as e:
                    self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน: {str(e)}[/red]")
                    self.logger.error(f"เกิดข้อผิดพลาดในการสแกน: {str(e)}")
                    return None

            def display_interesting_coins(self, results):
                """แสดงเหรียญที่น่าสนใจสำหรับการเทรด"""
                try:
                    if not results:
                        self.console.print("[red]ไม่มีข้อมูลเหรียญที่น่าสนใจ[/red]")
                        return
                    
                    self.console.print("\n[bold green]===== เหรียญที่น่าสนใจสำหรับการเทรด =====")
                    
                    # รวมเหรียญที่น่าสนใจทั้งหมด
                    interesting_coins = []
                    
                    # เติมเหรียญ breakout ก่อน (ในกรณีที่ BTC อยู่ในแนวโน้มขาขึ้น)
                    if self.cache['btc_analysis'].get('primary', {}).get('trend', 'NEUTRAL') == 'UPTREND':
                        for coin in results.get('STRONG_BREAKOUT', []):
                            if coin.get('btc_aligned', False) and coin.get('score_10', 0) >= 6.5:
                                interesting_coins.append(coin)
                        
                        for coin in results.get('BREAKOUT', []):
                            if coin.get('btc_aligned', False) and coin.get('score_10', 0) >= 6.0:
                                interesting_coins.append(coin)
                    
                    # เติมเหรียญ breakdown (ในกรณีที่ BTC อยู่ในแนวโน้มขาลง)
                    if self.cache['btc_analysis'].get('primary', {}).get('trend', 'NEUTRAL') == 'DOWNTREND':
                        for coin in results.get('STRONG_BREAKDOWN', []):
                            if coin.get('btc_aligned', False) and coin.get('score_10', 0) >= 6.5:
                                interesting_coins.append(coin)
                        
                        for coin in results.get('BREAKDOWN', []):
                            if coin.get('btc_aligned', False) and coin.get('score_10', 0) >= 6.0:
                                interesting_coins.append(coin)
                    
                    # เติมเหรียญที่น่าสนใจเพิ่มเติมที่ไม่สอดคล้องกับ BTC แต่มีสัญญาณแข็งแกร่ง
                    if len(interesting_coins) < self.settings['max_display_coins']:
                        for signal in ['STRONG_BREAKOUT', 'BREAKOUT', 'STRONG_BREAKDOWN', 'BREAKDOWN']:
                            for coin in results.get(signal, []):
                                if coin not in interesting_coins and coin.get('score_10', 0) >= 7.0:
                                    interesting_coins.append(coin)
                                    
                                    if len(interesting_coins) >= self.settings['max_display_coins']:
                                        break
                            
                            if len(interesting_coins) >= self.settings['max_display_coins']:
                                break
                    
                    # แสดงเหรียญที่น่าสนใจ
                    if interesting_coins:
                        interesting_coins.sort(key=lambda x: -x.get('score_10', 0))
                        
                        for coin in interesting_coins[:self.settings['max_display_coins']]:
                            self.display_coin_analysis(coin['symbol'])
                    else:
                        self.console.print("[yellow]ไม่พบเหรียญที่น่าสนใจในขณะนี้ โปรดลองอีกครั้งในภายหลัง[/yellow]")
                    
                    # แสดงข้อมูล BTC
                    self.display_btc_analysis()
                
                except Exception as e:
                    self.console.print(f"[red]เกิดข้อผิดพลาดในการแสดงเหรียญที่น่าสนใจ: {str(e)}[/red]")
                    self.logger.error(f"เกิดข้อผิดพลาดในการแสดงเหรียญที่น่าสนใจ: {str(e)}")
            
            def display_coin_analysis(self, symbol):
                """แสดงผลการวิเคราะห์เหรียญ"""
                try:
                    if not self.cache['btc_analysis']:
                        self.analyze_btc_trend()
                    
                    if symbol.upper() == 'BTCUSDT':
                        self.display_btc_analysis()
                        return
                    
                    if symbol in self.cache['momentum_scores']: 
                        coin_data = self.cache['momentum_scores'][symbol]
                    else:
                        self.console.print(f"[yellow]กำลังวิเคราะห์ {symbol}...[/yellow]")
                        coin_data = self.calculate_momentum_score(symbol)
                    
                    if not coin_data or coin_data.get('price', 0) == 0:
                        self.console.print(f"[red]ไม่สามารถวิเคราะห์ {symbol} ได้[/red]")
                        return
                    
                    # แสดงผลการวิเคราะห์
                    self.display.display_coin_analysis(
                        symbol, 
                        coin_data, 
                        self.cache['btc_analysis'], 
                        self.console, 
                        self.terms, 
                        self.advice, 
                        self.fibo_names
                    )
                    
                except Exception as e:
                    self.logger.error(f"เกิดข้อผิดพลาดในการแสดงการวิเคราะห์ {symbol}: {str(e)}")
                    self.console.print(f"[red]เกิดข้อผิดพลาดในการแสดงการวิเคราะห์: {str(e)}[/red]")
            
            def display_btc_analysis(self):
                """แสดงผลการวิเคราะห์ Bitcoin"""
                try:
                    if not self.cache['btc_analysis']:
                        self.analyze_btc_trend()
                    
                    # แสดงผลการวิเคราะห์ BTC
                    self.display.display_btc_analysis(
                        self.cache['btc_analysis'], 
                        self.console, 
                        self.terms, 
                        self.advice, 
                        self.fibo_names
                    )
                    
                except Exception as e:
                    self.logger.error(f"เกิดข้อผิดพลาดในการแสดงการวิเคราะห์ Bitcoin: {str(e)}")
                    self.console.print(f"[red]เกิดข้อผิดพลาดในการแสดงการวิเคราะห์ Bitcoin: {str(e)}[/red]")