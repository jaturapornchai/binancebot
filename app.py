#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, sys, pandas as pd, numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console

class GateIORSIScanner:
    def __init__(self):
        try: # โหลด API keys และกำหนดค่าเริ่มต้น
            load_dotenv(override=True); self.api_key = os.getenv('GATEIO_API_KEY') or os.environ.get('GATEIO_API_KEY'); self.secret_key = os.getenv('GATEIO_SECRET_KEY') or os.environ.get('GATEIO_SECRET_KEY')
            if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env หรือ environment variables")
            config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4"); self.client, self.futures_api = ApiClient(config), FuturesApi(ApiClient(config))
            # กำหนดพารามิเตอร์ RSI=14, จำนวนแท่งเทียนย้อนหลัง=20, window size สำหรับหา swing points=5
            self.rsi_period, self.rsi_overbought, self.rsi_oversold, self.lookback_periods, self.swing_window = 14, 70, 30, 20, 5
            # กำหนดพารามิเตอร์สำหรับสัญญาณการเทรด
            self.rsi_recovery_threshold = 5  # ค่า RSI ต้องฟื้นตัวอย่างน้อย 5 จุดจากจุดต่ำสุด/สูงสุด
            self.ma_periods = [5, 20]  # คำนวณค่าเฉลี่ยเคลื่อนที่ 5 และ 20 คาบเพื่อยืนยันเทรนด์
            self.signal_strength_threshold = 7  # ค่าความแข็งแกร่งของสัญญาณขั้นต่ำ (1-10)
            self.console = Console()
        except Exception as e: print(f"เกิดข้อผิดพลาดในการเริ่มต้น: {str(e)}"); sys.exit(1)

    def calculate_rsi(self, prices):
        """คำนวณค่า RSI จากข้อมูลราคา"""
        try:
            # คำนวณการเปลี่ยนแปลงของราคา และแยกเป็น gain/loss
            delta = np.diff(prices); gain, loss = np.where(delta > 0, delta, 0), np.where(delta < 0, -delta, 0)
            # คำนวณค่าเฉลี่ยเคลื่อนที่แบบถ่วงน้ำหนัก (EMA)
            avg_gain = np.concatenate(([np.mean(gain[:self.rsi_period])], np.zeros(len(gain) - self.rsi_period)))
            avg_loss = np.concatenate(([np.mean(loss[:self.rsi_period])], np.zeros(len(loss) - self.rsi_period)))
            # คำนวณ EMA สำหรับทุกราคา
            for i in range(self.rsi_period, len(gain)): avg_gain[i-self.rsi_period+1] = (avg_gain[i-self.rsi_period] * (self.rsi_period-1) + gain[i]) / self.rsi_period; avg_loss[i-self.rsi_period+1] = (avg_loss[i-self.rsi_period] * (self.rsi_period-1) + loss[i]) / self.rsi_period
            # คำนวณ RS และ RSI
            rs = avg_gain / np.where(avg_loss == 0, 0.001, avg_loss)  # ป้องกันการหารด้วยศูนย์
            return np.concatenate((np.full(self.rsi_period, np.nan), 100 - (100 / (1 + rs))))
        except Exception as e: self.console.print(f"[red]เกิดข้อผิดพลาดในการคำนวณ RSI: {str(e)}[/red]"); return np.array([])

    def find_swing_points(self, df):
        """ค้นหาจุด swing high และ swing low ของ RSI และราคา"""
        # เตรียม DataFrame สำหรับเก็บจุด swing
        df['rsi_swing_high'] = False; df['rsi_swing_low'] = False; df['price_swing_high'] = False; df['price_swing_low'] = False
        # ค้นหาจุด swing point
        for i in range(self.swing_window, len(df) - self.swing_window):
            left_window, right_window = df.iloc[i-self.swing_window:i], df.iloc[i+1:i+self.swing_window+1]
            # Swing High/Low ของ RSI
            if all(df.iloc[i]['rsi'] >= left_window['rsi']) and all(df.iloc[i]['rsi'] >= right_window['rsi']): df.loc[df.index[i], 'rsi_swing_high'] = True
            if all(df.iloc[i]['rsi'] <= left_window['rsi']) and all(df.iloc[i]['rsi'] <= right_window['rsi']): df.loc[df.index[i], 'rsi_swing_low'] = True
            # Swing High/Low ของราคา
            if all(df.iloc[i]['close'] >= left_window['close']) and all(df.iloc[i]['close'] >= right_window['close']): df.loc[df.index[i], 'price_swing_high'] = True
            if all(df.iloc[i]['close'] <= left_window['close']) and all(df.iloc[i]['close'] <= right_window['close']): df.loc[df.index[i], 'price_swing_low'] = True
        return df

    def calculate_ma(self, df, periods):
        """คำนวณค่าเฉลี่ยเคลื่อนที่ (Moving Average) สำหรับยืนยันเทรนด์"""
        for period in periods:
            df[f'ma_{period}'] = df['close'].rolling(window=period).mean()
        return df
        
    def find_divergences(self, df):
        """ตรวจหา Divergence โดยใช้จุด Swing High/Low"""
        divergences = {'bearish': [], 'bullish': []}; df = self.find_swing_points(df)
        # คำนวณค่าเฉลี่ยเคลื่อนที่เพื่อยืนยันเทรนด์
        df = self.calculate_ma(df, self.ma_periods)
        
        # ค้นหา bearish divergence (ราคาทำ higher high แต่ RSI ทำ lower high)
        rsi_swing_highs, price_swing_highs = df[df['rsi_swing_high']].sort_index(), df[df['price_swing_high']].sort_index()
        if len(rsi_swing_highs) >= 2 and len(price_swing_highs) >= 2:
            for i in range(1, min(len(rsi_swing_highs), self.lookback_periods)):
                if i >= len(rsi_swing_highs): break
                current_rsi_high, prev_rsi_high = rsi_swing_highs.iloc[-i], rsi_swing_highs.iloc[-(i+1)]
                # หาจุด swing high ของราคาที่ใกล้เคียงกับ rsi swing high
                current_price_idx = df.index.get_indexer([current_rsi_high.name], method='nearest')[0]
                prev_price_idx = df.index.get_indexer([prev_rsi_high.name], method='nearest')[0]
                current_price, prev_price = df.iloc[current_price_idx]['close'], df.iloc[prev_price_idx]['close']
                
                # ตรวจสอบ bearish divergence: ราคาทำ higher high แต่ RSI ทำ lower high
                if current_price > prev_price and current_rsi_high['rsi'] < prev_rsi_high['rsi'] and current_rsi_high['rsi'] > self.rsi_overbought:
                    # คำนวณความแข็งแกร่งของสัญญาณ (1-10)
                    rsi_diff = prev_rsi_high['rsi'] - current_rsi_high['rsi']  # ความต่างของ RSI
                    price_diff_percent = (current_price - prev_price) / prev_price * 100  # เปอร์เซ็นต์การเปลี่ยนแปลงของราคา
                    
                    # ยิ่ง RSI แตกต่างมาก และราคาเปลี่ยนมาก ยิ่งเป็นสัญญาณที่แข็งแกร่ง
                    signal_strength = min(10, (rsi_diff * 0.5 + price_diff_percent * 0.5))
                    
                    # ตรวจสอบการยืนยันเทรนด์จาก MA
                    trend_confirmation = 0
                    if current_price_idx > 0 and 'ma_5' in df.columns and 'ma_20' in df.columns:
                        # ถ้าราคาอยู่เหนือ MA ทั้งสองเส้น และ MA สั้นอยู่เหนือ MA ยาว = แนวโน้มขาขึ้นชัดเจน (ดีสำหรับ short)
                        if (df.iloc[current_price_idx]['close'] > df.iloc[current_price_idx]['ma_5'] > df.iloc[current_price_idx]['ma_20']):
                            trend_confirmation = 3
                        # ถ้าราคาเพิ่งตัด MA ลง = การเปลี่ยนเทรนด์ (ดีสำหรับ short)
                        elif (df.iloc[current_price_idx-1]['close'] > df.iloc[current_price_idx-1]['ma_5'] and 
                              df.iloc[current_price_idx]['close'] < df.iloc[current_price_idx]['ma_5']):
                            trend_confirmation = 2
                    
                    # เพิ่มความแข็งแกร่งตามการยืนยันเทรนด์
                    signal_strength += trend_confirmation
                    
                    divergences['bearish'].append({
                        'timestamp': current_rsi_high.name, 
                        'price': current_price, 
                        'rsi': current_rsi_high['rsi'], 
                        'prev_price': prev_price, 
                        'prev_rsi': prev_rsi_high['rsi'], 
                        'candles_ago': len(df) - 1 - current_price_idx,
                        'signal_strength': min(10, signal_strength),
                        'trend_confirmation': trend_confirmation > 0
                    })
        
        # ค้นหา bullish divergence (ราคาทำ lower low แต่ RSI ทำ higher low)
        rsi_swing_lows, price_swing_lows = df[df['rsi_swing_low']].sort_index(), df[df['price_swing_low']].sort_index()
        if len(rsi_swing_lows) >= 2 and len(price_swing_lows) >= 2:
            for i in range(1, min(len(rsi_swing_lows), self.lookback_periods)):
                if i >= len(rsi_swing_lows): break
                current_rsi_low, prev_rsi_low = rsi_swing_lows.iloc[-i], rsi_swing_lows.iloc[-(i+1)]
                # หาจุด swing low ของราคาที่ใกล้เคียงกับ rsi swing low
                current_price_idx = df.index.get_indexer([current_rsi_low.name], method='nearest')[0]
                prev_price_idx = df.index.get_indexer([prev_rsi_low.name], method='nearest')[0]
                current_price, prev_price = df.iloc[current_price_idx]['close'], df.iloc[prev_price_idx]['close']
                
                # ตรวจสอบ bullish divergence: ราคาทำ lower low แต่ RSI ทำ higher low
                if current_price < prev_price and current_rsi_low['rsi'] > prev_rsi_low['rsi'] and current_rsi_low['rsi'] < self.rsi_oversold:
                    # คำนวณความแข็งแกร่งของสัญญาณ (1-10)
                    rsi_diff = current_rsi_low['rsi'] - prev_rsi_low['rsi']  # ความต่างของ RSI
                    price_diff_percent = (prev_price - current_price) / prev_price * 100  # เปอร์เซ็นต์การเปลี่ยนแปลงของราคา
                    
                    # ยิ่ง RSI แตกต่างมาก และราคาเปลี่ยนมาก ยิ่งเป็นสัญญาณที่แข็งแกร่ง
                    signal_strength = min(10, (rsi_diff * 0.5 + price_diff_percent * 0.5))
                    
                    # ตรวจสอบการยืนยันเทรนด์จาก MA
                    trend_confirmation = 0
                    if current_price_idx > 0 and 'ma_5' in df.columns and 'ma_20' in df.columns:
                        # ถ้าราคาอยู่ต่ำกว่า MA ทั้งสองเส้น และ MA สั้นอยู่ต่ำกว่า MA ยาว = แนวโน้มขาลงชัดเจน (ดีสำหรับ long)
                        if (df.iloc[current_price_idx]['close'] < df.iloc[current_price_idx]['ma_5'] < df.iloc[current_price_idx]['ma_20']):
                            trend_confirmation = 3
                        # ถ้าราคาเพิ่งตัด MA ขึ้น = การเปลี่ยนเทรนด์ (ดีสำหรับ long)
                        elif (df.iloc[current_price_idx-1]['close'] < df.iloc[current_price_idx-1]['ma_5'] and 
                              df.iloc[current_price_idx]['close'] > df.iloc[current_price_idx]['ma_5']):
                            trend_confirmation = 2
                    
                    # เพิ่มความแข็งแกร่งตามการยืนยันเทรนด์
                    signal_strength += trend_confirmation
                    
                    divergences['bullish'].append({
                        'timestamp': current_rsi_low.name, 
                        'price': current_price, 
                        'rsi': current_rsi_low['rsi'], 
                        'prev_price': prev_price, 
                        'prev_rsi': prev_rsi_low['rsi'], 
                        'candles_ago': len(df) - 1 - current_price_idx,
                        'signal_strength': min(10, signal_strength),
                        'trend_confirmation': trend_confirmation > 0
                    })
        
        return divergences
    
    def generate_trading_signals(self, df, divergences):
        """สร้างสัญญาณการเทรด Long/Short จากข้อมูล RSI Divergence"""
        trading_signals = {'long': [], 'short': []}
        
        # ตรวจสอบสัญญาณ Long (จาก Bullish Divergence)
        for div in divergences['bullish']:
            if div['signal_strength'] >= self.signal_strength_threshold:
                # คำนวณ Risk/Reward Ratio
                # สมมติให้ Stop Loss อยู่ต่ำกว่าราคาปัจจุบัน 2%
                stop_loss = div['price'] * 0.98
                # สมมติให้ Take Profit อยู่สูงกว่าราคาปัจจุบัน 6% (RR = 1:3)
                take_profit = div['price'] * 1.06
                
                trading_signals['long'].append({
                    'price': div['price'],
                    'strength': div['signal_strength'],
                    'candles_ago': div['candles_ago'],
                    'rsi': div['rsi'],
                    'trend_confirmed': div['trend_confirmation'],
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_reward': 3
                })
        
        # ตรวจสอบสัญญาณ Short (จาก Bearish Divergence)
        for div in divergences['bearish']:
            if div['signal_strength'] >= self.signal_strength_threshold:
                # คำนวณ Risk/Reward Ratio
                # สมมติให้ Stop Loss อยู่สูงกว่าราคาปัจจุบัน 2%
                stop_loss = div['price'] * 1.02
                # สมมติให้ Take Profit อยู่ต่ำกว่าราคาปัจจุบัน 6% (RR = 1:3)
                take_profit = div['price'] * 0.94
                
                trading_signals['short'].append({
                    'price': div['price'],
                    'strength': div['signal_strength'],
                    'candles_ago': div['candles_ago'],
                    'rsi': div['rsi'],
                    'trend_confirmed': div['trend_confirmation'],
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_reward': 3
                })
        
        return trading_signals

    def scan_market(self):
        """สแกนตลาดเพื่อหาสัญญาณ RSI divergence และสร้างสัญญาณซื้อขาย"""
        stats = {'contracts_scanned': 0, 'divergence_signals': 0, 'long_signals': 0, 'short_signals': 0}
        trading_opportunities = {'long': [], 'short': []}
        
        try:
            # แสดงเวลาปัจจุบันและเริ่มสแกน
            current_time = pd.Timestamp.now(tz='Asia/Bangkok')
            self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')} (ตรวจสอบย้อนหลัง {self.lookback_periods} แท่ง)[/blue]")
            self.console.print(f"[blue]===========================================[/blue]")
            # ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ
            ticket = self.futures_api.list_futures_tickers(settle='usdt')
            contracts = [c.contract for c in ticket if re.match(r'^\D+_USDT$', c.contract) and c.contract not in ['USDC_USDT', 'DOGS_USDT'] and float(c.volume_24h) * float(c.last) > 5000000]
            self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(contracts)} สัญญา[/blue]")
            # สแกนแต่ละสัญญา
            for i, contract in enumerate(contracts, 1):
                try:
                    # ดึงข้อมูลแท่งเทียนและแปลงเป็น DataFrame
                    candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='1h', limit=300)
                    if not candles: self.console.print(f"[red]❌ {contract}: ไม่พบข้อมูลแท่งเทียน[/red]"); continue
                    data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
                    df = pd.DataFrame(data); df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s'); df = df.sort_values('timestamp')
                    # คำนวณค่า RSI และตรวจหา divergence
                    if len(df) > (self.rsi_period + self.swing_window * 2):
                        df['rsi'] = self.calculate_rsi(df['close'].values); latest_candle = df.iloc[-1]
                        candle_type = "สีเขียว 🟩" if latest_candle['close'] > latest_candle['open'] else "สีแดง 🟥" if latest_candle['close'] < latest_candle['open'] else "Doji ⬛"
                        
                        # ตรวจหา divergence โดยใช้จุด swing high/low
                        divergences = self.find_divergences(df)
                        
                        # สร้างสัญญาณการเทรด Long/Short
                        trading_signals = self.generate_trading_signals(df, divergences)
                        
                        # เตรียมข้อความการแสดงผล
                        output_msg = f"[cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract}[/cyan] - [magenta]{candle_type} (O: {latest_candle['open']:.6f}, H: {latest_candle['high']:.6f}, L: {latest_candle['low']:.6f}, C: {latest_candle['close']:.6f}, RSI: {latest_candle['rsi']:.2f})[/magenta]"
                        
                        # สร้างข้อความแสดงสถานะ RSI
                        rsi_status = ""
                        if latest_candle['rsi'] > self.rsi_overbought: rsi_status += f" [red bold]⚠️ RSI Overbought: {latest_candle['rsi']:.2f} > {self.rsi_overbought}[/red bold]"
                        if latest_candle['rsi'] < self.rsi_oversold: rsi_status += f" [green bold]⚠️ RSI Oversold: {latest_candle['rsi']:.2f} < {self.rsi_oversold}[/green bold]"
                        
                        # ตรวจสอบ divergence
                        divergence_found = False
                        
                        # แสดงผล Bearish Divergence และสัญญาณ Short
                        if divergences['bearish']:
                            for div in divergences['bearish']: 
                                output_msg += f" - [red bold]❗️🚨🔻 BEARISH DIVERGENCE ({div['candles_ago']} แท่งก่อน): ราคา {div['price']:.6f} > {div['prev_price']:.6f}, RSI {div['rsi']:.2f} < {div['prev_rsi']:.2f} (ความแข็งแกร่ง: {div['signal_strength']:.1f}/10) 🔻🚨❗️[/red bold]"
                                divergence_found = True
                            stats['divergence_signals'] += len(divergences['bearish'])
                        
                        # แสดงผล Bullish Divergence และสัญญาณ Long
                        if divergences['bullish']:
                            for div in divergences['bullish']: 
                                output_msg += f" - [green bold]❗️🚨🔼 BULLISH DIVERGENCE ({div['candles_ago']} แท่งก่อน): ราคา {div['price']:.6f} < {div['prev_price']:.6f}, RSI {div['rsi']:.2f} > {div['prev_rsi']:.2f} (ความแข็งแกร่ง: {div['signal_strength']:.1f}/10) 🔼🚨❗️[/green bold]"
                                divergence_found = True
                            stats['divergence_signals'] += len(divergences['bullish'])
                        
                        # แสดงสัญญาณการเทรด
                        if trading_signals['long']:
                            for signal in trading_signals['long']:
                                output_msg += f"\n[green bold]🔔 สัญญาณ LONG: ราคา {signal['price']:.6f} | ความแข็งแกร่ง: {signal['strength']:.1f}/10 | RSI: {signal['rsi']:.2f} | RR: 1:{signal['risk_reward']} 🔔[/green bold]"
                                output_msg += f"\n[green]   👉 แนะนำ: เปิด LONG ที่ {signal['price']:.6f} | Stop Loss: {signal['stop_loss']:.6f} | Take Profit: {signal['take_profit']:.6f}[/green]"
                                stats['long_signals'] += 1
                                # เก็บโอกาสการเทรดเพื่อสรุปในภายหลัง
                                trading_opportunities['long'].append({'contract': contract, 'price': signal['price'], 'strength': signal['strength']})
                        
                        if trading_signals['short']:
                            for signal in trading_signals['short']:
                                output_msg += f"\n[red bold]🔔 สัญญาณ SHORT: ราคา {signal['price']:.6f} | ความแข็งแกร่ง: {signal['strength']:.1f}/10 | RSI: {signal['rsi']:.2f} | RR: 1:{signal['risk_reward']} 🔔[/red bold]"
                                output_msg += f"\n[red]   👉 แนะนำ: เปิด SHORT ที่ {signal['price']:.6f} | Stop Loss: {signal['stop_loss']:.6f} | Take Profit: {signal['take_profit']:.6f}[/red]"
                                stats['short_signals'] += 1
                                # เก็บโอกาสการเทรดเพื่อสรุปในภายหลัง
                                trading_opportunities['short'].append({'contract': contract, 'price': signal['price'], 'strength': signal['strength']})
                        
                        # เพิ่มสถานะ RSI และแสดงข้อความไม่พบสัญญาณถ้าไม่มี divergence
                        if rsi_status: output_msg += rsi_status
                        if not divergence_found: output_msg += " - [blue]ไม่พบสัญญาณ RSI Divergence[/blue]"
                        
                        # แสดงผลทั้งหมด (เฉพาะเมื่อมีสัญญาณ)
                        if divergence_found or trading_signals['long'] or trading_signals['short']:
                            self.console.print(output_msg)
                        else:
                            # แสดงเฉพาะการสแกนแบบสั้นๆ ถ้าไม่พบสัญญาณ
                            self.console.print(f"[dim cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract} - ไม่พบสัญญาณ[/dim cyan]")
                    else: 
                        self.console.print(f"[dim red]❌ {contract}: ข้อมูลไม่เพียงพอสำหรับการคำนวณ RSI และ Swing points[/dim red]")
                except Exception as e: 
                    self.console.print(f"[red]❌ {contract}: เกิดข้อผิดพลาด: {str(e)}[/red]")
                    continue
                stats['contracts_scanned'] += 1
            
            # แสดงสรุปการสแกน
            self.console.print(f"[blue]===== สรุปการสแกน =====[/blue]")
            self.console.print(f"[blue]📊 สัญญาที่สแกน: {stats['contracts_scanned']}/{len(contracts)}[/blue]")
            
            # สรุปสัญญาณที่พบ
            if stats['divergence_signals'] > 0:
                self.console.print(f"[bold]🚨 พบสัญญาณ RSI DIVERGENCE: {stats['divergence_signals']} สัญญาณ (ตรวจสอบย้อนหลัง {self.lookback_periods} แท่ง) 🚨[/bold]")
            else:
                self.console.print(f"[green]✅ ไม่พบสัญญาณ RSI Divergence (ตรวจสอบย้อนหลัง {self.lookback_periods} แท่ง)[/green]")
            
            # สรุปสัญญาณการเทรด
            if stats['long_signals'] > 0:
                self.console.print(f"[green bold]🔔 พบสัญญาณ LONG: {stats['long_signals']} สัญญาณ[/green bold]")
                self.console.print("[green]โอกาสการเทรด LONG ที่น่าสนใจ:[/green]")
                # เรียงลำดับตามความแข็งแกร่งของสัญญาณ
                for i, opportunity in enumerate(sorted(trading_opportunities['long'], key=lambda x: x['strength'], reverse=True)[:5]):
                    self.console.print(f"[green]{i+1}. {opportunity['contract']} ที่ราคา {opportunity['price']:.6f} (ความแข็งแกร่ง: {opportunity['strength']:.1f}/10)[/green]")
            
            if stats['short_signals'] > 0:
                self.console.print(f"[red bold]🔔 พบสัญญาณ SHORT: {stats['short_signals']} สัญญาณ[/red bold]")
                self.console.print("[red]โอกาสการเทรด SHORT ที่น่าสนใจ:[/red]")
                # เรียงลำดับตามความแข็งแกร่งของสัญญาณ
                for i, opportunity in enumerate(sorted(trading_opportunities['short'], key=lambda x: x['strength'], reverse=True)[:5]):
                    self.console.print(f"[red]{i+1}. {opportunity['contract']} ที่ราคา {opportunity['price']:.6f} (ความแข็งแกร่ง: {opportunity['strength']:.1f}/10)[/red]")
            
            self.console.print(f"[blue]===========================================[/blue]")
        except KeyboardInterrupt: 
            self.console.print("[yellow]โปรแกรมถูกหยุดโดยผู้ใช้[/yellow]")
        except Exception as e: 
            self.console.print(f"[red]❌ เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}[/red]")

# เริ่มการทำงานของโปรแกรม
if __name__ == "__main__":
    try: scanner = GateIORSIScanner(); scanner.console.print("[blue]เริ่มต้นระบบสแกน RSI Divergence...[/blue]"); scanner.scan_market()
    except KeyboardInterrupt: print("\nโปรแกรมถูกหยุดโดยผู้ใช้")
    except Exception as e: print(f"เกิดข้อผิดพลาดร้ายแรง: {str(e)}"); sys.exit(1)