#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, time, datetime, json, traceback, logging, argparse
import pandas as pd, numpy as np
import concurrent.futures
from dotenv import load_dotenv
from binance.client import Client
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler("altcoin_momentum_scanner.log", encoding='utf-8'), logging.StreamHandler(stream=sys.stdout)])
logger = logging.getLogger("AltcoinMomentumScanner")
class AltcoinMomentumScanner:
    def __init__(self):
        try:
            load_dotenv(override=True)
            self.api_key, self.secret_key = os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_SECRET_KEY')
            if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env")
            self.client = Client(self.api_key, self.secret_key)
            self.console = Console()
            self.settings = {
                'timeframes': ['1h', '4h', '1d'], 'default_timeframe': '1h',
                'higher_timeframe': '4h',  # กำหนด timeframe ที่สูงกว่าสำหรับ Multi-Timeframe Analysis
                'max_coins': 1300, 'min_daily_volume': 1000000,
                'rsi_period': 14, 'macd_fast': 12, 'macd_slow': 26, 'macd_signal': 9,
                'bb_period': 20, 'bb_std': 2.0, 'atr_period': 14, 'volume_ma_period': 20,
                'volume_surge_threshold': 1.5, 'price_change_threshold': 2.0,
                'breakout_threshold': 0.5, 'breakdown_threshold': 0.5, 'min_score': 5.0,
                'price_momentum_weight': 0.30, 'volume_weight': 0.25,
                'pattern_weight': 0.25, 'indicator_weight': 0.20,
                # เพิ่มน้ำหนักสำหรับการวิเคราะห์ Multi-Timeframe
                'higher_tf_weight': 0.4,  # น้ำหนักของ timeframe ที่สูงกว่า (4h)
                'lower_tf_weight': 0.6,   # น้ำหนักของ timeframe หลัก (1h)
            }
            self.cache = {
                'candles': {}, 'tickers': {}, 'last_update': {}, 
                'momentum_scores': {}, 'last_scan': None,
                'scan_results': {'STRONG_BREAKOUT': [], 'BREAKOUT': [], 
                                'BREAKDOWN': [], 'STRONG_BREAKDOWN': [], 'CONSOLIDATION': []}
            }
            # คำศัพท์สำหรับสัญญาณ (ภาษาไทย)
            self.terms = {
                'STRONG_BREAKOUT': '📈🔥 ทะลุแนวต้านแข็งแกร่ง', 
                'BREAKOUT': '📈 ทะลุแนวต้าน',
                'BREAKDOWN': '📉 หลุดแนวรับ', 
                'STRONG_BREAKDOWN': '📉🔥 หลุดแนวรับแข็งแกร่ง',
                'CONSOLIDATION': '⏸️ กำลังสะสม'
            }
            # คำแนะนำการเทรด (ภาษาไทย)
            self.advice = {
                'STRONG_BREAKOUT': 'เหมาะสำหรับการเข้า Long ด้วยปริมาณสูง - เกิดการทะลุแนวต้านที่มีปริมาณการซื้อขายสูงและตัวชี้วัดหลายตัวยืนยัน',
                'BREAKOUT': 'พิจารณาเข้า Long ด้วยความระมัดระวัง - รอการทดสอบแนวต้านเดิมที่ทะลุไปเพื่อความมั่นใจเพิ่มเติม',
                'BREAKDOWN': 'พิจารณาเข้า Short ด้วยความระมัดระวัง - รอการทดสอบแนวรับเดิมที่หลุดไปเพื่อความมั่นใจเพิ่มเติม',
                'STRONG_BREAKDOWN': 'เหมาะสำหรับการเข้า Short ด้วยปริมาณสูง - เกิดการหลุดแนวรับที่มีปริมาณการซื้อขายสูงและตัวชี้วัดหลายตัวยืนยัน',
                'CONSOLIDATION': 'รอสัญญาณที่ชัดเจน - กำลังอยู่ในช่วงสะสมที่อาจนำไปสู่การทะลุแนวต้านหรือหลุดแนวรับในอนาคต'
            }
            # คำแปลรูปแบบกราฟ (Chart Patterns) เป็นภาษาไทย
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
            logger.info("เริ่มต้นระบบสำเร็จ")
            self.console.print("[green]🚀 เริ่มต้นระบบ AltcoinMomentumScanner สำเร็จ[/green]")
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาด: {str(e)}")
            sys.exit(1)
    def translate_pattern(self, pattern):
        """แปลชื่อรูปแบบกราฟ"""
        if pattern in self.pattern_names:
            return self.pattern_names[pattern]
        return pattern  # ถ้าไม่มีคำแปล ให้คืนค่าเดิม
    def ensure_dataframe(self, data):
        if data is None: return pd.DataFrame()
        if isinstance(data, pd.DataFrame): return data
        try:
            if isinstance(data, (list, np.ndarray)):
                if not data: return pd.DataFrame()
                if isinstance(data[0], (list, np.ndarray)):
                    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                           'quote_volume', 'trades', 'taker_buy_volume', 'taker_buy_quote_volume', 'ignore']
                    if len(data[0]) < len(cols): cols = cols[:len(data[0])]
                    return pd.DataFrame(data, columns=cols)
                else: return pd.DataFrame([data])
            else: return pd.DataFrame([data])
        except Exception as e:
            logger.error(f"ไม่สามารถแปลงข้อมูลเป็น DataFrame: {str(e)}")
            return pd.DataFrame()
    def get_klines(self, symbol, interval, limit=200):
        try:
            cache_key = f"{symbol}_{interval}_{limit}"
            current_time = time.time()
            if cache_key in self.cache['candles'] and current_time - self.cache['last_update'].get(cache_key, 0) < 300:
                return self.ensure_dataframe(self.cache['candles'][cache_key])
            binance_interval = {
                '1m': Client.KLINE_INTERVAL_1MINUTE, '3m': Client.KLINE_INTERVAL_3MINUTE,
                '5m': Client.KLINE_INTERVAL_5MINUTE, '15m': Client.KLINE_INTERVAL_15MINUTE,
                '30m': Client.KLINE_INTERVAL_30MINUTE, '1h': Client.KLINE_INTERVAL_1HOUR,
                '2h': Client.KLINE_INTERVAL_2HOUR, '4h': Client.KLINE_INTERVAL_4HOUR,
                '6h': Client.KLINE_INTERVAL_6HOUR, '8h': Client.KLINE_INTERVAL_8HOUR,
                '12h': Client.KLINE_INTERVAL_12HOUR, '1d': Client.KLINE_INTERVAL_1DAY,
                '3d': Client.KLINE_INTERVAL_3DAY, '1w': Client.KLINE_INTERVAL_1WEEK,
                '1M': Client.KLINE_INTERVAL_1MONTH
            }.get(interval, Client.KLINE_INTERVAL_1HOUR)
            klines = self.client.futures_klines(symbol=symbol, interval=binance_interval, limit=limit)
            if not klines or len(klines) < 30:
                logger.warning(f"ข้อมูลแท่งเทียน {symbol} ไม่เพียงพอ: {len(klines) if klines else 0} แท่ง")
                return pd.DataFrame()
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                'quote_volume', 'trades', 'taker_buy_volume', 'taker_buy_quote_volume', 'ignore'
            ])
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_volume',
                           'taker_buy_volume', 'taker_buy_quote_volume']
            for col in numeric_cols: df[col] = pd.to_numeric(df[col])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            df['trades'] = df['trades'].astype(int)
            self._calculate_indicators(df)
            self._identify_chart_patterns(df)
            self.cache['candles'][cache_key] = df
            self.cache['last_update'][cache_key] = current_time
            return df
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลแท่งเทียน {symbol}: {str(e)}")
            return pd.DataFrame()
    def _calculate_indicators(self, df):
        try:
            # 1. ตัวชี้วัดพื้นฐาน
            df['body'] = abs(df['close'] - df['open'])
            df['range'] = df['high'] - df['low']
            df['body_pct'] = (df['body'] / df['range'].replace(0, np.nan)) * 100
            df['bullish'] = df['close'] > df['open']
            df['upper_wick'] = np.where(df['bullish'], df['high'] - df['close'], df['high'] - df['open'])
            df['lower_wick'] = np.where(df['bullish'], df['open'] - df['low'], df['close'] - df['low'])
            # 2. การเปลี่ยนแปลงของราคา
            for period in [1, 3, 5, 7, 14]:
                if len(df) > period: df[f'change_{period}d'] = (df['close'] / df['close'].shift(period) - 1) * 100
            # 3. โมเมนตัมของปริมาณการซื้อขาย
            vol_ma = self.settings['volume_ma_period']
            df['volume_ma'] = df['volume'].rolling(window=vol_ma).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']
            vol_mean = df['volume'].rolling(window=30).mean()
            vol_std = df['volume'].rolling(window=30).std()
            df['volume_zscore'] = (df['volume'] - vol_mean) / vol_std.replace(0, 1)
            # On-Balance Volume (OBV)
            df['obv'] = np.nan
            df.loc[0, 'obv'] = df.loc[0, 'volume']
            for i in range(1, len(df)):
                if df.loc[i, 'close'] > df.loc[i-1, 'close']: df.loc[i, 'obv'] = df.loc[i-1, 'obv'] + df.loc[i, 'volume']
                elif df.loc[i, 'close'] < df.loc[i-1, 'close']: df.loc[i, 'obv'] = df.loc[i-1, 'obv'] - df.loc[i, 'volume']
                else: df.loc[i, 'obv'] = df.loc[i-1, 'obv']
            # 4. ความผันผวน (Volatility)
            df['tr'] = np.maximum.reduce([
                df['high'] - df['low'],
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            ])
            df['atr'] = df['tr'].rolling(window=self.settings['atr_period']).mean()
            df['atr_pct'] = (df['atr'] / df['close']) * 100
            # 5. Bollinger Bands
            bb_period, bb_std = self.settings['bb_period'], self.settings['bb_std']
            df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
            df['bb_std'] = df['close'].rolling(window=bb_period).std()
            df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * bb_std)
            df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * bb_std)
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
            df['bb_percent_b'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
            # 6. RSI
            rsi_period = self.settings['rsi_period']
            delta = df['close'].diff()
            gain, loss = delta.where(delta > 0, 0), -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(window=rsi_period).mean()
            avg_loss = loss.rolling(window=rsi_period).mean()
            rs = avg_gain / avg_loss.replace(0, 1e-9)  # ป้องกันการหารด้วย 0
            df['rsi'] = 100 - (100 / (1 + rs))
            # 7. MACD
            fast, slow, signal = self.settings['macd_fast'], self.settings['macd_slow'], self.settings['macd_signal']
            df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
            df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
            df['macd'] = df['ema_fast'] - df['ema_slow']
            df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']
            df['macd_hist_change'] = df['macd_hist'].diff()
            # 8. Stochastic RSI
            stoch_period = 14
            if len(df) >= stoch_period:
                df['stoch_k'] = 100 * ((df['close'] - df['low'].rolling(window=stoch_period).min()) / 
                                    (df['high'].rolling(window=stoch_period).max() - df['low'].rolling(window=stoch_period).min()))
                df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
                rsi_min = df['rsi'].rolling(window=stoch_period).min()
                rsi_max = df['rsi'].rolling(window=stoch_period).max()
                df['stoch_rsi'] = 100 * ((df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 1e-9))
                df['stoch_rsi_d'] = df['stoch_rsi'].rolling(window=3).mean()
            # 9. แนวรับแนวต้านสำคัญ
            self._identify_support_resistance(df)
            # 10. Squeeze Momentum Indicator
            bb_avg = df['bb_width'].rolling(window=20).mean()
            df['squeeze_on'] = df['bb_width'] < bb_avg * 0.8
            df['squeeze_fire'] = (df['squeeze_on'].shift(1) == True) & (df['squeeze_on'] == False) & (abs(df['change_1d']) > 2)
            # 11. สัญญาณการเปลี่ยนแปลงแนวโน้ม
            df['trend_reversal'] = False
            bullish_reversal = ((df['rsi'].shift(1) < 30) & (df['rsi'] > 30) & 
                              (df['macd_hist'].shift(1) < 0) & (df['macd_hist'] > 0) & (df['close'] > df['open']))
            bearish_reversal = ((df['rsi'].shift(1) > 70) & (df['rsi'] < 70) & 
                              (df['macd_hist'].shift(1) > 0) & (df['macd_hist'] < 0) & (df['close'] < df['open']))
            df.loc[bullish_reversal | bearish_reversal, 'trend_reversal'] = True
            # 12. แนวโน้มทิศทางหลัก
            df['uptrend'] = False
            df['downtrend'] = False
            # ตรวจสอบแนวโน้มโดยใช้ EMA 50 และ EMA 200
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
            # กำหนดแนวโน้มขาขึ้น: ราคา > EMA50 > EMA200
            df['uptrend'] = (df['close'] > df['ema50']) & (df['ema50'] > df['ema200'])
            # กำหนดแนวโน้มขาลง: ราคา < EMA50 < EMA200
            df['downtrend'] = (df['close'] < df['ema50']) & (df['ema50'] < df['ema200'])
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาดในการคำนวณตัวชี้วัด: {str(e)}")
    def _identify_support_resistance(self, df):
        try:
            df['swing_high'] = df['swing_low'] = False
            if len(df) < 5: return
            for i in range(2, len(df) - 2):
                # swing high
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and
                    df['high'].iloc[i] > df['high'].iloc[i-2] and
                    df['high'].iloc[i] > df['high'].iloc[i+1] and
                    df['high'].iloc[i] > df['high'].iloc[i+2]):
                    df.iloc[i, df.columns.get_loc('swing_high')] = True
                # swing low
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and
                    df['low'].iloc[i] < df['low'].iloc[i-2] and
                    df['low'].iloc[i] < df['low'].iloc[i+1] and
                    df['low'].iloc[i] < df['low'].iloc[i+2]):
                    df.iloc[i, df.columns.get_loc('swing_low')] = True
            recent_df = df.iloc[-30:].copy() if len(df) >= 30 else df.copy()
            resistance_points = recent_df.loc[recent_df['swing_high'], 'high'].tolist()
            recent_high = df['high'].iloc[-15:].max() if len(df) >= 15 else df['high'].max()
            support_points = recent_df.loc[recent_df['swing_low'], 'low'].tolist()
            recent_low = df['low'].iloc[-15:].min() if len(df) >= 15 else df['low'].min()
            resistance_points.append(recent_high)
            support_points.append(recent_low)
            current_price = df['close'].iloc[-1]
            resistance_above = [r for r in resistance_points if r > current_price]
            nearest_resistance = min(resistance_above) if resistance_above else None
            support_below = [s for s in support_points if s < current_price]
            nearest_support = max(support_below) if support_below else None
            if nearest_resistance:
                df['distance_to_resistance'] = ((nearest_resistance - current_price) / current_price) * 100
            else:
                df['distance_to_resistance'] = np.nan
            if nearest_support:
                df['distance_to_support'] = ((current_price - nearest_support) / current_price) * 100
            else:
                df['distance_to_support'] = np.nan
            df['nearest_resistance'] = nearest_resistance
            df['nearest_support'] = nearest_support
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาดในการระบุแนวรับแนวต้าน: {str(e)}")
    def _identify_chart_patterns(self, df):
        try:
            # 1. Breakout/Breakdown ระยะ 20 แท่ง
            df['hh20'] = df['high'].rolling(20).max()  
            df['ll20'] = df['low'].rolling(20).min()   
            volume_surge = df['volume'] > df['volume_ma'] * self.settings['volume_surge_threshold']
            df['breakout_up'] = (df['close'] > df['hh20'].shift(1)) & volume_surge
            df['breakout_down'] = (df['close'] < df['ll20'].shift(1)) & volume_surge
            # 2. รูปแบบ Flag / Pennant และอื่นๆ
            df['bull_flag'] = df['bear_flag'] = df['ascending_triangle'] = df['descending_triangle'] = False
            df['symmetrical_triangle'] = df['falling_wedge'] = df['rising_wedge'] = False
            df['head_and_shoulders'] = df['inv_head_and_shoulders'] = df['double_top'] = df['double_bottom'] = False
            df['hammer'] = df['shooting_star'] = df['bullish_engulfing'] = df['bearish_engulfing'] = False
            # ตรวจสอบช่วง 20 แท่งล่าสุด (ถ้ามีข้อมูลพอ)
            if len(df) >= 25:
                for i in range(5, len(df) - 5):
                    flag_pole_length = 5
                    if (df['close'].iloc[i] - df['close'].iloc[i-flag_pole_length]) / df['close'].iloc[i-flag_pole_length] > 0.05:
                        flag_length = 5
                        if i + flag_length < len(df):
                            flag_slope = np.polyfit(range(flag_length), df['close'].iloc[i:i+flag_length], 1)[0]
                            if -0.005 <= flag_slope <= 0.002:
                                flag_volatility = df['high'].iloc[i:i+flag_length].max() - df['low'].iloc[i:i+flag_length].min()
                                flag_volatility_pct = flag_volatility / df['close'].iloc[i]
                                if flag_volatility_pct < 0.05:
                                    df.iloc[i+flag_length, df.columns.get_loc('bull_flag')] = True
            # Triangle patterns and Wedges
            if len(df) >= 20:
                last_20 = df.iloc[-20:].copy()
                high_std = last_20['high'].std() / last_20['high'].mean()
                if high_std < 0.01:
                    low_trend = np.polyfit(range(len(last_20)), last_20['low'], 1)[0]
                    if low_trend > 0:
                        df.iloc[-1, df.columns.get_loc('ascending_triangle')] = True
                low_std = last_20['low'].std() / last_20['low'].mean()
                if low_std < 0.01:
                    high_trend = np.polyfit(range(len(last_20)), last_20['high'], 1)[0]
                    if high_trend < 0:
                        df.iloc[-1, df.columns.get_loc('descending_triangle')] = True
                high_trend = np.polyfit(range(len(last_20)), last_20['high'], 1)[0]
                low_trend = np.polyfit(range(len(last_20)), last_20['low'], 1)[0]
                if high_trend < 0 and low_trend < 0 and high_trend < low_trend:
                    df.iloc[-1, df.columns.get_loc('falling_wedge')] = True
                if high_trend > 0 and low_trend > 0 and high_trend > low_trend:
                    df.iloc[-1, df.columns.get_loc('rising_wedge')] = True
            # Head and Shoulders pattern
            if len(df) >= 30:
                try:
                    swing_highs = df.iloc[-30:].loc[df.iloc[-30:]['swing_high']].index.tolist()
                    if len(swing_highs) >= 3:
                        for i in range(len(swing_highs) - 2):
                            left_shoulder = df.loc[swing_highs[i]]['high']
                            head = df.loc[swing_highs[i+1]]['high']
                            right_shoulder = df.loc[swing_highs[i+2]]['high']
                            if (head > left_shoulder and head > right_shoulder and
                                abs(left_shoulder - right_shoulder) / left_shoulder < 0.1):
                                df.iloc[-1, df.columns.get_loc('head_and_shoulders')] = True
                                break
                    swing_lows = df.iloc[-30:].loc[df.iloc[-30:]['swing_low']].index.tolist()
                    if len(swing_lows) >= 3:
                        for i in range(len(swing_lows) - 2):
                            left_shoulder = df.loc[swing_lows[i]]['low']
                            head = df.loc[swing_lows[i+1]]['low']
                            right_shoulder = df.loc[swing_lows[i+2]]['low']
                            if (head < left_shoulder and head < right_shoulder and
                                abs(left_shoulder - right_shoulder) / left_shoulder < 0.1):
                                df.iloc[-1, df.columns.get_loc('inv_head_and_shoulders')] = True
                                break
                except Exception as e:
                    logger.error(f"เกิดข้อผิดพลาดในการระบุรูปแบบ Head and Shoulders: {str(e)}")
            # Double Top / Double Bottom
            if len(df) >= 20:
                try:
                    swing_highs = df.iloc[-20:].loc[df.iloc[-20:]['swing_high']].index.tolist()
                    if len(swing_highs) >= 2:
                        high1 = df.loc[swing_highs[-2]]['high']
                        high2 = df.loc[swing_highs[-1]]['high']
                        if abs(high1 - high2) / high1 < 0.03:
                            df.iloc[-1, df.columns.get_loc('double_top')] = True
                    swing_lows = df.iloc[-20:].loc[df.iloc[-20:]['swing_low']].index.tolist()
                    if len(swing_lows) >= 2:
                        low1 = df.loc[swing_lows[-2]]['low']
                        low2 = df.loc[swing_lows[-1]]['low']
                        if abs(low1 - low2) / low1 < 0.03:
                            df.iloc[-1, df.columns.get_loc('double_bottom')] = True
                except Exception as e:
                    logger.error(f"เกิดข้อผิดพลาดในการระบุรูปแบบ Double Top/Bottom: {str(e)}")
            # Candlestick patterns
            for i in range(1, len(df)):
                if (df['lower_wick'].iloc[i] > 2 * df['body'].iloc[i] and
                    df['upper_wick'].iloc[i] < df['body'].iloc[i] and
                    df['body'].iloc[i] > 0):
                    df.iloc[i, df.columns.get_loc('hammer')] = True
                if (df['upper_wick'].iloc[i] > 2 * df['body'].iloc[i] and
                    df['lower_wick'].iloc[i] < df['body'].iloc[i] and
                    df['body'].iloc[i] > 0):
                    df.iloc[i, df.columns.get_loc('shooting_star')] = True
                if (df['bullish'].iloc[i] and not df['bullish'].iloc[i-1] and
                    df['open'].iloc[i] < df['close'].iloc[i-1] and
                    df['close'].iloc[i] > df['open'].iloc[i-1]):
                    df.iloc[i, df.columns.get_loc('bullish_engulfing')] = True
                if (not df['bullish'].iloc[i] and df['bullish'].iloc[i-1] and
                    df['open'].iloc[i] > df['close'].iloc[i-1] and
                    df['close'].iloc[i] < df['open'].iloc[i-1]):
                    df.iloc[i, df.columns.get_loc('bearish_engulfing')] = True
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาดในการระบุรูปแบบกราฟ: {str(e)}")
    def analyze_higher_timeframe(self, symbol):
        """วิเคราะห์ timeframe ที่สูงกว่า (4h) เพื่อดูแนวโน้มใหญ่"""
        try:
            higher_tf = self.settings['higher_timeframe']
            df_higher = self.get_klines(symbol, higher_tf)
            if not isinstance(df_higher, pd.DataFrame) or df_higher.empty or len(df_higher) < 30:
                return {
                    'trend': 'NEUTRAL',
                    'strength': 0,
                    'support': None,
                    'resistance': None,
                    'patterns': []
                }
            latest = df_higher.iloc[-1].copy()
            # ระบุแนวโน้มหลัก
            trend = 'NEUTRAL'
            if latest.get('uptrend', False):
                trend = 'UPTREND'
            elif latest.get('downtrend', False):
                trend = 'DOWNTREND'
            # คะแนนความแข็งแรงของแนวโน้ม
            trend_strength = 0
            # ตรวจสอบแนวโน้มขาขึ้น
            if trend == 'UPTREND':
                # RSI สูงกว่า 50
                if latest.get('rsi', 50) > 50:
                    trend_strength += 1
                # MACD เป็นบวก
                if latest.get('macd', 0) > 0:
                    trend_strength += 1
                # ราคาอยู่เหนือ Bollinger Band กลาง
                if latest.get('close', 0) > latest.get('bb_middle', 0):
                    trend_strength += 1
                # มีรูปแบบกราฟขาขึ้น
                bullish_patterns = ['ascending_triangle', 'falling_wedge', 'double_bottom', 'inv_head_and_shoulders']
                for pattern in bullish_patterns:
                    if latest.get(pattern, False):
                        trend_strength += 1
                        break
            # ตรวจสอบแนวโน้มขาลง
            elif trend == 'DOWNTREND':
                # RSI ต่ำกว่า 50
                if latest.get('rsi', 50) < 50:
                    trend_strength += 1
                # MACD เป็นลบ
                if latest.get('macd', 0) < 0:
                    trend_strength += 1
                # ราคาอยู่ต่ำกว่า Bollinger Band กลาง
                if latest.get('close', 0) < latest.get('bb_middle', 0):
                    trend_strength += 1
                # มีรูปแบบกราฟขาลง
                bearish_patterns = ['descending_triangle', 'rising_wedge', 'double_top', 'head_and_shoulders']
                for pattern in bearish_patterns:
                    if latest.get(pattern, False):
                        trend_strength += 1
                        break
            # เก็บรูปแบบกราฟที่พบบน timeframe ที่สูงกว่า
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
            # แปลชื่อรูปแบบกราฟ
            translated_patterns = [self.translate_pattern(p) for p in patterns]
            return {
                'trend': trend,
                'strength': trend_strength,
                'support': latest.get('nearest_support'),
                'resistance': latest.get('nearest_resistance'),
                'patterns': translated_patterns
            }
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาดในการวิเคราะห์ timeframe ที่สูงขึ้น {symbol}: {str(e)}")
            return {
                'trend': 'NEUTRAL',
                'strength': 0,
                'support': None,
                'resistance': None,
                'patterns': []
            }
    def calculate_momentum_score(self, symbol, interval=None):
        try:
            if interval is None: interval = self.settings['default_timeframe']
            # วิเคราะห์ timeframe หลัก (1h)
            df = self.get_klines(symbol, interval)
            if not isinstance(df, pd.DataFrame) or df.empty or len(df) < 30:
                return {
                    'symbol': symbol, 'interval': interval, 'momentum_score': 0,
                    'signal': 'CONSOLIDATION', 'price': 0, 'pattern': []
                }
            # วิเคราะห์ timeframe ที่สูงกว่า (4h) - MTFA
            higher_tf_analysis = self.analyze_higher_timeframe(symbol)
            latest = df.iloc[-1].copy()
            # 1. โมเมนตัมของราคา
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
            # 2. โมเมนตัมของปริมาณการซื้อขาย
            volume_momentum = 0
            volume_ratio = latest.get('volume_ratio', 1)
            if volume_ratio > 1.5:
                volume_strength = min(3, (volume_ratio - 1) * 1.5)
                if (change_1d > 0 and latest['close'] > latest['open']) or (change_1d < 0 and latest['close'] < latest['open']):
                    volume_momentum = volume_strength
                else: volume_momentum = volume_strength * 0.3
            # 3. คะแนนจากรูปแบบกราฟ
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
            # ตรวจสอบรูปแบบกราฟอื่นๆ
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
            # 4. คะแนนจากตัวชี้วัดทางเทคนิค
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
            # 5. คะแนนจาก timeframe ที่สูงกว่า (MTFA)
            higher_tf_score = 0
            # คะแนนตามแนวโน้มของ timeframe สูงกว่า
            if higher_tf_analysis['trend'] == 'UPTREND':
                higher_tf_score = min(5, 2 + higher_tf_analysis['strength'])
                # โบนัสสำหรับแนวโน้มสอดคล้องกับ timeframe หลัก
                if price_momentum > 0:
                    higher_tf_score += 1
            elif higher_tf_analysis['trend'] == 'DOWNTREND':
                higher_tf_score = max(-5, -2 - higher_tf_analysis['strength'])
                # โบนัสสำหรับแนวโน้มสอดคล้องกับ timeframe หลัก
                if price_momentum < 0:
                    higher_tf_score -= 1
            # เพิ่มรูปแบบที่พบใน timeframe ที่สูงกว่า
            if higher_tf_analysis['patterns']:
                for pattern in higher_tf_analysis['patterns']:
                    if pattern not in pattern_list:
                        pattern_list.append(f"{pattern} (4H)")
            # 6. รวมคะแนนทั้งหมดโดยใช้การวิเคราะห์แบบ MTFA
            # คะแนนจาก timeframe หลัก (1h)
            lower_tf_score = (
                price_momentum * self.settings['price_momentum_weight'] +
                volume_momentum * self.settings['volume_weight'] +
                pattern_score * self.settings['pattern_weight'] +
                indicator_score * self.settings['indicator_weight']
            )
            # รวมคะแนนจากทั้งสอง timeframe ตามน้ำหนักที่กำหนด
            total_score = (
                lower_tf_score * self.settings['lower_tf_weight'] +
                higher_tf_score * self.settings['higher_tf_weight']
            )
            # กำหนดสัญญาณ
            signal = 'CONSOLIDATION'
            if total_score >= 2:
                signal = 'STRONG_BREAKOUT' if total_score >= 4 else 'BREAKOUT'
            elif total_score <= -2:
                signal = 'STRONG_BREAKDOWN' if total_score <= -4 else 'BREAKDOWN'
            # แปลชื่อรูปแบบกราฟตามภาษา
            translated_patterns = [self.translate_pattern(p) for p in pattern_list]
            return {
                'symbol': symbol, 
                'interval': interval,
                'price': latest['close'],
                'momentum_score': total_score,
                'signal': signal, 
                'strength': abs(total_score),
                'price_momentum': price_momentum,
                'volume_momentum': volume_momentum,
                'pattern_score': pattern_score,
                'indicator_score': indicator_score,
                'higher_tf_score': higher_tf_score,
                'higher_tf_trend': higher_tf_analysis['trend'],
                'pattern': translated_patterns,
                'extra': {
                    'price_change_1d': change_1d, 
                    'price_change_3d': change_3d,
                    'volume_ratio': volume_ratio, 
                    'rsi': rsi, 
                    'macd': macd, 
                    'macd_hist': macd_hist,
                    'bb_percent_b': bb_percent_b,
                    'nearest_resistance': latest.get('nearest_resistance', None),
                    'nearest_support': latest.get('nearest_support', None),
                    'distance_to_resistance': latest.get('distance_to_resistance', None),
                    'distance_to_support': latest.get('distance_to_support', None),
                    'atr_pct': latest.get('atr_pct', 0), 
                    'squeeze_fire': latest.get('squeeze_fire', False),
                    'trend_reversal': latest.get('trend_reversal', False),
                    'breakout_up': breakout_up, 
                    'breakout_down': breakout_down,
                    'higher_tf_support': higher_tf_analysis['support'],
                    'higher_tf_resistance': higher_tf_analysis['resistance']
                }
            }
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาดในการคำนวณโมเมนตัม {symbol}: {str(e)}")
            return {'symbol': symbol, 'interval': interval, 'momentum_score': 0, 
                   'signal': 'CONSOLIDATION', 'price': 0, 'pattern': []}
    def get_potential_coins(self):
        try:
            self.console.print("[blue]กำลังดึงข้อมูลเหรียญจาก Binance...[/blue]")
            exchange_info = self.client.futures_exchange_info()
            symbols = [s['symbol'] for s in exchange_info['symbols'] 
                      if s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT']
            self.console.print(f"[blue]พบเหรียญทั้งหมด {len(symbols)} เหรียญ[/blue]")
            tickers = self.client.futures_ticker()
            potential_coins = []
            for ticker in tickers:
                if ticker['symbol'] in symbols:
                    symbol = ticker['symbol']
                    price = float(ticker['lastPrice'])
                    volume = float(ticker['quoteVolume'])
                    price_change = float(ticker['priceChangePercent'])
                    if volume >= self.settings['min_daily_volume']:
                        volatility = abs(price_change)
                        volume_score = min(10, volume / 10000000)
                        initial_score = (volatility * 0.7) + (volume_score * 0.3)
                        potential_coins.append({
                            'symbol': symbol, 'price': price, 'price_change': price_change,
                            'volume': volume, 'initial_score': initial_score
                        })
            potential_coins.sort(key=lambda x: x['initial_score'], reverse=True)
            selected_coins = potential_coins[:self.settings['max_coins']]
            self.console.print(f"[green]เลือก {len(selected_coins)} เหรียญเพื่อวิเคราะห์โมเมนตัม[/green]")
            if selected_coins:
                table = Table(title="ตัวอย่างเหรียญที่จะวิเคราะห์")
                table.add_column("เหรียญ", style="cyan")
                table.add_column("ราคา", style="yellow")
                table.add_column("เปลี่ยนแปลง 24h", style="green")
                table.add_column("ปริมาณ (USD)", style="magenta")
                for coin in selected_coins[:5]:
                    change_color = "green" if coin['price_change'] > 0 else "red"
                    table.add_row(
                        coin['symbol'],
                        f"{coin['price']:.6f}",
                        f"[{change_color}]{coin['price_change']:+.2f}%[/{change_color}]",
                        f"${coin['volume']:,.0f}"
                    )
                self.console.print(table)
            return selected_coins
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงข้อมูลเหรียญ: {str(e)}[/red]")
            logger.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลเหรียญ: {str(e)}")
            return []
    def scan_for_momentum(self, timeframe=None):
        try:
            start_time = time.time()
            timeframe = timeframe or self.settings['default_timeframe']
            self.console.print(f"[blue]🔍 กำลังสแกนหาเหรียญที่มีโมเมนตัมสูง (timeframe: {timeframe} ร่วมกับ {self.settings['higher_timeframe']})...[/blue]")
            potential_coins = self.get_potential_coins()
            if not potential_coins:
                self.console.print("[red]ไม่พบเหรียญที่เหมาะสมสำหรับการวิเคราะห์[/red]")
                return
            all_results = []
            with Progress(TextColumn("[progress.description]{task.description}"), 
                         BarColumn(), TaskProgressColumn()) as progress:
                scan_task = progress.add_task("[cyan]กำลังวิเคราะห์โมเมนตัม...", total=len(potential_coins))
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(self.calculate_momentum_score, coin['symbol'], timeframe): 
                              coin['symbol'] for coin in potential_coins}
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
                            logger.error(f"เกิดข้อผิดพลาดในการวิเคราะห์ {symbol}: {str(e)}")
            results_by_signal = {signal: [] for signal in self.terms}
            for result in all_results:
                signal = result['signal']
                results_by_signal[signal].append(result)
            for signal in results_by_signal:
                results_by_signal[signal].sort(key=lambda x: abs(x['momentum_score']), reverse=True)
            self.cache['momentum_scores'] = {r['symbol']: r for r in all_results}
            self.cache['scan_results'] = results_by_signal
            self.cache['last_scan'] = datetime.datetime.now()
            self._display_scan_summary(results_by_signal, time.time() - start_time)
            self._save_scan_results(results_by_signal, timeframe)
            return results_by_signal
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน: {str(e)}[/red]")
            logger.error(f"เกิดข้อผิดพลาดในการสแกน: {str(e)}")
            return None
    def _display_scan_summary(self, results, duration):
        scan_time = self.cache['last_scan'].strftime('%Y-%m-%d %H:%M:%S')
        summary_table = Table(title=f"ผลการสแกนโมเมนตัม Altcoin (Timeframe: {self.settings['default_timeframe']} + {self.settings['higher_timeframe']}) - {scan_time}")
        summary_table.add_column("สัญญาณ", style="cyan")
        summary_table.add_column("จำนวน", style="yellow")
        summary_table.add_column("คำอธิบาย", style="white")
        counts = {s: len(results[s]) for s in results}
        total = sum(counts.values())
        summary_table.add_row(self.terms['STRONG_BREAKOUT'], f"{counts['STRONG_BREAKOUT']}", self.advice['STRONG_BREAKOUT'])
        summary_table.add_row(self.terms['BREAKOUT'], f"{counts['BREAKOUT']}", self.advice['BREAKOUT'])
        summary_table.add_row(self.terms['BREAKDOWN'], f"{counts['BREAKDOWN']}", self.advice['BREAKDOWN'])
        summary_table.add_row(self.terms['STRONG_BREAKDOWN'], f"{counts['STRONG_BREAKDOWN']}", self.advice['STRONG_BREAKDOWN'])
        summary_table.add_row(self.terms['CONSOLIDATION'], f"{counts['CONSOLIDATION']}", self.advice['CONSOLIDATION'])
        summary_table.add_row("📊 รวมทั้งหมด", f"{total}", f"ใช้เวลาวิเคราะห์ {duration:.1f} วินาที")
        self.console.print("\n")
        self.console.print(summary_table)
        # แสดงเหรียญที่น่าสนใจในแต่ละกลุ่ม
        for signal in ['STRONG_BREAKOUT', 'BREAKOUT', 'STRONG_BREAKDOWN', 'BREAKDOWN']:
            coins = results[signal]
            if not coins: continue
            signal_text = self.terms[signal]
            signal_color = "green" if "BREAKOUT" in signal else "red"
            coin_table = Table(title=f"{signal_text}")
            coin_table.add_column("เหรียญ", style="cyan")
            coin_table.add_column("ราคา", style="yellow")
            coin_table.add_column("คะแนน", style="magenta")
            coin_table.add_column("เปลี่ยนแปลง", style="green")
            coin_table.add_column("รูปแบบ", style="blue")
            for coin in coins[:5]:
                change_color = "green" if coin['extra']['price_change_1d'] > 0 else "red"
                pattern_text = coin['pattern'][0] if coin['pattern'] else "-"
                coin_table.add_row(
                    coin['symbol'],
                    f"{coin['price']:.6f}",
                    f"{coin['momentum_score']:.1f}",
                    f"[{change_color}]{coin['extra']['price_change_1d']:+.2f}%[/{change_color}]",
                    pattern_text
                )
            self.console.print(coin_table)
    def _save_scan_results(self, results, timeframe):
        try:
            os.makedirs("scan_results", exist_ok=True)
            scan_time = self.cache['last_scan'].strftime('%Y%m%d_%H%M%S')
            filename = f"scan_results/altcoin_scan_{timeframe}_{scan_time}.txt"
            with open(filename, 'w', encoding='utf-8') as file:
                file.write(f"======= ผลการสแกนโมเมนตัม Altcoin (Timeframe: {timeframe} + {self.settings['higher_timeframe']}) =======\n")
                file.write(f"วันเวลาที่สแกน: {self.cache['last_scan'].strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                counts = {s: len(results[s]) for s in results}
                total = sum(counts.values())
                file.write(f"พบเหรียญทั้งหมด {total} เหรียญ:\n")
                for signal, term in self.terms.items():
                    file.write(f"{term}: {counts[signal]} เหรียญ\n")
                file.write("\n")
                for signal in ['STRONG_BREAKOUT', 'BREAKOUT', 'BREAKDOWN', 'STRONG_BREAKDOWN']:
                    coins = results[signal]
                    if not coins: continue
                    file.write(f"=== {self.terms[signal]} ({len(coins)}) ===\n")
                    for i, coin in enumerate(coins, 1):
                        file.write(f"{i}. {coin['symbol']}: ราคา {coin['price']:.6f} | คะแนน: {coin['momentum_score']:.1f}\n")
                        file.write(f"   เปลี่ยนแปลง 24h: {coin['extra']['price_change_1d']:+.2f}%\n")
                        file.write(f"   แนวโน้ม 4H: {coin['higher_tf_trend']} | คะแนน 4H: {coin['higher_tf_score']:.1f}\n")
                        if coin['pattern']:
                            file.write(f"   รูปแบบกราฟ: {', '.join(coin['pattern'])}\n")
                        file.write(f"   RSI: {coin['extra']['rsi']:.1f} | MACD: {coin['extra']['macd']:.6f} | ")
                        file.write(f"ปริมาณ: {coin['extra']['volume_ratio']:.1f}x\n")
                        if coin['extra']['nearest_resistance'] is not None:
                            file.write(f"   แนวต้านถัดไป (1H): {coin['extra']['nearest_resistance']:.6f} ")
                            file.write(f"(ห่าง {coin['extra']['distance_to_resistance']:.1f}%)\n")
                        if coin['extra']['nearest_support'] is not None:
                            file.write(f"   แนวรับถัดไป (1H): {coin['extra']['nearest_support']:.6f} ")
                            file.write(f"(ห่าง {coin['extra']['distance_to_support']:.1f}%)\n")
                        if coin['extra']['higher_tf_resistance'] is not None:
                            file.write(f"   แนวต้านถัดไป (4H): {coin['extra']['higher_tf_resistance']:.6f}\n")
                        if coin['extra']['higher_tf_support'] is not None:
                            file.write(f"   แนวรับถัดไป (4H): {coin['extra']['higher_tf_support']:.6f}\n")
                        file.write(f"   คำแนะนำ: {self.advice[signal]}\n\n")
            # บันทึกเป็นไฟล์ JSON
            json_filename = f"scan_results/altcoin_scan_{timeframe}_{scan_time}.json"
            with open(json_filename, 'w', encoding='utf-8') as jsonfile:
                json_results = {}
                for signal, coins in results.items():
                    json_results[signal] = []
                    for coin in coins:
                        coin_copy = {}
                        for k, v in coin.items():
                            if k == 'extra':
                                coin_copy[k] = {}
                                for ek, ev in v.items():
                                    if isinstance(ev, (np.integer, np.floating)):
                                        coin_copy[k][ek] = float(ev)
                                    elif isinstance(ev, (bool, np.bool_)):
                                        coin_copy[k][ek] = bool(ev)
                                    elif ev is None:
                                        coin_copy[k][ek] = None
                                    else:
                                        try:
                                            json.dumps(ev)
                                            coin_copy[k][ek] = ev
                                        except (TypeError, OverflowError):
                                            coin_copy[k][ek] = str(ev)
                            elif isinstance(v, (np.integer, np.floating)):
                                coin_copy[k] = float(v)
                            elif isinstance(v, (bool, np.bool_)):
                                coin_copy[k] = bool(v)
                            elif isinstance(v, (list, tuple)):
                                coin_copy[k] = [str(item) if not isinstance(item, (str, int, float, bool, type(None))) else item for item in v]
                            else:
                                try:
                                    json.dumps(v)
                                    coin_copy[k] = v
                                except (TypeError, OverflowError):
                                    coin_copy[k] = str(v)
                        json_results[signal].append(coin_copy)
                try:
                    json.dumps(json_results)
                except (TypeError, OverflowError) as e:
                    logger.error(f"ยังคงมีปัญหาในการแปลง JSON: {str(e)}")
                    json_results = {"error": "ไม่สามารถบันทึกผลลัพธ์ทั้งหมดได้", "scan_time": scan_time}
                json.dump(json_results, jsonfile, indent=2, ensure_ascii=False)
            self.console.print(f"[green]บันทึกผลการสแกนลงไฟล์ {filename} และ {json_filename} เรียบร้อยแล้ว[/green]")
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาดในการบันทึกผลการสแกน: {str(e)}")
            try:
                error_filename = f"scan_results/error_log_{timeframe}_{scan_time}.txt"
                with open(error_filename, 'w', encoding='utf-8') as error_file:
                    error_file.write(f"เกิดข้อผิดพลาดในการบันทึกผลการสแกน: {str(e)}\n")
                    error_file.write(f"Traceback: {traceback.format_exc()}\n")
                self.console.print(f"[yellow]บันทึกข้อผิดพลาดลงไฟล์ {error_filename}[/yellow]")
            except:
                pass
    def display_coin_analysis(self, symbol):
        try:
            if symbol in self.cache['momentum_scores']:
                coin_data = self.cache['momentum_scores'][symbol]
            else:
                self.console.print(f"[yellow]กำลังวิเคราะห์ {symbol}...[/yellow]")
                coin_data = self.calculate_momentum_score(symbol)
            if not coin_data or coin_data.get('price', 0) == 0:
                self.console.print(f"[red]ไม่สามารถวิเคราะห์ {symbol} ได้[/red]")
                return
            signal = coin_data['signal']
            signal_text = self.terms[signal]
            signal_color = "green" if "BREAKOUT" in signal else "red" if "BREAKDOWN" in signal else "yellow"
            self.console.print(f"\n[blue]===== การวิเคราะห์ {symbol} =====")
            self.console.print(f"[{signal_color}]สัญญาณปัจจุบัน: {signal_text} (คะแนน: {coin_data['momentum_score']:.2f})[/{signal_color}]")
            price = coin_data['price']
            price_change_1d = coin_data['extra']['price_change_1d']
            price_change_3d = coin_data['extra']['price_change_3d']
            self.console.print(f"[white]ราคา: {price:.6f} | " +
                              f"เปลี่ยน 24h: [{'green' if price_change_1d > 0 else 'red'}]{price_change_1d:+.2f}%[/] | " +
                              f"เปลี่ยน 3 วัน: [{'green' if price_change_3d > 0 else 'red'}]{price_change_3d:+.2f}%[/]")
            # แสดงผลการวิเคราะห์ Multi-Timeframe
            higher_tf_trend = coin_data.get('higher_tf_trend', 'NEUTRAL')
            higher_tf_score = coin_data.get('higher_tf_score', 0)
            trend_color = "green" if higher_tf_trend == 'UPTREND' else "red" if higher_tf_trend == 'DOWNTREND' else "yellow"
            self.console.print(f"[white]แนวโน้ม 4H: [{trend_color}]{higher_tf_trend}[/{trend_color}] | " +
                              f"คะแนน 4H: {higher_tf_score:+.1f}")
            rsi = coin_data['extra']['rsi']
            macd = coin_data['extra']['macd']
            macd_hist = coin_data['extra']['macd_hist']
            volume_ratio = coin_data['extra']['volume_ratio']
            self.console.print(f"[white]RSI: [{'red' if rsi > 70 else 'green' if rsi < 30 else 'white'}]{rsi:.1f}[/] | " +
                              f"MACD: [{'green' if macd > 0 else 'red'}]{macd:.6f}[/] | " +
                              f"MACD Histogram: [{'green' if macd_hist > 0 else 'red'}]{macd_hist:.6f}[/] | " +
                              f"ปริมาณ: [{'green' if volume_ratio > 1.5 else 'white'}]{volume_ratio:.1f}x[/]")
            # แสดงแนวรับ/แนวต้านของทั้งสอง timeframe
            nearest_resistance = coin_data['extra']['nearest_resistance']
            nearest_support = coin_data['extra']['nearest_support']
            distance_to_resistance = coin_data['extra']['distance_to_resistance']
            distance_to_support = coin_data['extra']['distance_to_support']
            higher_tf_resistance = coin_data['extra']['higher_tf_resistance']
            higher_tf_support = coin_data['extra']['higher_tf_support']
            if nearest_resistance:
                self.console.print(f"[white]แนวต้านถัดไป (1H): {nearest_resistance:.6f} (ห่าง {distance_to_resistance:.1f}%)")
            if nearest_support:
                self.console.print(f"[white]แนวรับถัดไป (1H): {nearest_support:.6f} (ห่าง {distance_to_support:.1f}%)")
            if higher_tf_resistance:
                self.console.print(f"[white]แนวต้านถัดไป (4H): {higher_tf_resistance:.6f}")
            if higher_tf_support:
                self.console.print(f"[white]แนวรับถัดไป (4H): {higher_tf_support:.6f}")
            if coin_data['pattern']:
                self.console.print("[white]รูปแบบที่พบ:")
                for pattern in coin_data['pattern']:
                    if "(4H)" in pattern:
                        self.console.print(f"[yellow]- {pattern}[/yellow]")
                    else:
                        color = "green" if any(bullish in pattern.lower() for bullish in ['ทะลุแนวต้าน', 'สามเหลี่ยมฐานยก', 'ลิ่มเอียงลง', 'ธงกระทิง', 'หัวและไหล่กลับหัว', 'ฐานคู่', 'ค้อน', 'แท่งเขียวกลืนแท่งแดง', 'ตัดขึ้น']) else "red"
                        self.console.print(f"[{color}]- {pattern}[/{color}]")
            extra = coin_data['extra']
            if extra['squeeze_fire']:
                self.console.print("[magenta]🔥 Volatility Squeeze - โอกาสเกิดการเคลื่อนไหวรุนแรง[/magenta]")
            if extra['trend_reversal']:
                self.console.print("[yellow]⚠️ สัญญาณกลับตัวของแนวโน้ม - อาจเกิดการเปลี่ยนทิศทาง[/yellow]")
            self.console.print(f"\n[white]คำแนะนำ: [{signal_color}]{self.advice[signal]}[/{signal_color}]")
            if "BREAKOUT" in signal:
                atr = extra['atr_pct'] * price / 100 if 'atr_pct' in extra else price * 0.01
                suggested_stop = price - (1.5 * atr)
                potential_target = nearest_resistance if nearest_resistance else higher_tf_resistance if higher_tf_resistance else price * 1.1
                self.console.print(f"[white]การจัดการความเสี่ยง:")
                self.console.print(f"- จุดเข้า: {price:.6f} (หรือรอ Retest แนวต้านเดิม)")
                self.console.print(f"- จุดตัดขาดทุนแนะนำ: {suggested_stop:.6f} (ประมาณ 1.5 ATR)")
                self.console.print(f"- เป้าหมายแนะนำ: {potential_target:.6f}")
                rr_ratio = ((potential_target - price) / (price - suggested_stop))
                self.console.print(f"- Risk:Reward Ratio: {rr_ratio:.2f}:1")
            elif "BREAKDOWN" in signal:
                atr = extra['atr_pct'] * price / 100 if 'atr_pct' in extra else price * 0.01
                suggested_stop = price + (1.5 * atr)
                potential_target = nearest_support if nearest_support else higher_tf_support if higher_tf_support else price * 0.9
                self.console.print(f"[white]การจัดการความเสี่ยง:")
                self.console.print(f"- จุดเข้า: {price:.6f} (หรือรอ Retest แนวรับเดิม)")
                self.console.print(f"- จุดตัดขาดทุนแนะนำ: {suggested_stop:.6f} (ประมาณ 1.5 ATR)")
                self.console.print(f"- เป้าหมายแนะนำ: {potential_target:.6f}")
                rr_ratio = ((price - potential_target) / (suggested_stop - price))
                self.console.print(f"- Risk:Reward Ratio: {rr_ratio:.2f}:1")
            self.console.print(f"[blue]=====================================[/blue]\n")
        except Exception as e:
            logger.error(f"เกิดข้อผิดพลาดในการแสดงการวิเคราะห์ {symbol}: {str(e)}")
            self.console.print(f"[red]เกิดข้อผิดพลาดในการแสดงการวิเคราะห์: {str(e)}[/red]")
def main():
    parser = argparse.ArgumentParser(description='AltcoinMomentumScanner - เครื่องมือวิเคราะห์โมเมนตัมและจับจังหวะเข้าเทรด Altcoin')
    parser.add_argument('-t', '--timeframe', choices=['1h', '4h', '1d'], default='1h',
                        help='กำหนด timeframe หลักที่ต้องการวิเคราะห์ (default: 1h)')
    parser.add_argument('-ht', '--higher-timeframe', choices=['4h', '1d'], default='4h',
                        help='กำหนด timeframe ที่สูงกว่าสำหรับการวิเคราะห์ Multi-Timeframe (default: 4h)')
    parser.add_argument('-s', '--symbol', type=str, help='ระบุเหรียญที่ต้องการวิเคราะห์เชิงลึก (เช่น BTCUSDT)')
    parser.add_argument('-f', '--filter', choices=['breakout', 'breakdown', 'all'], default='all',
                        help='กรองผลลัพธ์ (breakout, breakdown, all)')
    try:
        scanner = AltcoinMomentumScanner()
        # ปรับค่า higher_timeframe ตามที่ระบุ
        args = parser.parse_args()
        scanner.settings['higher_timeframe'] = args.higher_timeframe
        if args.symbol:
            # ถ้าระบุเหรียญ ให้วิเคราะห์เชิงลึกเฉพาะเหรียญนั้น
            scanner.display_coin_analysis(args.symbol.upper())
        else:
            # สแกนทั้งหมด
            results = scanner.scan_for_momentum(args.timeframe)
            # กรองผลลัพธ์ตามที่ระบุ
            if args.filter == 'breakout' and results:
                breakout_coins = results['STRONG_BREAKOUT'] + results['BREAKOUT']
                breakout_coins.sort(key=lambda x: x['momentum_score'], reverse=True)
                if breakout_coins:
                    terms = scanner.terms
                    table = Table(title=f"เหรียญที่มีสัญญาณ {terms['BREAKOUT']} ({len(breakout_coins)} เหรียญ)")
                    table.add_column("เหรียญ", style="cyan")
                    table.add_column("ราคา", style="yellow")
                    table.add_column("คะแนน", style="green")
                    table.add_column("เปลี่ยนแปลง 24h", style="green")
                    table.add_column("รูปแบบ", style="magenta")
                    for coin in breakout_coins[:15]:
                        change_color = "green" if coin['extra']['price_change_1d'] > 0 else "red"
                        pattern = coin['pattern'][0] if coin['pattern'] else "-"
                        table.add_row(
                            coin['symbol'],
                            f"{coin['price']:.6f}",
                            f"{coin['momentum_score']:.1f}",
                            f"[{change_color}]{coin['extra']['price_change_1d']:+.2f}%[/{change_color}]",
                            pattern
                        )
                    scanner.console.print(table)
            elif args.filter == 'breakdown' and results:
                breakdown_coins = results['STRONG_BREAKDOWN'] + results['BREAKDOWN']
                breakdown_coins.sort(key=lambda x: x['momentum_score'])
                if breakdown_coins:
                    terms = scanner.terms
                    table = Table(title=f"เหรียญที่มีสัญญาณ {terms['BREAKDOWN']} ({len(breakdown_coins)} เหรียญ)")
                    table.add_column("เหรียญ", style="cyan")
                    table.add_column("ราคา", style="yellow")
                    table.add_column("คะแนน", style="red")
                    table.add_column("เปลี่ยนแปลง 24h", style="red")
                    table.add_column("รูปแบบ", style="magenta")
                    for coin in breakdown_coins[:15]:
                        change_color = "green" if coin['extra']['price_change_1d'] > 0 else "red"
                        pattern = coin['pattern'][0] if coin['pattern'] else "-"
                        table.add_row(
                            coin['symbol'],
                            f"{coin['price']:.6f}",
                            f"{coin['momentum_score']:.1f}",
                            f"[{change_color}]{coin['extra']['price_change_1d']:+.2f}%[/{change_color}]",
                            pattern
                        )
                    scanner.console.print(table)
    except KeyboardInterrupt:
        print("\nโปรแกรมถูกหยุดโดยผู้ใช้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {str(e)}")
        logger.error(f"เกิดข้อผิดพลาด: {str(e)}")
        return 1
    return 0
if __name__ == "__main__":
    sys.exit(main())