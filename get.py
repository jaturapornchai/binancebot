#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, time, re, sys
from typing import List, Dict, Tuple, Optional
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi, SpotApi
from rich.console import Console
import datetime


class GateIOTradingAnalyzer:
    def __init__(self, leverage=5, order_amount=20):
        try:
            # ปรับการโหลด environment variables
            load_dotenv(override=True)
            self.api_key = os.getenv('GATEIO_API_KEY')
            self.secret_key = os.getenv('GATEIO_SECRET_KEY')
            
            # ถ้าไม่มีใน .env ลองดึงจาก environment variables โดยตรง
            if not self.api_key:
                self.api_key = os.environ.get('GATEIO_API_KEY')
            if not self.secret_key:
                self.secret_key = os.environ.get('GATEIO_SECRET_KEY')
                
            if not self.api_key or not self.secret_key:
                raise ValueError("API keys ไม่พบในไฟล์ .env หรือ environment variables")
           
            # สร้าง Configuration object
            self.config = Configuration(key=self.api_key, secret=self.secret_key)
            self.client = ApiClient(self.config)
           
            # สร้าง API objects สำหรับ Futures และ Spot markets
            self.futures_api = FuturesApi(self.client)
            self.spot_api = SpotApi(self.client)
           
            # ตั้งค่า console สำหรับการแสดงผล
            self.console = Console()
           
            # กำหนดค่าเริ่มต้น
            self.timeframes = ["5m", "15m", "1h", "4h", "1d"]
            self.candle_limit = 500
            
            # กำหนดค่าสำหรับการเทรด
            self.leverage = leverage
            self.order_amount = order_amount
           
            self.console.print("[green]เชื่อมต่อกับ Gate.io API สำเร็จ[/green]")
       
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการเชื่อมต่อกับ Gate.io API: {str(e)}[/red]")
            sys.exit(1)
   
    def get_candle_data(self, symbol: str, interval="1h", limit=500) -> pd.DataFrame:
        """
        ดึงข้อมูล candlestick ของคู่เทรดตามกรอบเวลาที่กำหนด
       
        Args:
            symbol (str): คู่เทรด เช่น BTC_USDT
            interval (str): กรอบเวลา (5m, 15m, 1h, 4h, 1d)
            limit (int): จำนวนแท่งเทียนที่ต้องการดึง (สูงสุด 1000)
           
        Returns:
            pd.DataFrame: ข้อมูล candlestick ในรูปแบบ DataFrame
        """
        try:
            # ดึงข้อมูล candlestick
            candles = self.spot_api.list_candlesticks(
                currency_pair=symbol,
                interval=interval,
                limit=limit
            )
           
            # สร้าง DataFrame
            if candles and len(candles) > 0:
                # กำหนดชื่อคอลัมน์ตามจำนวนข้อมูลที่ได้รับ
                columns = []
                if len(candles[0]) == 8:
                    columns = ['timestamp', 'volume', 'close', 'high', 'low', 'open', 'volume_quote', 'count']
                else:
                    columns = ['timestamp', 'volume', 'close', 'high', 'low', 'open']
               
                # สร้าง DataFrame
                df = pd.DataFrame(candles, columns=columns)
               
                # แปลงค่าแต่ละคอลัมน์อย่างระมัดระวัง
                for i, row in df.iterrows():
                    for col in columns:
                        try:
                            # แปลงค่า "true" และ "false" เป็น True และ False
                            if isinstance(row[col], str) and row[col].lower() in ['true', 'false']:
                                df.at[i, col] = True if row[col].lower() == 'true' else False
                        except:
                            pass
               
                # แปลง timestamp เป็นตัวเลขก่อนแปลงเป็นวันที่
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
               
                # แปลงคอลัมน์ตัวเลขอื่นๆ
                num_columns = ['volume', 'close', 'high', 'low', 'open']
                for col in num_columns:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
               
                # เพิ่มคอลัมน์เพิ่มเติมถ้ามี
                if 'volume_quote' in df.columns:
                    df['volume_quote'] = pd.to_numeric(df['volume_quote'], errors='coerce')
                if 'count' in df.columns:
                    df['count'] = pd.to_numeric(df['count'], errors='coerce')
               
                # ลบแถวที่มีค่า NaN
                df = df.dropna(subset=['timestamp', 'close'])
               
                # เรียงข้อมูลตามเวลา
                df = df.sort_values('timestamp')
                df.reset_index(drop=True, inplace=True)
               
                return df
           
            return pd.DataFrame()
           
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงข้อมูล candlestick: {str(e)}[/red]")
            return pd.DataFrame()


    def calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series:
        """คำนวณ Exponential Moving Average (EMA)"""
        return df['close'].ewm(span=period, adjust=False).mean()


    def analyze_timeframe(self, df: pd.DataFrame) -> str:
        """
        วิเคราะห์กรอบเวลาเพื่อกำหนดสัญญาณซื้อขาย
       
        Args:
            df (pd.DataFrame): ข้อมูล candlestick
           
        Returns:
            str: 'LONG', 'SHORT', หรือ 'HOLD'
        """
        # ตรวจสอบว่ามีข้อมูลเพียงพอหรือไม่
        if len(df) < 20:
            return "HOLD"
           
        # คำนวณค่าเฉลี่ยเคลื่อนที่
        df['ema9'] = self.calculate_ema(df, 9)
        df['ema21'] = self.calculate_ema(df, 21)
        df['ema50'] = self.calculate_ema(df, 50)
        df['ema200'] = self.calculate_ema(df, 200) if len(df) >= 200 else self.calculate_ema(df, len(df) // 2)
       
        # ดึงข้อมูลล่าสุด
        latest = df.iloc[-1]
        prev = df.iloc[-2]
       
        # เงื่อนไขสำหรับสัญญาณ LONG
        long_conditions = [
            latest['ema9'] > latest['ema21'],  # EMA9 อยู่เหนือ EMA21
            latest['ema21'] > latest['ema50'],  # EMA21 อยู่เหนือ EMA50
            latest['close'] > latest['ema200'],  # ราคาปิดอยู่เหนือ EMA200
            latest['close'] > prev['close'],  # ราคาปิดล่าสุดสูงกว่าราคาปิดก่อนหน้า
            latest['ema9'] > prev['ema9']  # EMA9 มีแนวโน้มเพิ่มขึ้น
        ]
       
        # เงื่อนไขสำหรับสัญญาณ SHORT
        short_conditions = [
            latest['ema9'] < latest['ema21'],  # EMA9 อยู่ต่ำกว่า EMA21
            latest['ema21'] < latest['ema50'],  # EMA21 อยู่ต่ำกว่า EMA50
            latest['close'] < latest['ema200'],  # ราคาปิดอยู่ต่ำกว่า EMA200
            latest['close'] < prev['close'],  # ราคาปิดล่าสุดต่ำกว่าราคาปิดก่อนหน้า
            latest['ema9'] < prev['ema9']  # EMA9 มีแนวโน้มลดลง
        ]
       
        # นับจำนวนเงื่อนไขที่เป็นจริง
        long_score = sum(long_conditions)
        short_score = sum(short_conditions)
       
        # กำหนดเกณฑ์การตัดสินใจ
        if long_score >= 4:
            return "LONG"
        elif short_score >= 4:
            return "SHORT"
        else:
            return "HOLD"

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        ดึงราคาล่าสุดของสัญญา
        
        Args:
            symbol (str): คู่เทรด เช่น BTC_USDT
            
        Returns:
            float: ราคาล่าสุด หรือ None หากไม่สามารถดึงได้
        """
        try:
            # ตรวจสอบว่าเป็น spot หรือ futures
            if symbol.endswith('_USDT'):
                # ถ้าเป็น futures ใช้ futures_api
                for t in self.futures_api.list_futures_tickers(settle='usdt'):
                    if t.contract == symbol:
                        return float(t.last)
            else:
                # ถ้าเป็น spot ใช้ spot_api
                ticker = self.spot_api.get_ticker(currency_pair=symbol)
                if ticker and hasattr(ticker, 'last'):
                    return float(ticker.last)
                    
            self.console.print(f"[red]ไม่พบราคาสำหรับ {symbol}[/red]")
            return None
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงราคาล่าสุด {symbol}: {str(e)}[/red]")
            return None
            
    def check_existing_position(self, symbol: str) -> Optional[Dict]:
        """
        ตรวจสอบว่ามี position ที่เปิดอยู่หรือไม่
        
        Args:
            symbol (str): คู่เทรด เช่น BTC_USDT
            
        Returns:
            Dict: ข้อมูล position หรือ None หากไม่มี
        """
        try:
            for p in self.futures_api.list_positions(settle='usdt', holding=True):
                if p.contract == symbol:
                    pos_info = p.to_dict()
                    size = float(pos_info['size'])
                    position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                    self.console.print(f"[yellow]พบ position {position_type} สำหรับ {symbol}: ขนาด={abs(size)}[/yellow]")
                    return {'type': position_type, 'data': pos_info}
            return None
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการตรวจสอบ position ที่มีอยู่: {str(e)}[/red]")
            return None

    def set_leverage(self, symbol: str) -> bool:
        """
        ตั้งค่า leverage สำหรับการเทรด
        
        Args:
            symbol (str): คู่เทรด เช่น BTC_USDT
            
        Returns:
            bool: True หากตั้งค่าสำเร็จ, False หากไม่สำเร็จ
        """
        try:
            self.futures_api.update_position_leverage(
                contract=symbol, 
                settle='usdt', 
                leverage=str(self.leverage)
            )
            self.console.print(f"[yellow]ตั้งค่า leverage {self.leverage}x สำหรับ {symbol}[/yellow]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถตั้งค่า leverage สำหรับ {symbol}: {str(e)}[/red]")
            return False

    def close_position(self, symbol: str, position: Dict) -> bool:
        """
        ปิด position ที่มีอยู่
        
        Args:
            symbol (str): คู่เทรด เช่น BTC_USDT
            position (Dict): ข้อมูล position ที่ต้องการปิด
            
        Returns:
            bool: True หากปิดสำเร็จ, False หากไม่สำเร็จ
        """
        try:
            size = float(position['data']['size'])
            if size == 0: 
                return False
                
            # กำหนดทิศทางตรงข้ามเพื่อปิด position
            direction = abs(size) if size < 0 else -size
            
            # สร้างคำสั่งปิด position
            order_params = {
                'contract': symbol,
                'size': direction,
                'price': 0,  # ใช้ market order
                'tif': 'ioc',  # immediate-or-cancel
                'reduce_only': True  # ปิด position เท่านั้น
            }
            
            self.futures_api.create_futures_order('usdt', order_params)
            
            position_type = position['type']
            self.console.print(f"[green]✅ ปิด position {position_type} สำหรับ {symbol}: ขนาด={abs(size)}[/green]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถปิด position สำหรับ {symbol}: {str(e)}[/red]")
            return False

    def create_order(self, symbol: str, is_long: bool) -> Optional[Dict]:
        """
        เปิด position LONG หรือ SHORT
        
        Args:
            symbol (str): คู่เทรด เช่น BTC_USDT
            is_long (bool): True สำหรับ LONG, False สำหรับ SHORT
            
        Returns:
            Dict: ข้อมูลคำสั่ง หรือ None หากไม่สำเร็จ
        """
        try:
            # ตั้งค่า leverage ก่อนเปิด position
            if not self.set_leverage(symbol): 
                return None
                
            # ดึงราคาล่าสุด
            price = self.get_latest_price(symbol)
            if not price: 
                return None
                
            # ดึงข้อมูลสัญญา
            contract_info = self.futures_api.get_futures_contract(contract=symbol, settle='usdt')
            contract_dict = contract_info.to_dict()
            
            # คำนวณขนาด position
            multiplier = float(contract_dict['quanto_multiplier'])
            min_size = float(contract_dict['order_size_min'])
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            
            # สร้างคำสั่งเปิด position
            order_params = {
                'contract': symbol,
                'size': size if is_long else -size,
                'price': 0,  # ใช้ market order
                'tif': 'ioc',  # immediate-or-cancel
                'reduce_only': False  # เปิด position ใหม่
            }
            
            order = self.futures_api.create_futures_order('usdt', order_params)
            
            position_type = "LONG" if is_long else "SHORT"
            self.console.print(f"[{'green' if is_long else 'red'}]✅ เปิด position {position_type}: {symbol} ขนาด={size}[/{'green' if is_long else 'red'}]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด {'LONG' if is_long else 'SHORT'} สำหรับ {symbol}: {str(e)}[/red]")
            return None
   
    def get_futures_contracts(self) -> List[str]:
        """
        ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ
        
        Returns:
            List[str]: รายชื่อสัญญาที่สามารถเทรดได้
        """
        try:
            ticket = self.futures_api.list_futures_tickers(settle='usdt')
            valid_contracts = [
                c.contract for c in ticket 
                if re.match(r'^\D+_USDT$', c.contract) 
                and c.contract not in ['USDC_USDT', 'DOGS_USDT'] 
                and float(c.volume_24h) * float(c.last) > 1000000
            ]
            self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา[/blue]")
            return valid_contracts
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงรายชื่อสัญญา: {str(e)}[/red]")
            return []
            
    def scan_positions(self) -> int:
        """
        สแกน positions ที่เปิดอยู่เพื่อทำการปิดตามเงื่อนไขที่กำหนด
        
        Returns:
            int: จำนวน positions ที่ถูกปิด
        """
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            positions_checked, positions_closed = 0, 0
            
            for pos in positions:
                contract = pos['contract']
                size = float(pos['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else None
                if not position_type: 
                    continue
                    
                entry_price = float(pos['entry_price'])
                self.console.print(f"[cyan]▶ ตรวจสอบ: {contract} ({position_type}) - ราคาเข้า: {entry_price:.6f} - ขนาด: {abs(size)}[/cyan]")
                
                # ดึงข้อมูลแท่งเทียนเพื่อตรวจสอบสัญญาณการซื้อขาย
                df = self.get_candle_data(contract, interval='1h', limit=500)
                if df.empty:
                    self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                    continue
                    
                signal = self.analyze_timeframe(df)
                
                # ตรวจสอบเงื่อนไขการปิด position
                close_position = False
                
                # กรณี position เป็น LONG แต่สัญญาณเป็น SHORT หรือ HOLD
                if position_type == "LONG" and (signal == "SHORT" or signal == "HOLD"):
                    close_position = True
                    reason = f"สัญญาณเปลี่ยนเป็น {signal}"
                    
                # กรณี position เป็น SHORT แต่สัญญาณเป็น LONG หรือ HOLD
                elif position_type == "SHORT" and (signal == "LONG" or signal == "HOLD"):
                    close_position = True
                    reason = f"สัญญาณเปลี่ยนเป็น {signal}"
                
                # ถ้าควรปิด position
                if close_position:
                    self.console.print(f"[yellow]🔔 ปิด {position_type} position: {contract} - เหตุผล: {reason}[/yellow]")
                    # ปิด position
                    if self.close_position(contract, {'type': position_type, 'data': pos}):
                        positions_closed += 1
                else:
                    self.console.print(f"[blue]   ยังไม่เข้าเงื่อนไขการปิด position[/blue]")
                    
                positions_checked += 1
                
            self.console.print(f"[blue]สรุป: ตรวจสอบ {positions_checked}/{len(positions)}, ปิด {positions_closed} positions[/blue]")
            return positions_closed
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน positions: {str(e)}[/red]")
            return 0
            
    def scan_market(self):
        """สแกนตลาดเพื่อหาสัญญาณการเทรดและจัดการ positions แบบต่อเนื่อง"""
        first_run = True
        stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
        
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                
                # สแกนทุก 5 นาที แต่ไม่ใช่นาทีที่ 55 (เพราะที่ 55 จะสแกนทั้งหมด)
                if current_time.minute % 5 == 0 and current_time.minute != 55:
                    if not first_run:  # ข้ามการตรวจสอบครั้งแรก (เพราะจะสแกนทั้งหมดอยู่แล้ว)
                        # ตรวจสอบ Positions ที่มีอยู่
                        self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่ {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                        scan_stats = {'positions_closed': self.scan_positions()}
                        time.sleep(60)  # รอ 1 นาทีเพื่อไม่ให้สแกนซ้ำในช่วงเวลาเดียวกัน
                
                # สแกนตลาดเต็มรูปแบบในนาทีที่ 55 หรือตอนเริ่มต้นโปรแกรม
                if current_time.minute == 55 or first_run:
                    self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    first_run = False
                    scan_stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
                    
                    # ตรวจสอบ Positions ที่มีอยู่
                    self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                    scan_stats['positions_closed'] = self.scan_positions()
                    
                    # ตรวจหาสัญญาณเทรดใหม่
                    self.console.print(f"[blue]📊 ตรวจหาสัญญาณเทรดใหม่[/blue]")
                    contracts = self.get_futures_contracts()
                    
                    for i, contract in enumerate(contracts, 1):
                        self.console.print(f"[cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract}[/cyan]")
                        
                        # ดึงข้อมูลและวิเคราะห์
                        df = self.get_candle_data(contract, interval='1h', limit=500)
                        if df.empty:
                            self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                            continue
                        
                        signal = self.analyze_timeframe(df)
                        
                        # ตรวจสอบและดำเนินการตามสัญญาณ
                        if signal == "LONG":
                            scan_stats['buy_signals'] += 1
                            # ตรวจสอบ position ที่มีอยู่
                            existing_position = self.check_existing_position(contract)
                            
                            if existing_position:
                                if existing_position['type'] == "LONG":
                                    # มี LONG อยู่แล้ว ไม่ทำอะไร
                                    self.console.print(f"[yellow]⚠️ มี LONG position อยู่แล้ว ไม่เปิดเพิ่ม[/yellow]")
                                else:  # มี SHORT อยู่
                                    self.console.print(f"[yellow]⚠️ มี SHORT position อยู่ แต่สัญญาณแนะนำ LONG[/yellow]")
                                    self.console.print(f"[yellow]🔔 ปิด SHORT position ก่อนเปิด LONG[/yellow]")
                                    if self.close_position(contract, existing_position):
                                        self.console.print(f"[green]🆕 เปิด LONG position หลังจากปิด SHORT[/green]")
                                        if self.create_order(contract, True):  # เปิด LONG
                                            scan_stats['long_opened'] += 1
                            else:  # ไม่มี position
                                self.console.print(f"[green]🆕 เปิด LONG position ตามสัญญาณ[/green]")
                                if self.create_order(contract, True):  # เปิด LONG
                                    scan_stats['long_opened'] += 1
                            
                        elif signal == "SHORT":
                            scan_stats['sell_signals'] += 1
                            # ตรวจสอบ position ที่มีอยู่
                            existing_position = self.check_existing_position(contract)
                            
                            if existing_position:
                                if existing_position['type'] == "SHORT":
                                    # มี SHORT อยู่แล้ว ไม่ทำอะไร
                                    self.console.print(f"[yellow]⚠️ มี SHORT position อยู่แล้ว ไม่เปิดเพิ่ม[/yellow]")
                                else:  # มี LONG อยู่
                                    self.console.print(f"[yellow]⚠️ มี LONG position อยู่ แต่สัญญาณแนะนำ SHORT[/yellow]")
                                    self.console.print(f"[yellow]🔔 ปิด LONG position ก่อนเปิด SHORT[/yellow]")
                                    if self.close_position(contract, existing_position):
                                        self.console.print(f"[red]🆕 เปิด SHORT position หลังจากปิด LONG[/red]")
                                        if self.create_order(contract, False):  # เปิด SHORT
                                            scan_stats['short_opened'] += 1
                            else:  # ไม่มี position
                                self.console.print(f"[red]🆕 เปิด SHORT position ตามสัญญาณ[/red]")
                                if self.create_order(contract, False):  # เปิด SHORT
                                    scan_stats['short_opened'] += 1
                        else:
                            self.console.print(f"[blue]   สัญญาณแนะนำให้ HOLD ไม่ดำเนินการใดๆ[/blue]")
                        
                        scan_stats['contracts_scanned'] += 1
                    
                    # อัปเดตสถิติรวม
                    for key in stats:
                        stats[key] += scan_stats[key]
                    
                    # แสดงสรุปการสแกนรอบนี้
                    self.console.print(f"[blue]===== สรุปการสแกนรอบนี้ =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกน: {scan_stats['contracts_scanned']}/{len(contracts)}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ LONG: {scan_stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SHORT: {scan_stats['sell_signals']}[/red]")
                    self.console.print(f"[green]📈 เปิด LONG: {scan_stats['long_opened']}[/green]")
                    self.console.print(f"[red]📉 เปิด SHORT: {scan_stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position: {scan_stats['positions_closed']}[/yellow]")
                   
                    # แสดงสถิติรวมทั้งหมด
                    self.console.print(f"[blue]===== สถิติรวมทั้งหมด =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกนทั้งหมด: {stats['contracts_scanned']}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ LONG ทั้งหมด: {stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SHORT ทั้งหมด: {stats['sell_signals']}[/red]")
                    self.console.print(f"[green]📈 เปิด LONG ทั้งหมด: {stats['long_opened']}[/green]")
                    self.console.print(f"[red]📉 เปิด SHORT ทั้งหมด: {stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position ทั้งหมด: {stats['positions_closed']}[/yellow]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    
                    # หากเพิ่งเสร็จสิ้นการสแกนที่นาที 55 รอสักครู่เพื่อไม่ให้เริ่มต้นสแกนซ้ำ
                    if current_time.minute == 55:
                        time.sleep(30)
                
                # รอสักครู่ก่อนตรวจสอบเวลาอีกครั้ง
                time.sleep(10)
                
            except KeyboardInterrupt:
                self.console.print("[yellow]โปรแกรมถูกหยุดโดยผู้ใช้[/yellow]")
                break
            except Exception as e:
                self.console.print(f"[red]❌ เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}[/red]")
                time.sleep(60)  # หากเกิดข้อผิดพลาด รอ 1 นาทีก่อนลองใหม่
                
    def analyze_symbol(self, symbol: str, trade: bool = False) -> Tuple[str, Dict]:
        """
        วิเคราะห์สัญญาณซื้อขายสำหรับคู่เทรดที่ระบุ และดำเนินการซื้อขายหากเปิดใช้งาน
       
        Args:
            symbol (str): คู่เทรด เช่น BTC_USDT, ETH_USDT
            trade (bool): เปิดใช้งานการซื้อขายหรือไม่ (ค่าเริ่มต้นคือ False)
           
        Returns:
            Tuple[str, Dict]: สัญญาณซื้อขาย ('LONG', 'SHORT', หรือ 'HOLD') และข้อมูลการวิเคราะห์ทั้งหมด
        """
        # ตรวจสอบรูปแบบ symbol ที่ถูกต้อง
        if "_" not in symbol:
            # แปลงรูปแบบ เช่น BTCUSDT เป็น BTC_USDT
            if "USDT" in symbol:
                parts = symbol.split("USDT")
                symbol = f"{parts[0]}_USDT"
       
        self.console.print(f"[bold blue]กำลังวิเคราะห์ {symbol}...[/bold blue]")
       
        # เตรียมผลลัพธ์
        results = {
            "symbol": symbol,
            "timestamp": datetime.datetime.now().isoformat(),
            "timeframes": {},
            "signals_count": {"LONG": 0, "SHORT": 0, "HOLD": 0}
        }
       
        # วิเคราะห์แต่ละกรอบเวลา
        for tf in self.timeframes:
            df = self.get_candle_data(symbol=symbol, interval=tf, limit=self.candle_limit)
           
            if not df.empty and len(df) > 20:
                signal = self.analyze_timeframe(df)
               
                # เพิ่มผลลัพธ์สำหรับกรอบเวลานี้
                results["timeframes"][tf] = {
                    "signal": signal,
                    "candle_count": len(df),
                    "last_close": float(df['close'].iloc[-1]),
                    "last_timestamp": df['timestamp'].iloc[-1].isoformat()
                }
               
                # นับสัญญาณ
                results["signals_count"][signal] += 1
               
                self.console.print(f"[{'green' if signal == 'LONG' else 'red' if signal == 'SHORT' else 'yellow'}]กรอบเวลา {tf}: {signal}[/{'green' if signal == 'LONG' else 'red' if signal == 'SHORT' else 'yellow'}]")
            else:
                self.console.print(f"[yellow]ไม่สามารถวิเคราะห์กรอบเวลา {tf} ได้เนื่องจากข้อมูลไม่เพียงพอ[/yellow]")
       
        # ตัดสินใจสัญญาณโดยรวม
        long_count = results["signals_count"]["LONG"]
        short_count = results["signals_count"]["SHORT"]
        hold_count = results["signals_count"]["HOLD"]
       
        # คำนวณความเชื่อมั่น
        total_timeframes = len(results["timeframes"])
        if total_timeframes > 0:
            long_confidence = (long_count / total_timeframes) * 100
            short_confidence = (short_count / total_timeframes) * 100
            hold_confidence = (hold_count / total_timeframes) * 100
           
            results["confidence"] = {
                "LONG": long_confidence,
                "SHORT": short_confidence,
                "HOLD": hold_confidence
            }
       
        # ตัดสินใจสัญญาณสุดท้าย
        final_signal = "HOLD"
        if long_count > short_count and long_count > hold_count:
            final_signal = "LONG"
        elif short_count > long_count and short_count > hold_count:
            final_signal = "SHORT"
       
        results["final_signal"] = final_signal
       
        # แสดงสรุปผล
        self.console.print(f"\n[bold magenta]===== สรุปการวิเคราะห์ {symbol} =====[/bold magenta]")
        self.console.print(f"จำนวนกรอบเวลาที่แนะนำ LONG: {long_count}")
        self.console.print(f"จำนวนกรอบเวลาที่แนะนำ SHORT: {short_count}")
        self.console.print(f"จำนวนกรอบเวลาที่แนะนำ HOLD: {hold_count}")
       
        signal_color = "green" if final_signal == "LONG" else "red" if final_signal == "SHORT" else "yellow"
        self.console.print(f"[bold {signal_color}]สัญญาณสุดท้าย: {final_signal}[/bold {signal_color}]")
        
        # ดำเนินการซื้อขายหากเปิดใช้งาน
        if trade:
            # ตรวจสอบ position ที่มีอยู่
            existing_position = self.check_existing_position(symbol)
            
            # ถ้ามี position อยู่แล้ว
            if existing_position:
                current_position_type = existing_position['type']
                
                # ตรวจสอบว่าควรปิด position หรือไม่
                should_close = False
                
                # กรณี position เป็น LONG แต่สัญญาณเป็น SHORT
                if current_position_type == "LONG" and final_signal == "SHORT":
                    self.console.print(f"[yellow]⚠️ มี LONG position อยู่ แต่สัญญาณแนะนำ SHORT[/yellow]")
                    should_close = True
                
                # กรณี position เป็น SHORT แต่สัญญาณเป็น LONG
                elif current_position_type == "SHORT" and final_signal == "LONG":
                    self.console.print(f"[yellow]⚠️ มี SHORT position อยู่ แต่สัญญาณแนะนำ LONG[/yellow]")
                    should_close = True
                
                # กรณี position เป็น LONG/SHORT แต่สัญญาณเป็น HOLD
                elif final_signal == "HOLD":
                    self.console.print(f"[yellow]⚠️ มี {current_position_type} position อยู่ แต่สัญญาณแนะนำ HOLD[/yellow]")
                    should_close = True
                
                # ปิด position ถ้าควรปิด
                if should_close:
                    self.console.print(f"[yellow]🔔 กำลังปิด {current_position_type} position ตามสัญญาณ[/yellow]")
                    if self.close_position(symbol, existing_position):
                        existing_position = None  # รีเซ็ต position
                else:
                    self.console.print(f"[blue]ยังคง {current_position_type} position ตามสัญญาณ[/blue]")
            
            # เปิด position ใหม่ถ้าไม่มี position หรือปิด position เดิมไปแล้ว
            if not existing_position:
                if final_signal == "LONG":
                    self.console.print(f"[green]🆕 กำลังเปิด LONG position ตามสัญญาณ[/green]")
                    self.create_order(symbol, True)  # เปิด LONG
                elif final_signal == "SHORT":
                    self.console.print(f"[red]🆕 กำลังเปิด SHORT position ตามสัญญาณ[/red]")
                    self.create_order(symbol, False)  # เปิด SHORT
                elif final_signal == "HOLD":
                    self.console.print(f"[blue]ไม่เปิด position ใดๆ ตามสัญญาณ HOLD[/blue]")
       
        return final_signal, results


# เริ่มระบบเทรดอัตโนมัติทันที
if __name__ == "__main__":
    try:
        print("เริ่มระบบเทรดอัตโนมัติ GateIO...")
        analyzer = GateIOTradingAnalyzer()
        analyzer.console.print("[bold green]ระบบเทรดอัตโนมัติพร้อมทำงาน[/bold green]")
        analyzer.console.print("[bold yellow]กำลังเริ่มต้นการทำงานแบบต่อเนื่อง...[/bold yellow]")
        analyzer.scan_market()  # เรียกใช้ scan_market() ที่ทำงานต่อเนื่อง
    except KeyboardInterrupt:
        print("\nโปรแกรมถูกหยุดโดยผู้ใช้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดร้ายแรง: {str(e)}")
        sys.exit(1)