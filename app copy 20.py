#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, time, re, sys
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console


class GateIOEMATrader:
    def __init__(self):
        try:
            # ปรับการโหลด environment variables ให้ทำงานได้ดีกับ Docker
            load_dotenv(override=True)
            self.api_key = os.getenv('GATEIO_API_KEY')
            self.secret_key = os.getenv('GATEIO_SECRET_KEY')
           
            # เพิ่มทางเลือกให้รับ API keys จาก environment variables โดยตรง
            if not self.api_key:
                self.api_key = os.environ.get('GATEIO_API_KEY')
            if not self.secret_key:
                self.secret_key = os.environ.get('GATEIO_SECRET_KEY')
               
            if not self.api_key or not self.secret_key:
                raise ValueError("API keys ไม่พบในไฟล์ .env หรือ environment variables")
               
            config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
            self.client, self.futures_api = ApiClient(config), FuturesApi(ApiClient(config))
            self.leverage, self.order_amount = 5, 50
           
            # กำหนดพารามิเตอร์สำหรับ EMA ใหม่ (E1=EMA5, E2=EMA10, E3=EMA30)
            self.ema_short = 5   # E1
            self.ema_mid = 10    # E2
            self.ema_long = 30   # E3
           
            # กำหนดพารามิเตอร์สำหรับ RSI
            self.rsi_period = 14
           
            # กำหนดพารามิเตอร์สำหรับ trend และ stop loss
            self.btc_trend_periods = 7  # จำนวน timeframe สำหรับ BTC trend (7 timeframe)
            self.trend_periods = 14  # จำนวน timeframe สำหรับเหรียญอื่น (14 timeframe)
            self.stop_lookback = 7  # จำนวน timeframes สำหรับหา stop loss
           
            # เงื่อนไขเฉพาะของแต่ละสกุลเงิน
            self.btc_trend = None  # 'UP', 'DOWN', หรือ None
           
            self.console = Console()
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการเริ่มต้น: {str(e)}")
            sys.exit(1)


    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ"""
        try:
            ticket = self.futures_api.list_futures_tickers(settle='usdt')
            valid_contracts = [c.contract for c in ticket if re.match(r'^\D+_USDT$', c.contract) and c.contract not in ['USDC_USDT', 'DOGS_USDT'] and float(c.volume_24h) * float(c.last) > 100000]
            self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา[/blue]")
            return valid_contracts
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงรายชื่อสัญญา: {str(e)}[/red]")
            return []


    def calculate_rsi(self, data, period=14):
        """คำนวณ RSI (Relative Strength Index)"""
        delta = data.diff().dropna()
        gain = delta.copy()
        loss = delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        loss = abs(loss)
       
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
       
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi


    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนจาก API โดยใช้ timeframe 1 ชั่วโมง และคำนวณ EMA และ RSI"""
        try:
            # ใช้ timeframe 1 ชั่วโมง
            candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='1h', limit=500)
            if not candles: return pd.DataFrame()
            data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            df = df.sort_values('timestamp')
           
            # คำนวณ EMA (E1=EMA5, E2=EMA10, E3=EMA30)
            df[f'E1'] = df['close'].ewm(span=self.ema_short, adjust=False).mean()
            df[f'E2'] = df['close'].ewm(span=self.ema_mid, adjust=False).mean()
            df[f'E3'] = df['close'].ewm(span=self.ema_long, adjust=False).mean()
           
            # คำนวณ RSI
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
           
            # คำนวณข้อมูลเพิ่มเติม
            df['candle_color'] = np.where(df['close'] > df['open'], 'green', np.where(df['close'] < df['open'], 'red', 'doji'))
           
            return df
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงข้อมูลแท่งเทียน {contract}: {str(e)}[/red]")
            return pd.DataFrame()


    def check_btc_trend(self) -> str:
        """ตรวจสอบเทรนด์ของ BTC_USDT โดยใช้ 7 time frame"""
        try:
            df = self.get_candlesticks('BTC_USDT')
            if df.empty: return None
           
            # ตรวจสอบข้อมูลว่ามีเพียงพอหรือไม่
            if len(df) < self.btc_trend_periods + 1:
                self.console.print(f"[yellow]⚠️ ข้อมูล BTC_USDT ไม่เพียงพอสำหรับการวิเคราะห์เทรนด์ ({len(df)} < {self.btc_trend_periods + 1})[/yellow]")
                return None
           
            # ตรวจสอบ BTCUPTREND: E1 สูงกว่า E2 และ E2 สูงกว่า E3 ต่อเนื่อง 7 timeframe
            uptrend_count = 0
            for i in range(-self.btc_trend_periods, 0):
                if (df.iloc[i]['E1'] > df.iloc[i]['E2'] and
                    df.iloc[i]['E2'] > df.iloc[i]['E3']):
                    uptrend_count += 1
           
            # ตรวจสอบ BTCDOWNTREND: E1 ต่ำกว่า E2 และ E2 ต่ำกว่า E3 ต่อเนื่อง 7 timeframe
            downtrend_count = 0
            for i in range(-self.btc_trend_periods, 0):
                if (df.iloc[i]['E1'] < df.iloc[i]['E2'] and
                    df.iloc[i]['E2'] < df.iloc[i]['E3']):
                    downtrend_count += 1
           
            if uptrend_count == self.btc_trend_periods:
                self.console.print(f"[green]✅ BTC อยู่ในเทรนด์ขาขึ้น (E1 > E2 > E3 ต่อเนื่อง {uptrend_count} ชั่วโมง)[/green]")
                return "UP"
            elif downtrend_count == self.btc_trend_periods:
                self.console.print(f"[red]✅ BTC อยู่ในเทรนด์ขาลง (E1 < E2 < E3 ต่อเนื่อง {downtrend_count} ชั่วโมง)[/red]")
                return "DOWN"
            else:
                self.console.print(f"[yellow]⚠️ BTC ไม่อยู่ในเทรนด์ที่ชัดเจน (UP: {uptrend_count}/{self.btc_trend_periods}, DOWN: {downtrend_count}/{self.btc_trend_periods})[/yellow]")
                return None
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการตรวจสอบเทรนด์ BTC: {str(e)}[/red]")
            return None


    def calculate_trend_signal(self, df: pd.DataFrame) -> dict:
        """คำนวณสัญญาณเทรดตามเงื่อนไข EMA และ RSI ใหม่"""
        try:
            # ตรวจสอบว่ามีข้อมูลเพียงพอหรือไม่
            if len(df) < self.trend_periods + 1:
                return {'is_uptrend': False, 'is_downtrend': False}
           
            # ตรวจสอบ UPTREND: E1 สูงกว่า E2 และ E2 สูงกว่า E3 ต่อเนื่อง 14 timeframe
            uptrend_count = 0
            for i in range(-self.trend_periods, 0):
                if (df.iloc[i]['E1'] > df.iloc[i]['E2'] and
                    df.iloc[i]['E2'] > df.iloc[i]['E3']):
                    uptrend_count += 1
           
            # ตรวจสอบ DOWNTREND: E1 ต่ำกว่า E2 และ E2 ต่ำกว่า E3 ต่อเนื่อง 14 timeframe
            downtrend_count = 0
            for i in range(-self.trend_periods, 0):
                if (df.iloc[i]['E1'] < df.iloc[i]['E2'] and
                    df.iloc[i]['E2'] < df.iloc[i]['E3']):
                    downtrend_count += 1
           
            # คำนวณ STOPLONG, STOPSHORT
            if len(df) >= self.stop_lookback + 1:
                stop_period = df.iloc[-self.stop_lookback-1:-1]  # ไม่รวม timeframe ปัจจุบัน
                stoplong = stop_period['low'].min()
                stopshort = stop_period['high'].max()
            else:
                stoplong = df['low'].min()
                stopshort = df['high'].max()
           
            # ดึงข้อมูล CANDLE ล่าสุด
            latest_candle = df.iloc[-1]
            candle_color = latest_candle['candle_color']
           
            # ดึงค่า RSI ล่าสุด
            rsi_value = latest_candle['rsi']
           
            # ตรวจสอบเงื่อนไข BUY/SELL (เปลี่ยนตามโจทย์ใหม่)
            is_uptrend = (uptrend_count == self.trend_periods)
            is_downtrend = (downtrend_count == self.trend_periods)
           
            # เงื่อนไขใหม่:
            # BUY = มีสัญญาณ UPTREND และ ราคาสูงสุดของ CANDLE สูงกว่า E2 และ ราคาต่ำสุดของ CANDLE ต่ำกว่า E2 และ CANDLE เป็นสีเขียว และ BTCUPTREND และ RSI น้อยกว่า 70
            buy_signal = (is_uptrend and
                         latest_candle['high'] > latest_candle['E2'] and
                         latest_candle['low'] < latest_candle['E2'] and
                         candle_color == 'green' and
                         self.btc_trend == 'UP' and
                         rsi_value < 70)
           
            # SELL = มีสัญญาณ DOWNTREND และ ราคาสูงสุดของ CANDLE สูงกว่า E2 และ ราคาต่ำสุดของ CANDLE ต่ำกว่า E2 และ CANDLE เป็นสีแดง และ BTCDOWNTREND และ RSI มากกว่า 30
            sell_signal = (is_downtrend and
                          latest_candle['high'] > latest_candle['E2'] and
                          latest_candle['low'] < latest_candle['E2'] and
                          candle_color == 'red' and
                          self.btc_trend == 'DOWN' and
                          rsi_value > 30)
           
            return {
                'is_uptrend': is_uptrend,
                'is_downtrend': is_downtrend,
                'uptrend_count': uptrend_count,
                'downtrend_count': downtrend_count,
                'stoplong': stoplong,
                'stopshort': stopshort,
                'buy_signal': buy_signal,
                'sell_signal': sell_signal,
                'candle_color': candle_color,
                'latest_price': latest_candle['close'],
                'E1': latest_candle['E1'],
                'E2': latest_candle['E2'],
                'E3': latest_candle['E3'],
                'candle_low': latest_candle['low'],
                'candle_high': latest_candle['high'],
                'rsi': rsi_value
            }
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการคำนวณเทรนด์: {str(e)}[/red]")
            return {'is_uptrend': False, 'is_downtrend': False}


    def get_latest_price(self, contract: str) -> float:
        """ดึงราคาล่าสุดของสัญญา"""
        try:
            for t in self.futures_api.list_futures_tickers(settle='usdt'):
                if t.contract == contract: return float(t.last)
            self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
            return None
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงราคาล่าสุด {contract}: {str(e)}[/red]")
            return None


    def check_trading_signal(self, df: pd.DataFrame, trend_data: dict, contract: str = None) -> str:
        """ตรวจสอบสัญญาณการเทรดตามเงื่อนไข EMA และ RSI ใหม่"""
        try:
            if not trend_data: return None
            latest_price = self.get_latest_price(contract)
            if latest_price is None: return None
           
            # แสดงข้อมูลการวิเคราะห์
            self.console.print(f"[blue]   ตรวจสอบสัญญาณ: ราคาล่าสุด={latest_price:.6f}[/blue]")
            self.console.print(f"[blue]   EMA: E1(5)={trend_data['E1']:.6f}, E2(10)={trend_data['E2']:.6f}, E3(30)={trend_data['E3']:.6f}[/blue]")
            self.console.print(f"[blue]   RSI: {trend_data['rsi']:.2f}[/blue]")
            self.console.print(f"[blue]   STOP: STOPLONG={trend_data['stoplong']:.6f}, STOPSHORT={trend_data['stopshort']:.6f}[/blue]")
           
            candle_color_display = "🟩 สีเขียว" if trend_data['candle_color'] == 'green' else "🟥 สีแดง" if trend_data['candle_color'] == 'red' else "⬛ Doji"
            self.console.print(f"[blue]   แท่งเทียนล่าสุด: {candle_color_display}, Low={trend_data['candle_low']:.6f}, High={trend_data['candle_high']:.6f}[/blue]")
           
            # แสดงสถานะเทรนด์
            if trend_data.get('is_uptrend', False):
                self.console.print(f"[green]   ✓ เงื่อนไข UPTREND เป็นจริง (E1 > E2 > E3 ต่อเนื่อง {trend_data['uptrend_count']}/{self.trend_periods} ชั่วโมง)[/green]")
            else:
                self.console.print(f"[blue]   ✗ เงื่อนไข UPTREND ไม่เป็นจริง (E1 > E2 > E3: {trend_data['uptrend_count']}/{self.trend_periods})[/blue]")
           
            if trend_data.get('is_downtrend', False):
                self.console.print(f"[red]   ✓ เงื่อนไข DOWNTREND เป็นจริง (E1 < E2 < E3 ต่อเนื่อง {trend_data['downtrend_count']}/{self.trend_periods} ชั่วโมง)[/red]")
            else:
                self.console.print(f"[blue]   ✗ เงื่อนไข DOWNTREND ไม่เป็นจริง (E1 < E2 < E3: {trend_data['downtrend_count']}/{self.trend_periods})[/blue]")
           
            # แสดงสถานะ BTC
            if self.btc_trend == "UP":
                self.console.print(f"[green]   ✓ BTC อยู่ในเทรนด์ขาขึ้น (BTCUPTREND)[/green]")
            elif self.btc_trend == "DOWN":
                self.console.print(f"[red]   ✓ BTC อยู่ในเทรนด์ขาลง (BTCDOWNTREND)[/red]")
            else:
                self.console.print(f"[blue]   ✗ BTC ไม่อยู่ในเทรนด์ที่ชัดเจน[/blue]")
           
            # แสดงสถานะการตัด E2
            if trend_data['candle_high'] > trend_data['E2']:
                self.console.print(f"[green]   ✓ ราคาสูงสุดของแท่งเทียน ({trend_data['candle_high']:.6f}) สูงกว่า E2 ({trend_data['E2']:.6f})[/green]")
            else:
                self.console.print(f"[blue]   ✗ ราคาสูงสุดของแท่งเทียนไม่สูงกว่า E2[/blue]")
               
            if trend_data['candle_low'] < trend_data['E2']:
                self.console.print(f"[green]   ✓ ราคาต่ำสุดของแท่งเทียน ({trend_data['candle_low']:.6f}) ต่ำกว่า E2 ({trend_data['E2']:.6f})[/green]")
            else:
                self.console.print(f"[blue]   ✗ ราคาต่ำสุดของแท่งเทียนไม่ต่ำกว่า E2[/blue]")
           
            # แสดงสถานะ RSI
            if trend_data['rsi'] < 70:
                self.console.print(f"[green]   ✓ RSI < 70 ({trend_data['rsi']:.2f})[/green]")
            else:
                self.console.print(f"[blue]   ✗ RSI ไม่น้อยกว่า 70 ({trend_data['rsi']:.2f})[/blue]")
               
            if trend_data['rsi'] > 30:
                self.console.print(f"[red]   ✓ RSI > 30 ({trend_data['rsi']:.2f})[/red]")
            else:
                self.console.print(f"[blue]   ✗ RSI ไม่มากกว่า 30 ({trend_data['rsi']:.2f})[/blue]")
           
            # ตรวจสอบเงื่อนไข BUY/SELL
            if trend_data.get('buy_signal', False):
                self.console.print(f"[green]🟢 สัญญาณ BUY: UPTREND + ราคาสูงสุดของแท่งเทียน > E2 + ราคาต่ำสุดของแท่งเทียน < E2 + แท่งเทียนสีเขียว + BTCUPTREND + RSI < 70[/green]")
                return "BUY"
           
            if trend_data.get('sell_signal', False):
                self.console.print(f"[red]🔴 สัญญาณ SELL: DOWNTREND + ราคาสูงสุดของแท่งเทียน > E2 + ราคาต่ำสุดของแท่งเทียน < E2 + แท่งเทียนสีแดง + BTCDOWNTREND + RSI > 30[/red]")
                return "SELL"
           
            return None
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการตรวจสอบสัญญาณ: {str(e)}[/red]")
            return None


    def should_close_position(self, position: Dict, contract: str = None, trend_data: dict = None) -> bool:
        """ตรวจสอบเงื่อนไขปิด position ตามเงื่อนไขที่กำหนดใหม่"""
        try:
            if trend_data is None: return False
           
            size = float(position['size'])
            entry_price = float(position['entry_price'])
           
            # คำนวณ P&L เป็นเปอร์เซ็นต์
            latest_price = self.get_latest_price(contract)
            if latest_price is None: return False
           
            pnl_percentage = ((latest_price - entry_price) / entry_price * 100) if size > 0 else ((entry_price - latest_price) / entry_price * 100)
           
            close_reason = None
            if size > 0:  # LONG position
                # เงื่อนไขปิด position long: ราคาต่ำสุดของ CANDLE ปัจจุบัน ต่ำกว่า STOPLONG
                if trend_data['candle_low'] < trend_data['stoplong']:
                    close_reason = f"ราคาต่ำสุดของ CANDLE {trend_data['candle_low']:.6f} ต่ำกว่า STOPLONG {trend_data['stoplong']:.6f}"
            elif size < 0:  # SHORT position
                # เงื่อนไขปิด position short: ราคาสูงสุดของ CANDLE ปัจจุบัน สูงกว่า STOPSHORT
                if trend_data['candle_high'] > trend_data['stopshort']:
                    close_reason = f"ราคาสูงสุดของ CANDLE {trend_data['candle_high']:.6f} สูงกว่า STOPSHORT {trend_data['stopshort']:.6f}"
           
            if close_reason:
                self.console.print(f"[yellow]🟡 เข้าเงื่อนไขปิด {'LONG' if size > 0 else 'SHORT'}: {close_reason} (P&L: {pnl_percentage:.2f}%)[/yellow]")
                return True
           
            return False
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการตรวจสอบเงื่อนไขปิด position: {str(e)}[/red]")
            return False


    def check_existing_position(self, contract: str) -> Dict:
        """ตรวจสอบว่ามี position ที่เปิดอยู่หรือไม่"""
        try:
            for p in self.futures_api.list_positions(settle='usdt', holding=True):
                if p.contract == contract:
                    pos_info = p.to_dict()
                    size = float(pos_info['size'])
                    position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                    self.console.print(f"[yellow]พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                    return {'type': position_type, 'data': pos_info}
            return None
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการตรวจสอบ position ที่มีอยู่: {str(e)}[/red]")
            return None


    def set_leverage(self, contract: str) -> bool:
        """ตั้งค่า leverage สำหรับการเทรด"""
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            self.console.print(f"[yellow]ตั้งค่า leverage {self.leverage}x สำหรับ {contract}[/yellow]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถตั้งค่า leverage สำหรับ {contract}: {str(e)}[/red]")
            return False


    def close_position(self, contract: str, position: Dict) -> bool:
        """ปิด position ที่มีอยู่"""
        try:
            size = float(position['size'])
            if size == 0: return False
            direction = abs(size) if size < 0 else -size
            self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': direction, 'price': 0, 'tif': 'ioc', 'reduce_only': True})
            self.console.print(f"[green]✅ ปิด position {'LONG' if size > 0 else 'SHORT'} สำหรับ {contract}: ขนาด={abs(size)}[/green]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถปิด position สำหรับ {contract}: {str(e)}[/red]")
            return False


    def create_order(self, contract: str, is_long: bool) -> Dict:
        """เปิด position LONG หรือ SHORT"""
        try:
            if not self.set_leverage(contract): return None
            price = self.get_latest_price(contract)
            if not price: return None
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': size if is_long else -size, 'price': 0, 'tif': 'ioc', 'reduce_only': False})
            position_type = "LONG" if is_long else "SHORT"
            self.console.print(f"[{'green' if is_long else 'red'}]✅ เปิด position {position_type}: {contract} ขนาด={size}[/{'green' if is_long else 'red'}]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด {'LONG' if is_long else 'SHORT'} สำหรับ {contract}: {str(e)}[/red]")
            return None


    def scan_positions(self):
        """สแกน positions ที่เปิดอยู่เพื่อทำการปิดตามเงื่อนไขที่กำหนด"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            positions_checked, positions_closed = 0, 0
           
            # สร้าง dictionary เพื่อเก็บข้อมูล trend ของแต่ละสัญญา
            trend_data_values = {}
           
            # ดึงข้อมูลแท่งเทียนและคำนวณ trend data สำหรับแต่ละสัญญาที่มี position
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                if not df.empty:
                    trend_data = self.calculate_trend_signal(df)
                    if trend_data:
                        trend_data_values[contract] = trend_data
           
            for pos in positions:
                contract, size = pos['contract'], float(pos['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else None
                if not position_type: continue
                entry_price = float(pos['entry_price'])
                self.console.print(f"[cyan]▶ ตรวจสอบ: {contract} ({position_type}) - ราคาเข้า: {entry_price:.6f} - ขนาด: {abs(size)}[/cyan]")
                latest_price = self.get_latest_price(contract)
                if not latest_price:
                    self.console.print(f"[red]❌ ไม่สามารถดึงราคาล่าสุดของ {contract} ได้[/red]")
                    continue
               
                # คำนวณ P&L เป็นเปอร์เซ็นต์
                pnl_percentage = ((latest_price - entry_price) / entry_price * 100) if size > 0 else ((entry_price - latest_price) / entry_price * 100)
                self.console.print(f"[{'green' if pnl_percentage > 0 else 'red'}]   P&L: {pnl_percentage:.2f}%[/{'green' if pnl_percentage > 0 else 'red'}]")
               
                # ตรวจสอบเงื่อนไขการปิด position
                trend_data = trend_data_values.get(contract, None)
                close_position = self.should_close_position(pos, contract, trend_data)
                if close_position:
                    self.console.print(f"[yellow]🔔 ปิด {position_type} position: {contract}[/yellow]")
                    if self.close_position(contract, pos): positions_closed += 1
                else:
                    self.console.print(f"[blue]   ยังไม่เข้าเงื่อนไขการปิด position[/blue]")
                positions_checked += 1
            self.console.print(f"[blue]สรุป: ตรวจสอบ {positions_checked}/{len(positions)}, ปิด {positions_closed} positions[/blue]")
            return positions_closed
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน positions: {str(e)}[/red]")
            return 0


    def scan_market(self):
        """สแกนตลาดเพื่อหาสัญญาณการเทรดและจัดการ positions"""
        first_run = True
        stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                if current_time.minute % 5 == 0:
                    if current_time.minute == 55:
                        first_run = True
                    else:
                        # ตรวจสอบ Positions ที่มีอยู่
                        self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                        scan_stats = {'positions_closed': self.scan_positions()}
                        time.sleep(60)  # รอ 1 นาทีเพื่อไม่ให้สแกนซ้ำในช่วงเวลาเดียวกัน
                   
                if current_time.minute == 55 or first_run:  # สแกนทุกชั่วโมงเต็ม หรือครั้งแรกที่เริ่มโปรแกรม
                    self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    first_run = False
                    scan_stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
                   
                    # ตรวจสอบเทรนด์ของ BTC ก่อน
                    self.console.print(f"[blue]📊 ตรวจสอบเทรนด์ของ BTC[/blue]")
                    self.btc_trend = self.check_btc_trend()
                   
                    # ถ้า BTC ไม่อยู่ในเทรนด์ที่ชัดเจน ไม่ต้องเปิด position ใหม่
                    if self.btc_trend is None:
                        self.console.print(f"[yellow]⚠️ BTC ไม่อยู่ในเทรนด์ที่ชัดเจน จะไม่เปิด position ใหม่[/yellow]")
                    
                    # ตรวจสอบ Positions ที่มีอยู่
                    self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                    scan_stats['positions_closed'] = self.scan_positions()
                   
                    # ตรวจหาสัญญาณเทรดใหม่ (แม้ BTC ไม่อยู่ในเทรนด์ที่ชัดเจน เราก็ยังตรวจสอบสัญญาอื่น แต่จะไม่เปิด position ใหม่)
                    self.console.print(f"[blue]📊 ตรวจหาสัญญาณเทรดใหม่[/blue]")
                    contracts = self.get_futures_contracts()
                    for i, contract in enumerate(contracts, 1):
                        # ข้าม BTC เพราะเราตรวจสอบไปแล้ว
                        if contract == 'BTC_USDT':
                            continue
                           
                        self.console.print(f"[cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract}[/cyan]")
                        df = self.get_candlesticks(contract)
                        if df.empty:
                            self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                            continue
                       
                        trend_data = self.calculate_trend_signal(df)
                        if not trend_data:
                            self.console.print(f"[red]❌ ไม่สามารถคำนวณเทรนด์สำหรับ {contract} ได้[/red]")
                            continue
                       
                        signal = self.check_trading_signal(df, trend_data, contract)
                        if signal:
                            if signal == "BUY":
                                scan_stats['buy_signals'] += 1
                                # ตรวจสอบ position ที่มีอยู่
                                existing_position = self.check_existing_position(contract)
                               
                                if existing_position:
                                    if existing_position['type'] == "LONG":
                                        # มี LONG อยู่แล้ว ไม่ทำอะไร
                                        self.console.print(f"[yellow]⚠️ มี LONG position อยู่แล้ว ไม่เปิดเพิ่ม[/yellow]")
                                    else:  # มี SHORT อยู่
                                        self.console.print(f"[yellow]⚠️ มี SHORT position อยู่ แต่เราต้องการ LONG ตามสัญญาณ BUY[/yellow]")
                                        self.console.print(f"[yellow]⚠️ เงื่อนไขไม่ได้ระบุให้ปิด SHORT เพื่อเปิด LONG[/yellow]")
                                else:  # ไม่มี position
                                    self.console.print(f"[green]🆕 เปิด LONG position ตามสัญญาณ BUY[/green]")
                                    if self.create_order(contract, True):  # true คือ LONG
                                        scan_stats['long_opened'] += 1
                           
                            elif signal == "SELL":
                                scan_stats['sell_signals'] += 1
                                # ตรวจสอบ position ที่มีอยู่
                                existing_position = self.check_existing_position(contract)
                               
                                if existing_position:
                                    if existing_position['type'] == "SHORT":
                                        # มี SHORT อยู่แล้ว ไม่ทำอะไร
                                        self.console.print(f"[yellow]⚠️ มี SHORT position อยู่แล้ว ไม่เปิดเพิ่ม[/yellow]")
                                    else:  # มี LONG อยู่
                                        self.console.print(f"[yellow]⚠️ มี LONG position อยู่ แต่เราต้องการ SHORT ตามสัญญาณ SELL[/yellow]")
                                        self.console.print(f"[yellow]⚠️ เงื่อนไขไม่ได้ระบุให้ปิด LONG เพื่อเปิด SHORT[/yellow]")
                                else:  # ไม่มี position
                                    self.console.print(f"[red]🆕 เปิด SHORT position ตามสัญญาณ SELL[/red]")
                                    if self.create_order(contract, False):  # false คือ SHORT
                                        scan_stats['short_opened'] += 1
                        else:
                            self.console.print(f"[blue]   ไม่พบสัญญาณเทรด[/blue]")
                        scan_stats['contracts_scanned'] += 1
                   
                    # อัปเดตสถิติรวม
                    for key in stats: stats[key] += scan_stats[key]
                   
                    # แสดงสรุปการสแกน
                    self.console.print(f"[blue]===== สรุปการสแกนรอบนี้ =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกน: {scan_stats['contracts_scanned']}/{len(contracts)-1}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ BUY: {scan_stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SELL: {scan_stats['sell_signals']}[/red]")
                    self.console.print(f"[green]📈 เปิด LONG: {scan_stats['long_opened']}[/green]")
                    self.console.print(f"[red]📉 เปิด SHORT: {scan_stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position: {scan_stats['positions_closed']}[/yellow]")
                   
                    # แสดงสถิติรวมทั้งหมด
                    self.console.print(f"[blue]===== สถิติรวมทั้งหมด =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกนทั้งหมด: {stats['contracts_scanned']}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ BUY ทั้งหมด: {stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SELL ทั้งหมด: {stats['sell_signals']}[/red]")
                    self.console.print(f"[green]📈 เปิด LONG ทั้งหมด: {stats['long_opened']}[/green]")
                    self.console.print(f"[red]📉 เปิด SHORT ทั้งหมด: {stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position ทั้งหมด: {stats['positions_closed']}[/yellow]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    time.sleep(30)
                time.sleep(10)
            except KeyboardInterrupt:
                self.console.print("[yellow]โปรแกรมถูกหยุดโดยผู้ใช้[/yellow]")
                break
            except Exception as e:
                self.console.print(f"[red]❌ เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}[/red]")
                time.sleep(60)


def main():
    try:
        trader = GateIOEMATrader()
        trader.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย EMA และ RSI Strategy...[/blue]")
        trader.scan_market()
    except KeyboardInterrupt:
        print("\nโปรแกรมถูกหยุดโดยผู้ใช้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดร้ายแรง: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()