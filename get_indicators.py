#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import json
import logging

class TechnicalIndicators:
    def __init__(self):
        self.logger = logging.getLogger("AltcoinMomentumScanner")
        
    def calculate_all_indicators(self, df, settings):
        """คำนวณตัวชี้วัดทางเทคนิคทั้งหมดสำหรับ DataFrame"""
        try:
            # คำนวณข้อมูลพื้นฐานของแท่งเทียน
            df['body'] = abs(df['close'] - df['open'])
            df['range'] = df['high'] - df['low']
            df['body_pct'] = (df['body'] / df['range'].replace(0, np.nan)) * 100
            df['bullish'] = df['close'] > df['open']
            df['upper_wick'] = np.where(df['bullish'], df['high'] - df['close'], df['high'] - df['open'])
            df['lower_wick'] = np.where(df['bullish'], df['open'] - df['low'], df['close'] - df['low'])
            
            # คำนวณการเปลี่ยนแปลงของราคา
            for period in [1, 3, 5, 7, 14]:
                if len(df) > period: 
                    df[f'change_{period}d'] = (df['close'] / df['close'].shift(period) - 1) * 100
            
            # คำนวณค่าเฉลี่ยเคลื่อนที่ของปริมาณซื้อขาย
            vol_ma = settings['volume_ma_period']
            df['volume_ma'] = df['volume'].rolling(window=vol_ma).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']
            
            # คำนวณ Z-score ของปริมาณซื้อขาย
            vol_mean = df['volume'].rolling(window=30).mean()
            vol_std = df['volume'].rolling(window=30).std()
            df['volume_zscore'] = (df['volume'] - vol_mean) / vol_std.replace(0, 1)
            
            # คำนวณ On-Balance Volume (OBV)
            df['obv'] = np.nan
            df.loc[0, 'obv'] = df.loc[0, 'volume']
            for i in range(1, len(df)):
                if df.loc[i, 'close'] > df.loc[i-1, 'close']: 
                    df.loc[i, 'obv'] = df.loc[i-1, 'obv'] + df.loc[i, 'volume']
                elif df.loc[i, 'close'] < df.loc[i-1, 'close']: 
                    df.loc[i, 'obv'] = df.loc[i-1, 'obv'] - df.loc[i, 'volume']
                else: 
                    df.loc[i, 'obv'] = df.loc[i-1, 'obv']
            
            # คำนวณ Average True Range (ATR)
            df['tr'] = np.maximum.reduce([
                df['high'] - df['low'], 
                abs(df['high'] - df['close'].shift(1)), 
                abs(df['low'] - df['close'].shift(1))
            ])
            df['atr'] = df['tr'].rolling(window=settings['atr_period']).mean()
            df['atr_pct'] = (df['atr'] / df['close']) * 100
            
            # คำนวณ Bollinger Bands
            bb_period, bb_std = settings['bb_period'], settings['bb_std']
            df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
            df['bb_std'] = df['close'].rolling(window=bb_period).std()
            df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * bb_std)
            df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * bb_std)
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
            df['bb_percent_b'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
            
            # คำนวณ Relative Strength Index (RSI)
            rsi_period = settings['rsi_period']
            delta = df['close'].diff()
            gain, loss = delta.where(delta > 0, 0), -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(window=rsi_period).mean()
            avg_loss = loss.rolling(window=rsi_period).mean()
            rs = avg_gain / avg_loss.replace(0, 1e-9)
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # คำนวณ Moving Average Convergence Divergence (MACD)
            fast, slow, signal = settings['macd_fast'], settings['macd_slow'], settings['macd_signal']
            df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
            df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
            df['macd'] = df['ema_fast'] - df['ema_slow']
            df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']
            df['macd_hist_change'] = df['macd_hist'].diff()
            
            # คำนวณ Stochastic Oscillator
            stoch_period = 14
            if len(df) >= stoch_period:
                df['stoch_k'] = 100 * (
                    (df['close'] - df['low'].rolling(window=stoch_period).min()) / 
                    (df['high'].rolling(window=stoch_period).max() - df['low'].rolling(window=stoch_period).min())
                )
                df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
                
                # คำนวณ Stochastic RSI
                rsi_min = df['rsi'].rolling(window=stoch_period).min()
                rsi_max = df['rsi'].rolling(window=stoch_period).max()
                df['stoch_rsi'] = 100 * ((df['rsi'] - rsi_min) / (rsi_max - rsi_min).replace(0, 1e-9))
                df['stoch_rsi_d'] = df['stoch_rsi'].rolling(window=3).mean()
            
            # ระบุแนวรับแนวต้าน
            self.identify_support_resistance(df)
            
            # ระบุ Volatility Squeeze
            bb_avg = df['bb_width'].rolling(window=20).mean()
            df['squeeze_on'] = df['bb_width'] < bb_avg * 0.8
            df['squeeze_fire'] = (df['squeeze_on'].shift(1) == True) & (df['squeeze_on'] == False) & (abs(df['change_1d']) > 2)
            
            # ระบุการกลับตัวของแนวโน้ม
            df['trend_reversal'] = False
            bullish_reversal = (
                (df['rsi'].shift(1) < 30) & 
                (df['rsi'] > 30) & 
                (df['macd_hist'].shift(1) < 0) & 
                (df['macd_hist'] > 0) & 
                (df['close'] > df['open'])
            )
            bearish_reversal = (
                (df['rsi'].shift(1) > 70) & 
                (df['rsi'] < 70) & 
                (df['macd_hist'].shift(1) > 0) & 
                (df['macd_hist'] < 0) & 
                (df['close'] < df['open'])
            )
            df.loc[bullish_reversal | bearish_reversal, 'trend_reversal'] = True
            
            # ระบุแนวโน้มขาขึ้น/ขาลง
            df['uptrend'] = False
            df['downtrend'] = False
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
            df['uptrend'] = (df['close'] > df['ema50']) & (df['ema50'] > df['ema200'])
            df['downtrend'] = (df['close'] < df['ema50']) & (df['ema50'] < df['ema200'])
            
        except Exception as e: 
            self.logger.error(f"เกิดข้อผิดพลาดในการคำนวณตัวชี้วัด: {str(e)}")
    
    def identify_support_resistance(self, df):
        """ระบุระดับแนวรับแนวต้านในกราฟราคา"""
        try:
            df['swing_high'] = df['swing_low'] = False
            if len(df) < 5: return
            
            # ระบุจุด Swing High และ Swing Low
            for i in range(2, len(df) - 2):
                # จุด Swing High
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                    df['high'].iloc[i] > df['high'].iloc[i-2] and 
                    df['high'].iloc[i] > df['high'].iloc[i+1] and 
                    df['high'].iloc[i] > df['high'].iloc[i+2]):
                    df.iloc[i, df.columns.get_loc('swing_high')] = True
                
                # จุด Swing Low
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                    df['low'].iloc[i] < df['low'].iloc[i-2] and 
                    df['low'].iloc[i] < df['low'].iloc[i+1] and 
                    df['low'].iloc[i] < df['low'].iloc[i+2]):
                    df.iloc[i, df.columns.get_loc('swing_low')] = True
            
            # หาจุดแนวรับแนวต้านจากข้อมูลล่าสุด
            recent_df = df.iloc[-30:].copy() if len(df) >= 30 else df.copy()
            resistance_points = recent_df.loc[recent_df['swing_high'], 'high'].tolist()
            recent_high = df['high'].iloc[-15:].max() if len(df) >= 15 else df['high'].max()
            support_points = recent_df.loc[recent_df['swing_low'], 'low'].tolist()
            recent_low = df['low'].iloc[-15:].min() if len(df) >= 15 else df['low'].min()
            
            resistance_points.append(recent_high)
            support_points.append(recent_low)
            
            current_price = df['close'].iloc[-1]
            
            # หาระดับแนวต้านที่ใกล้ที่สุด
            resistance_above = [r for r in resistance_points if r > current_price]
            nearest_resistance = min(resistance_above) if resistance_above else None
            
            # หาระดับแนวรับที่ใกล้ที่สุด
            support_below = [s for s in support_points if s < current_price]
            nearest_support = max(support_below) if support_below else None
            
            # คำนวณระยะห่างจากราคาปัจจุบันถึงแนวรับแนวต้าน
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
            
            # ตรวจสอบระดับ Fibonacci ด้วย
            fibo_resistance = df['nearest_fibo_resistance_price'].iloc[-1] if 'nearest_fibo_resistance_price' in df.columns and pd.notna(df['nearest_fibo_resistance_price'].iloc[-1]) else None
            fibo_support = df['nearest_fibo_support_price'].iloc[-1] if 'nearest_fibo_support_price' in df.columns and pd.notna(df['nearest_fibo_support_price'].iloc[-1]) else None
            
            # ใช้ระดับ Fibonacci หากอยู่ใกล้กว่า
            if fibo_resistance and (nearest_resistance is None or abs(fibo_resistance - current_price) < abs(nearest_resistance - current_price)):
                df['nearest_resistance'] = fibo_resistance
                df['distance_to_resistance'] = ((fibo_resistance - current_price) / current_price) * 100
            
            if fibo_support and (nearest_support is None or abs(fibo_support - current_price) < abs(nearest_support - current_price)):
                df['nearest_support'] = fibo_support
                df['distance_to_support'] = ((current_price - fibo_support) / current_price) * 100
                
        except Exception as e: 
            self.logger.error(f"เกิดข้อผิดพลาดในการระบุแนวรับแนวต้าน: {str(e)}")
    
    def identify_chart_patterns(self, df, settings):
        """ระบุรูปแบบกราฟทางเทคนิค"""
        try:
            # หาค่าสูงสุดและต่ำสุดใน 20 วัน
            df['hh20'] = df['high'].rolling(20).max()  
            df['ll20'] = df['low'].rolling(20).min()   
            
            # ระบุการ Breakout/Breakdown
            volume_surge = df['volume'] > df['volume_ma'] * settings['volume_surge_threshold']
            df['breakout_up'] = (df['close'] > df['hh20'].shift(1)) & volume_surge
            df['breakout_down'] = (df['close'] < df['ll20'].shift(1)) & volume_surge
            
            # เตรียมตัวแปรสำหรับรูปแบบกราฟ
            df['bull_flag'] = df['bear_flag'] = df['ascending_triangle'] = df['descending_triangle'] = False
            df['symmetrical_triangle'] = df['falling_wedge'] = df['rising_wedge'] = False
            df['head_and_shoulders'] = df['inv_head_and_shoulders'] = df['double_top'] = df['double_bottom'] = False
            df['hammer'] = df['shooting_star'] = df['bullish_engulfing'] = df['bearish_engulfing'] = False
            
            # ระบุรูปแบบ Bull Flag
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
            
            # ระบุรูปแบบสามเหลี่ยมและลิ่ม
            if len(df) >= 20:
                last_20 = df.iloc[-20:].copy()
                high_std = last_20['high'].std() / last_20['high'].mean()
                
                if high_std < 0.01:
                    low_trend = np.polyfit(range(len(last_20)), last_20['low'], 1)[0]
                    if low_trend > 0: df.iloc[-1, df.columns.get_loc('ascending_triangle')] = True
                
                low_std = last_20['low'].std() / last_20['low'].mean()
                if low_std < 0.01:
                    high_trend = np.polyfit(range(len(last_20)), last_20['high'], 1)[0]
                    if high_trend < 0: df.iloc[-1, df.columns.get_loc('descending_triangle')] = True
                
                high_trend = np.polyfit(range(len(last_20)), last_20['high'], 1)[0]
                low_trend = np.polyfit(range(len(last_20)), last_20['low'], 1)[0]
                
                if high_trend < 0 and low_trend < 0 and high_trend < low_trend: 
                    df.iloc[-1, df.columns.get_loc('falling_wedge')] = True
                if high_trend > 0 and low_trend > 0 and high_trend > low_trend: 
                    df.iloc[-1, df.columns.get_loc('rising_wedge')] = True
            
            # ระบุรูปแบบ Head and Shoulders และ Inverse Head and Shoulders
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
                    self.logger.error(f"เกิดข้อผิดพลาดในการระบุรูปแบบ Head and Shoulders: {str(e)}")
            
            # ระบุรูปแบบ Double Top/Bottom
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
                    self.logger.error(f"เกิดข้อผิดพลาดในการระบุรูปแบบ Double Top/Bottom: {str(e)}")
            
            # ระบุรูปแบบแท่งเทียน
            for i in range(1, len(df)):
                # Hammer
                if (df['lower_wick'].iloc[i] > 2 * df['body'].iloc[i] and 
                    df['upper_wick'].iloc[i] < df['body'].iloc[i] and 
                    df['body'].iloc[i] > 0):
                    df.iloc[i, df.columns.get_loc('hammer')] = True
                
                # Shooting Star
                if (df['upper_wick'].iloc[i] > 2 * df['body'].iloc[i] and 
                    df['lower_wick'].iloc[i] < df['body'].iloc[i] and 
                    df['body'].iloc[i] > 0):
                    df.iloc[i, df.columns.get_loc('shooting_star')] = True
                
                # Bullish Engulfing
                if (df['bullish'].iloc[i] and not df['bullish'].iloc[i-1] and 
                    df['open'].iloc[i] < df['close'].iloc[i-1] and 
                    df['close'].iloc[i] > df['open'].iloc[i-1]):
                    df.iloc[i, df.columns.get_loc('bullish_engulfing')] = True
                
                # Bearish Engulfing
                if (not df['bullish'].iloc[i] and df['bullish'].iloc[i-1] and 
                    df['open'].iloc[i] > df['close'].iloc[i-1] and 
                    df['close'].iloc[i] < df['open'].iloc[i-1]):
                    df.iloc[i, df.columns.get_loc('bearish_engulfing')] = True
                    
        except Exception as e: 
            self.logger.error(f"เกิดข้อผิดพลาดในการระบุรูปแบบกราฟ: {str(e)}")
    
    def calculate_fibonacci_levels(self, df, settings):
        """คำนวณระดับ Fibonacci Retracement และ Extension"""
        try:
            if len(df) < settings['fibo_period']: return
            
            period = min(settings['fibo_period'], len(df))
            recent_df = df.iloc[-period:]
            
            # หาจุดสูงสุดและต่ำสุดสำหรับการคำนวณ Fibonacci
            price_max = recent_df['high'].max()
            price_min = recent_df['low'].min()
            price_range = price_max - price_min
            
            # ตรวจสอบทิศทางของราคา
            trend_direction = 'up' if df['close'].iloc[-1] >= df['close'].iloc[-5:-1].mean() else 'down'
            
            fibo_levels = {}
            retracement_levels = {}
            extension_levels = {}
            
            # คำนวณระดับ Fibonacci ตามทิศทางราคา
            if trend_direction == 'up':
                for level in settings['fibo_levels']:
                    if level <= 1:
                        # Retracement (ถอยกลับ)
                        retracement_levels[level] = price_max - (price_range * level)
                    else:
                        # Extension (ขยายต่อ)
                        extension_levels[level] = price_max + (price_range * (level - 1))
            else:
                for level in settings['fibo_levels']:
                    if level <= 1:
                        # Retracement (ถอยกลับ)
                        retracement_levels[level] = price_min + (price_range * level)
                    else:
                        # Extension (ขยายต่อ)
                        extension_levels[level] = price_min - (price_range * (level - 1))
            
            fibo_levels['retracement'] = retracement_levels
            fibo_levels['extension'] = extension_levels
            fibo_levels['direction'] = trend_direction
            fibo_levels['swing_high'] = price_max
            fibo_levels['swing_low'] = price_min
            
            # หาระดับ Fibonacci ที่ใกล้ที่สุดกับราคาปัจจุบัน
            current_price = df['close'].iloc[-1]
            fibo_support_levels = []
            fibo_resistance_levels = []
            
            if trend_direction == 'up':
                for level, price in retracement_levels.items():
                    if price < current_price:
                        fibo_support_levels.append((level, price))
                    else:
                        fibo_resistance_levels.append((level, price))
                for level, price in extension_levels.items():
                    fibo_resistance_levels.append((level, price))
            else:
                for level, price in retracement_levels.items():
                    if price > current_price:
                        fibo_resistance_levels.append((level, price))
                    else:
                        fibo_support_levels.append((level, price))
                for level, price in extension_levels.items():
                    fibo_support_levels.append((level, price))
            
            # เรียงลำดับตามระยะห่างจากราคาปัจจุบัน
            fibo_support_levels.sort(key=lambda x: abs(x[1] - current_price))
            fibo_resistance_levels.sort(key=lambda x: abs(x[1] - current_price))
            
            nearest_fibo_support = fibo_support_levels[0] if fibo_support_levels else None
            nearest_fibo_resistance = fibo_resistance_levels[0] if fibo_resistance_levels else None
            
            # เก็บข้อมูลไว้ใน DataFrame
            df['fibo_levels'] = json.dumps(fibo_levels)
            df['fibo_direction'] = trend_direction
            df['fibo_swing_high'] = price_max
            df['fibo_swing_low'] = price_min
            
            if nearest_fibo_support:
                df['nearest_fibo_support_level'] = nearest_fibo_support[0]
                df['nearest_fibo_support_price'] = nearest_fibo_support[1]
                df['nearest_fibo_support_distance'] = ((current_price - nearest_fibo_support[1]) / current_price) * 100
            else:
                df['nearest_fibo_support_level'] = None
                df['nearest_fibo_support_price'] = None
                df['nearest_fibo_support_distance'] = None
            
            if nearest_fibo_resistance:
                df['nearest_fibo_resistance_level'] = nearest_fibo_resistance[0]
                df['nearest_fibo_resistance_price'] = nearest_fibo_resistance[1]
                df['nearest_fibo_resistance_distance'] = ((nearest_fibo_resistance[1] - current_price) / current_price) * 100
            else:
                df['nearest_fibo_resistance_level'] = None
                df['nearest_fibo_resistance_price'] = None
                df['nearest_fibo_resistance_distance'] = None
            
            # เก็บข้อมูลค่าตัวเลขในรูปแบบ JSON
            df['fibo_retracement_levels'] = json.dumps(retracement_levels)
            df['fibo_extension_levels'] = json.dumps(extension_levels)
            
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการคำนวณระดับ Fibonacci: {str(e)}")