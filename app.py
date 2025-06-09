#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, time, re, sys
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
from rich.console import Console

class BinanceEMATrader:
    def __init__(self):
        try:
            # ปรับการโหลด environment variables ให้ทำงานได้ดีกับ Docker
            load_dotenv(override=True)
            self.api_key = os.getenv('BINANCE_API_KEY')
            self.secret_key = os.getenv('BINANCE_SECRET_KEY')
           
            # เพิ่มทางเลือกให้รับ API keys จาก environment variables โดยตรง
            if not self.api_key:
                self.api_key = os.environ.get('BINANCE_API_KEY')
            if not self.secret_key:
                self.secret_key = os.environ.get('BINANCE_SECRET_KEY')
               
            if not self.api_key or not self.secret_key:
                raise ValueError("API keys ไม่พบในไฟล์ .env หรือ environment variables")
               
            # สร้าง Binance client
            self.client = Client(self.api_key, self.secret_key)
           
            # กำหนดค่าต่างๆ
            self.leverage = 5
            self.order_amount = 5  # ในหน่วย USDT
           
            # กำหนดพารามิเตอร์สำหรับ EMA - เปลี่ยนเป็น EMA7, EMA25, EMA99 ตามเงื่อนไขใหม่
            self.ema_short = 7       # E1
            self.ema_mid = 25        # E2
            self.ema_long = 99       # E3
           
            # กำหนดพารามิเตอร์สำหรับ RSI
            self.rsi_period = 14
           
            # กำหนดพารามิเตอร์สำหรับการวิเคราะห์เทรนด์
            self.trend_lookback = 7  # จำนวน timeframes สำหรับตรวจสอบเทรนด์ -> แก้เป็น 7 ตามเงื่อนไข
           
            # กำหนดพารามิเตอร์สำหรับ stop loss
            self.stop_lookback = 5  # จำนวน timeframes สำหรับหา stop loss
           
            # กำหนดค่า profit/loss percentage สำหรับปิด position
            self.profit_percentage = 3.0  # กำไร 3%
            self.loss_percentage = 2.0   # ขาดทุน 2%
           
            self.console = Console()
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการเริ่มต้น: {str(e)}")
            sys.exit(1)

    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ"""
        try:
            self.console.print(f"[blue]กำลังดึงข้อมูลสัญญา futures จาก Binance...[/blue]")
           
            # ดึงข้อมูลสัญญา futures ทั้งหมด
            exchange_info = self.client.futures_exchange_info()
            symbols = [symbol['symbol'] for symbol in exchange_info['symbols']
                    if symbol['status'] == 'TRADING' and symbol['quoteAsset'] == 'USDT']
           
            self.console.print(f"[blue]พบสัญญา futures ทั้งหมด {len(symbols)} สัญญา[/blue]")
           
            # ดึงข้อมูล ticker ทั้งหมดพร้อมกันเพื่อเพิ่มประสิทธิภาพ
            self.console.print(f"[blue]กำลังดึงข้อมูลปริมาณการซื้อขาย...[/blue]")
            tickers = self.client.futures_ticker()
           
            # สร้าง dictionary ของ ticker เพื่อให้ค้นหาได้เร็วขึ้น
            ticker_dict = {ticker['symbol']: ticker for ticker in tickers}
           
            # กรองสัญญาที่มีสภาพคล่องเพียงพอ
            valid_contracts = []
            for symbol in symbols:
                if symbol in ticker_dict:
                    ticker = ticker_dict[symbol]
                    volume = float(ticker['volume']) * float(ticker['lastPrice'])
                    if volume > 100000:  # ตรวจสอบสภาพคล่อง
                        valid_contracts.append(symbol)
            # random
            np.random.shuffle(valid_contracts)  # สุ่มลำดับสัญญา
                       
            self.console.print(f"[green]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา[/green]")
           
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

    def get_candlesticks(self, symbol: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนจาก API โดยใช้ timeframe 1 ชั่วโมง และคำนวณ EMA และ RSI"""
        try:
            # ใช้ timeframe เป็น 1 ชั่วโมง
            candles = self.client.futures_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1HOUR, limit=500)
           
            if not candles:
                return pd.DataFrame()
               
            # แปลงข้อมูลแท่งเทียน
            data = []
            for candle in candles:
                data.append({
                    'timestamp': float(candle[0]),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5])
                })
               
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.sort_values('timestamp')
           
            # คำนวณ EMA (E1=EMA7, E2=EMA25, E3=EMA99)
            df[f'E1'] = df['close'].ewm(span=self.ema_short, adjust=False).mean()
            df[f'E2'] = df['close'].ewm(span=self.ema_mid, adjust=False).mean()
            df[f'E3'] = df['close'].ewm(span=self.ema_long, adjust=False).mean()
           
            # คำนวณ RSI
            df['rsi'] = self.calculate_rsi(df['close'], period=self.rsi_period)
           
            # คำนวณข้อมูลเพิ่มเติม
            df['candle_color'] = np.where(df['close'] > df['open'], 'green', np.where(df['close'] < df['open'], 'red', 'doji'))
           
            return df
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงข้อมูลแท่งเทียน {symbol}: {str(e)}[/red]")
            return pd.DataFrame()

    def is_e1_above_e2_above_e3(self, df: pd.DataFrame, lookback: int) -> bool:
        """ตรวจสอบว่า E1 > E2 > E3 ต่อเนื่องหรือไม่"""
        if len(df) < lookback:
            return False
       
        for i in range(1, lookback + 1):
            if not (df.iloc[-i]['E1'] > df.iloc[-i]['E2'] > df.iloc[-i]['E3']):
                return False
        return True

    def is_e1_below_e2_below_e3(self, df: pd.DataFrame, lookback: int) -> bool:
        """ตรวจสอบว่า E1 < E2 < E3 ต่อเนื่องหรือไม่"""
        if len(df) < lookback:
            return False
       
        for i in range(1, lookback + 1):
            if not (df.iloc[-i]['E1'] < df.iloc[-i]['E2'] < df.iloc[-i]['E3']):
                return False
        return True

    def candle_crosses_ema(self, candle, ema_value) -> bool:
        """ตรวจสอบว่าแท่งเทียนทับ EMA หรือไม่ (แท่งเทียนตัด EMA)"""
        return candle['low'] <= ema_value <= candle['high']

    def calculate_trend_signal(self, df: pd.DataFrame) -> dict:
        """คำนวณสัญญาณเทรดตามเงื่อนไขใหม่"""
        try:
            # ตรวจสอบว่ามีข้อมูลเพียงพอหรือไม่
            if len(df) < self.trend_lookback + 1:
                return {
                    'uptrend': False,
                    'downtrend': False,
                    'buy_signal': False,
                    'sell_signal': False
                }
           
            # คำนวณ HIGHPRICE, LOWPRICE
            if len(df) >= self.stop_lookback + 1:
                stop_period = df.iloc[-self.stop_lookback-1:-1]  # ไม่รวม timeframe ปัจจุบัน
                highprice = stop_period['high'].max()
                lowprice = stop_period['low'].min()
            else:
                highprice = df['high'].max()
                lowprice = df['low'].min()
           
            # ดึงข้อมูล CANDLE ล่าสุดและแท่งเทียนก่อนหน้า
            previous_candle = df.iloc[-2] if len(df) >= 2 else None
            if previous_candle is None:
                return {'buy_signal': False, 'sell_signal': False}
           
            # เปลี่ยนเงื่อนไขการกำหนด UPTREND และ DOWNTREND ตามเงื่อนไขใหม่
            uptrend = self.is_e1_above_e2_above_e3(df, self.trend_lookback)
            downtrend = self.is_e1_below_e2_below_e3(df, self.trend_lookback)
           
            # ตรวจสอบว่าแท่งเทียนก่อนหน้าทับ EMA1 หรือไม่
            crosses_ema1 = self.candle_crosses_ema(previous_candle, previous_candle['E1'])
           
            # เงื่อนไขใหม่:
            # BUY = C1 เป็นสีเขียว และ C1 ทับเส้น EMA1 และเป็น UPTREND
            buy_signal = (previous_candle['candle_color'] == 'green' and
                          crosses_ema1 and
                          uptrend)
           
            # SELL = C1 เป็นสีแดง และ C1 ทับเส้น EMA1 และเป็น DOWNTREND
            sell_signal = (previous_candle['candle_color'] == 'red' and
                           crosses_ema1 and
                           downtrend)
           
            return {
                'highprice': highprice,
                'lowprice': lowprice,
                'uptrend': uptrend,
                'downtrend': downtrend,
                'buy_signal': buy_signal,
                'sell_signal': sell_signal,
                'candle_color': previous_candle['candle_color'],
                'crosses_ema1': crosses_ema1,
                'latest_price': df.iloc[-1]['close'],
                'previous_price': previous_candle['close'],
                'E1': previous_candle['E1'],
                'E2': previous_candle['E2'],
                'E3': previous_candle['E3'],
                'candle_low': previous_candle['low'],
                'candle_high': previous_candle['high'],
                'rsi': previous_candle['rsi']
            }
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการคำนวณเทรนด์: {str(e)}[/red]")
            return {'buy_signal': False, 'sell_signal': False}

    def get_latest_price(self, symbol: str) -> float:
        """ดึงราคาล่าสุดของสัญญา"""
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงราคาล่าสุด {symbol}: {str(e)}[/red]")
            return None

    def check_trading_signal(self, df: pd.DataFrame, trend_data: dict, symbol: str = None) -> str:
        """ตรวจสอบสัญญาณการเทรดตามเงื่อนไขใหม่"""
        try:
            if not trend_data: return None
            latest_price = self.get_latest_price(symbol)
            if latest_price is None: return None
           
            # แสดงข้อมูลการวิเคราะห์
            self.console.print(f"[blue]   ตรวจสอบสัญญาณ: ราคาล่าสุด={latest_price:.6f}[/blue]")
            self.console.print(f"[blue]   EMA: E1(7)={trend_data['E1']:.6f}, E2(25)={trend_data['E2']:.6f}, E3(99)={trend_data['E3']:.6f}[/blue]")
            self.console.print(f"[blue]   TREND: UPTREND={trend_data['uptrend']}, DOWNTREND={trend_data['downtrend']}[/blue]")
            self.console.print(f"[blue]   PRICES: HIGHPRICE={trend_data['highprice']:.6f}, LOWPRICE={trend_data['lowprice']:.6f}[/blue]")
            self.console.print(f"[blue]   RSI: {trend_data['rsi']:.2f}[/blue]")
           
            candle_color_display = "🟩 สีเขียว" if trend_data['candle_color'] == 'green' else "🟥 สีแดง" if trend_data['candle_color'] == 'red' else "⬛ Doji"
            self.console.print(f"[blue]   แท่งเทียนก่อนหน้า: {candle_color_display}, Low={trend_data['candle_low']:.6f}, High={trend_data['candle_high']:.6f}[/blue]")
           
            # แสดงสถานะเงื่อนไขสำหรับแท่งเทียนทับ EMA1
            if trend_data['crosses_ema1']:
                self.console.print(f"[green]   ✓ แท่งเทียนก่อนหน้าทับ EMA1 (Low: {trend_data['candle_low']:.6f}, EMA1: {trend_data['E1']:.6f}, High: {trend_data['candle_high']:.6f})[/green]")
            else:
                self.console.print(f"[blue]   ✗ แท่งเทียนก่อนหน้าไม่ทับ EMA1[/blue]")
           
            # แสดงสถานะ UPTREND/DOWNTREND ตามเงื่อนไขใหม่
            if trend_data['uptrend']:
                self.console.print(f"[green]   ✓ เข้าเงื่อนไข UPTREND (E1>E2>E3 ต่อเนื่อง {self.trend_lookback} timeframes)[/green]")
            else:
                self.console.print(f"[blue]   ✗ ไม่เข้าเงื่อนไข UPTREND[/blue]")
               
            if trend_data['downtrend']:
                self.console.print(f"[red]   ✓ เข้าเงื่อนไข DOWNTREND (E1<E2<E3 ต่อเนื่อง {self.trend_lookback} timeframes)[/red]")
            else:
                self.console.print(f"[blue]   ✗ ไม่เข้าเงื่อนไข DOWNTREND[/blue]")
           
            # ตรวจสอบเงื่อนไข BUY/SELL ตามเงื่อนไขใหม่
            if trend_data.get('buy_signal', False):
                self.console.print(f"[green]🟢 สัญญาณ BUY: แท่งเทียนก่อนหน้าสีเขียว + ทับ EMA1 + UPTREND[/green]")
                return "BUY"
           
            if trend_data.get('sell_signal', False):
                self.console.print(f"[red]🔴 สัญญาณ SELL: แท่งเทียนก่อนหน้าสีแดง + ทับ EMA1 + DOWNTREND[/red]")
                return "SELL"
           
            # ถ้าไม่เข้าเงื่อนไข ให้ HOLD
            self.console.print(f"[blue]🔵 สัญญาณ HOLD: ไม่เข้าเงื่อนไข BUY หรือ SELL[/blue]")
            return "HOLD"
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการตรวจสอบสัญญาณ: {str(e)}[/red]")
            return None

    def check_existing_position(self, symbol: str) -> Dict:
        """ตรวจสอบว่ามี position ที่เปิดอยู่หรือไม่"""
        try:
            # ดึงข้อมูล position จาก Binance
            positions = self.client.futures_position_information()
           
            for pos in positions:
                if pos['symbol'] == symbol:
                    amt = float(pos['positionAmt'])
                    if amt == 0:  # ไม่มี position
                        continue
                       
                    position_type = "LONG" if amt > 0 else "SHORT"
                    entry_price = float(pos['entryPrice'])
                    leverage = float(pos['leverage'])
                   
                    self.console.print(f"[yellow]พบ position {position_type} สำหรับ {symbol}: ขนาด={abs(amt)}, ราคาเข้า={entry_price}, leverage={leverage}[/yellow]")
                   
                    return {
                        'type': position_type,
                        'data': {
                            'symbol': symbol,
                            'size': amt,
                            'entry_price': entry_price,
                            'leverage': leverage
                        }
                    }
           
            return None
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการตรวจสอบ position ที่มีอยู่: {str(e)}[/red]")
            return None

    def set_leverage(self, symbol: str) -> bool:
        """ตั้งค่า leverage สำหรับการเทรด"""
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=self.leverage)
            self.console.print(f"[yellow]ตั้งค่า leverage {self.leverage}x สำหรับ {symbol}[/yellow]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถตั้งค่า leverage สำหรับ {symbol}: {str(e)}[/red]")
            return False

    def close_position(self, symbol: str, position: Dict) -> bool:
        """ปิด position ที่มีอยู่"""
        try:
            amt = float(position['data']['size'])
            if amt == 0: return False
           
            # สร้างคำสั่งปิด position
            side = "SELL" if amt > 0 else "BUY"  # ถ้าเป็น LONG ให้ SELL, ถ้าเป็น SHORT ให้ BUY
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=abs(amt),
                reduceOnly=True
            )
           
            self.console.print(f"[green]✅ ปิด position {'LONG' if amt > 0 else 'SHORT'} สำหรับ {symbol}: ขนาด={abs(amt)}[/green]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถปิด position สำหรับ {symbol}: {str(e)}[/red]")
            return False

    def create_order(self, symbol: str, is_long: bool) -> Dict:
        """เปิด position LONG หรือ SHORT"""
        try:
            if not self.set_leverage(symbol): return None
           
            # ดึงราคาล่าสุด
            price = self.get_latest_price(symbol)
            if not price: return None
           
            # ดึงข้อมูลสัญญา เพื่อหาค่า min_qty และ precision
            exchange_info = self.client.futures_exchange_info()
            symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
           
            if not symbol_info:
                self.console.print(f"[red]ไม่พบข้อมูลสัญญา {symbol}[/red]")
                return None
               
            # หา precision สำหรับจำนวน
            qty_precision = 0
            for flt in symbol_info['filters']:
                if flt['filterType'] == 'LOT_SIZE':
                    step_size = float(flt['stepSize'])
                    qty_precision = len(str(step_size).rstrip('0').split('.')[1]) if '.' in str(step_size) else 0
                    min_qty = float(flt['minQty'])
                    break
           
            # คำนวณจำนวนที่จะเทรด
            usd_amount = self.order_amount * self.leverage
            qty = usd_amount / price
            qty = max(min_qty, round(qty, qty_precision))
           
            # สร้างคำสั่งเปิด position
            side = "BUY" if is_long else "SELL"
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=qty
            )
           
            position_type = "LONG" if is_long else "SHORT"
            self.console.print(f"[{'green' if is_long else 'red'}]✅ เปิด position {position_type}: {symbol} ขนาด={qty}[/{'green' if is_long else 'red'}]")
           
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด {'LONG' if is_long else 'SHORT'} สำหรับ {symbol}: {str(e)}[/red]")
            return None

    def scan_positions(self):
        """สแกน positions ที่เปิดอยู่เพื่อทำการปิดตามเงื่อนไขใหม่ (กำไร 3% หรือขาดทุน 2%)"""
        try:
            # ดึงข้อมูล positions ทั้งหมด
            positions = [p for p in self.client.futures_position_information() if float(p['positionAmt']) != 0]
           
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            positions_checked, positions_closed = 0, 0
           
            for pos in positions:
                symbol = pos['symbol']
                amt = float(pos['positionAmt'])
                position_type = "LONG" if amt > 0 else "SHORT"
               
                entry_price = float(pos['entryPrice'])
                latest_price = self.get_latest_price(symbol)
               
                if not latest_price:
                    self.console.print(f"[red]❌ ไม่สามารถดึงราคาล่าสุดของ {symbol} ได้[/red]")
                    continue
               
                # คำนวณ P&L เป็นเปอร์เซ็นต์
                pnl_percentage = ((latest_price - entry_price) / entry_price * 100) if amt > 0 else ((entry_price - latest_price) / entry_price * 100)
               
                self.console.print(f"[cyan]▶ ตรวจสอบ: {symbol} ({position_type}) - ราคาเข้า: {entry_price:.6f} - ขนาด: {abs(amt)}[/cyan]")
                self.console.print(f"[{'green' if pnl_percentage > 0 else 'red'}]   P&L: {pnl_percentage:.2f}%[/{'green' if pnl_percentage > 0 else 'red'}]")
               
                # ตรวจสอบเงื่อนไขการปิด position (กำไร 3% หรือขาดทุน 2%)
                close_position = False
                close_reason = ""
               
                if pnl_percentage >= self.profit_percentage:
                    close_position = True
                    close_reason = f"ทำกำไร {pnl_percentage:.2f}% (เกณฑ์: {self.profit_percentage}%)"
                elif pnl_percentage <= -self.loss_percentage:
                    close_position = True
                    close_reason = f"ขาดทุน {abs(pnl_percentage):.2f}% (เกณฑ์: {self.loss_percentage}%)"
               
                if close_position:
                    self.console.print(f"[yellow]🔔 ปิด {position_type} position: {symbol} - {close_reason}[/yellow]")
                   
                    # สร้าง position dictionary ในรูปแบบที่ close_position ใช้
                    pos_dict = {
                        'data': {
                            'symbol': symbol,
                            'size': amt,
                            'entry_price': entry_price
                        }
                    }
                   
                    if self.close_position(symbol, pos_dict):
                        positions_closed += 1
                else:
                    self.console.print(f"[blue]   ยังไม่เข้าเงื่อนไขการปิด position (P&L = {pnl_percentage:.2f}%, เกณฑ์กำไร = {self.profit_percentage}%, เกณฑ์ขาดทุน = {self.loss_percentage}%)[/blue]")
               
                positions_checked += 1
           
            self.console.print(f"[blue]สรุป: ตรวจสอบ {positions_checked}/{len(positions)}, ปิด {positions_closed} positions[/blue]")
            return positions_closed
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน positions: {str(e)}[/red]")
            return 0

    def scan_market(self):
        """สแกนตลาดเพื่อหาสัญญาณการเทรดและจัดการ positions"""
        first_run = True
        stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'hold_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                if current_time.minute % 15 == 0:
                    if current_time.minute == 0:
                        first_run = True
                    else:
                        # ตรวจสอบ Positions ที่มีอยู่
                        self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                        positions_closed = self.scan_positions()
                        stats['positions_closed'] += positions_closed
                        time.sleep(60)  # รอ 1 นาทีเพื่อไม่ให้สแกนบ่อยเกินไป
                if current_time.minute == 0 or first_run:  # สแกนทุกชั่วโมง หรือครั้งแรกที่เริ่มโปรแกรม
                    self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    first_run = False
                    scan_stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'hold_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
                   
                    # ตรวจสอบ Positions ที่มีอยู่
                    self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                    scan_stats['positions_closed'] = self.scan_positions()
                   
                    # ตรวจหาสัญญาณเทรดใหม่
                    self.console.print(f"[blue]📊 ตรวจหาสัญญาณเทรดใหม่[/blue]")
                    symbols = self.get_futures_contracts()
                    for i, symbol in enumerate(symbols, 1):
                        self.console.print(f"[cyan]▶ สแกนสัญญา ({i}/{len(symbols)}): {symbol}[/cyan]")
                        df = self.get_candlesticks(symbol)
                        if df.empty:
                            self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {symbol} ได้[/red]")
                            continue
                       
                        trend_data = self.calculate_trend_signal(df)
                        if not trend_data:
                            self.console.print(f"[red]❌ ไม่สามารถคำนวณเทรนด์สำหรับ {symbol} ได้[/red]")
                            continue
                       
                        signal = self.check_trading_signal(df, trend_data, symbol)
                        if signal == "BUY":
                            scan_stats['buy_signals'] += 1
                            # ตรวจสอบ position ที่มีอยู่
                            existing_position = self.check_existing_position(symbol)
                           
                            if existing_position:
                                if existing_position['type'] == "LONG":
                                    # มี LONG อยู่แล้ว ไม่ทำอะไร
                                    self.console.print(f"[yellow]⚠️ มี LONG position อยู่แล้ว ไม่เปิดเพิ่ม[/yellow]")
                                else:  # มี SHORT อยู่
                                    self.console.print(f"[yellow]⚠️ มี SHORT position อยู่ แต่เราต้องการ LONG ตามสัญญาณ BUY[/yellow]")
                                    self.console.print(f"[yellow]⚠️ เงื่อนไขไม่ได้ระบุให้ปิด SHORT เพื่อเปิด LONG[/yellow]")
                            else:  # ไม่มี position
                                self.console.print(f"[green]🆕 เปิด LONG position ตามสัญญาณ BUY[/green]")
                                if self.create_order(symbol, True):  # true คือ LONG
                                    scan_stats['long_opened'] += 1
                       
                        elif signal == "SELL":
                            scan_stats['sell_signals'] += 1
                            # ตรวจสอบ position ที่มีอยู่
                            existing_position = self.check_existing_position(symbol)
                           
                            if existing_position:
                                if existing_position['type'] == "SHORT":
                                    # มี SHORT อยู่แล้ว ไม่ทำอะไร
                                    self.console.print(f"[yellow]⚠️ มี SHORT position อยู่แล้ว ไม่เปิดเพิ่ม[/yellow]")
                                else:  # มี LONG อยู่
                                    self.console.print(f"[yellow]⚠️ มี LONG position อยู่ แต่เราต้องการ SHORT ตามสัญญาณ SELL[/yellow]")
                                    self.console.print(f"[yellow]⚠️ เงื่อนไขไม่ได้ระบุให้ปิด LONG เพื่อเปิด SHORT[/yellow]")
                            else:  # ไม่มี position
                                self.console.print(f"[red]🆕 เปิด SHORT position ตามสัญญาณ SELL[/red]")
                                if self.create_order(symbol, False):  # false คือ SHORT
                                    scan_stats['short_opened'] += 1
                        elif signal == "HOLD":
                            scan_stats['hold_signals'] += 1
                            self.console.print(f"[blue]   สัญญาณ HOLD: ไม่เข้าเงื่อนไขการเปิด position[/blue]")
                        else:
                            self.console.print(f"[red]   ไม่สามารถวิเคราะห์สัญญาณได้[/red]")
                           
                        scan_stats['contracts_scanned'] += 1
                   
                    # อัปเดตสถิติรวม
                    for key in stats: stats[key] += scan_stats[key]
                   
                    # แสดงสรุปการสแกน
                    self.console.print(f"[blue]===== สรุปการสแกนรอบนี้ =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกน: {scan_stats['contracts_scanned']}/{len(symbols)}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ BUY: {scan_stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SELL: {scan_stats['sell_signals']}[/red]")
                    self.console.print(f"[blue]🔄 สัญญาณ HOLD: {scan_stats['hold_signals']}[/blue]")
                    self.console.print(f"[green]📈 เปิด LONG: {scan_stats['long_opened']}[/green]")
                    self.console.print(f"[red]📉 เปิด SHORT: {scan_stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position: {scan_stats['positions_closed']}[/yellow]")
                   
                    # แสดงสถิติรวมทั้งหมด
                    self.console.print(f"[blue]===== สถิติรวมทั้งหมด =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกนทั้งหมด: {stats['contracts_scanned']}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ BUY ทั้งหมด: {stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SELL ทั้งหมด: {stats['sell_signals']}[/red]")
                    self.console.print(f"[blue]🔄 สัญญาณ HOLD ทั้งหมด: {stats['hold_signals']}[/blue]")
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
        trader = BinanceEMATrader()
        trader.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย EMA Strategy บน Binance Futures...[/blue]")
        trader.scan_market()
    except KeyboardInterrupt:
        print("\nโปรแกรมถูกหยุดโดยผู้ใช้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดร้ายแรง: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()