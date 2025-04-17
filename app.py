#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, time, re, sys
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console


class GateIOBreakdownTrader:
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
            
            # กำหนดพารามิเตอร์สำหรับการวิเคราะห์ตามเงื่อนไขใหม่
            self.t_lookback_frames = 144  # จำนวน timeframe ย้อนหลังสำหรับ T
            self.t_skip_recent_frames = 14  # จำนวน timeframe ล่าสุดที่ข้ามสำหรับ T
            self.s_lookback_frames = 14  # จำนวน timeframe ย้อนหลังสำหรับ S
            self.s_skip_recent_frames = 2  # จำนวน timeframe ล่าสุดที่ข้ามสำหรับ S
            
            # เปลี่ยนเงื่อนไขการปิด position เป็น 100%
            self.profit_take_percent = 100.0  # เปอร์เซ็นต์กำไรที่จะปิด position
            self.stop_loss_percent = 5.0  # เปอร์เซ็นต์ขาดทุนที่จะปิด position (ใช้ค่าเดิมไว้เผื่อต้องการใช้)
            
            self.console = Console()
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการเริ่มต้น: {str(e)}")
            sys.exit(1)


    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ"""
        try:
            ticket = self.futures_api.list_futures_tickers(settle='usdt')
            valid_contracts = [c.contract for c in ticket if re.match(r'^\D+_USDT$', c.contract) and c.contract not in ['USDC_USDT', 'DOGS_USDT'] and float(c.volume_24h) * float(c.last) > 500000]
            self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา[/blue]")
            return valid_contracts
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงรายชื่อสัญญา: {str(e)}[/red]")
            return []


    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนจาก API โดยใช้ timeframe 1 ชั่วโมง"""
        try:
            # ใช้ timeframe 1 ชั่วโมง
            candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='1h', limit=500)
            if not candles: return pd.DataFrame()
            data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            return df.sort_values('timestamp')
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงข้อมูลแท่งเทียน {contract}: {str(e)}[/red]")
            return pd.DataFrame()


    def calculate_breakdown(self, df: pd.DataFrame) -> dict:
        """คำนวณเงื่อนไข Breakdown ตามเงื่อนไขที่กำหนด"""
        try:
            # ตรวจสอบว่ามีข้อมูลเพียงพอหรือไม่
            if len(df) < self.t_lookback_frames:
                return {'is_breakdown': False}
            
            # ดึงแท่งเทียนล่าสุด
            latest_candle = df.iloc[-1]
            
            # T = แท่งเทียนย้อนหลังไป 144 time frame ถึงแท่งเทียนปัจจุบัน ลบ 14 time frame
            if len(df) < self.t_lookback_frames:
                # ถ้ามีข้อมูลไม่พอ ใช้ข้อมูลทั้งหมดที่มียกเว้น t_skip_recent_frames ล่าสุด
                t_period = df.iloc[:-self.t_skip_recent_frames]
            else:
                # ใช้ข้อมูลตามเงื่อนไขที่กำหนด
                t_period = df.iloc[-self.t_lookback_frames:-self.t_skip_recent_frames]
            
            # S = แท่งเทียนย้อนหลังไป 14 time frame ถึงแท่งเทียนปัจจุบัน ลบ 2 time frame
            if len(df) < self.s_lookback_frames:
                # ถ้ามีข้อมูลไม่พอ ใช้ข้อมูลทั้งหมดที่มียกเว้น s_skip_recent_frames ล่าสุด
                s_period = df.iloc[:-self.s_skip_recent_frames]
            else:
                # ใช้ข้อมูลตามเงื่อนไขที่กำหนด
                s_period = df.iloc[-self.s_lookback_frames:-self.s_skip_recent_frames]
            
            # หาราคาสูงสุดของช่วง T และ S และราคาต่ำสุดของ S
            t_high = t_period['high'].max()
            s_high = s_period['high'].max()
            s_low = s_period['low'].min()
            
            # เช็คว่าแท่งเทียนล่าสุดเป็นสีแดงหรือไม่ (close < open)
            is_red_candle = latest_candle['close'] < latest_candle['open']
            
            # BreakDown = ราคาสูงสุดของ Candle มากกว่า ราคาสูงสุดของ T และ
            # ราคาต่ำสุดของ Candle น้อยกว่า ราคาสูงสุดของ T และ
            # Candle เป็นสีแดง
            is_breakdown = (latest_candle['high'] > t_high) and (latest_candle['low'] < t_high) and is_red_candle
            
            return {
                'is_breakdown': is_breakdown,
                't_high': t_high,
                's_high': s_high,
                's_low': s_low,
                'candle_high': latest_candle['high'],
                'candle_low': latest_candle['low'],
                'is_red_candle': is_red_candle
            }
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการคำนวณ Breakdown: {str(e)}[/red]")
            return {'is_breakdown': False}


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


    def check_trading_signal(self, df: pd.DataFrame, breakdown_data: dict, contract: str = None) -> str:
        """ตรวจสอบสัญญาณการเทรดตามเงื่อนไข Breakdown"""
        try:
            if not breakdown_data: return None
            latest_price = self.get_latest_price(contract)
            if latest_price is None: return None
            
            # แสดงข้อมูลการวิเคราะห์
            if 't_high' in breakdown_data:
                candle_color = "🟥 สีแดง" if breakdown_data.get('is_red_candle', False) else "🟩 สีเขียว"
                self.console.print(f"[blue]   ตรวจสอบสัญญาณ: ราคาล่าสุด={latest_price:.6f}, T_High={breakdown_data['t_high']:.6f}, S_High={breakdown_data['s_high']:.6f}, S_Low={breakdown_data['s_low']:.6f}, Candle_High={breakdown_data['candle_high']:.6f}, Candle_Low={breakdown_data['candle_low']:.6f}, Candle={candle_color}[/blue]")
            
            # ตรวจสอบเงื่อนไข Breakdown และราคาปัจจุบันสูงกว่าราคาต่ำสุดของ S สำหรับสัญญาณ SELL
            if breakdown_data['is_breakdown'] and latest_price > breakdown_data['s_low']:
                self.console.print(f"[red]🔴 สัญญาณ SELL: พบ Breakdown pattern และราคาปัจจุบัน({latest_price:.6f}) > ราคาต่ำสุดของ S({breakdown_data['s_low']:.6f})[/red]")
                return "SELL"
            elif breakdown_data['is_breakdown']:
                self.console.print(f"[yellow]⚠️ พบ Breakdown pattern แต่ราคาปัจจุบัน({latest_price:.6f}) ไม่สูงกว่าราคาต่ำสุดของ S({breakdown_data['s_low']:.6f})[/yellow]")
            return None
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการตรวจสอบสัญญาณ: {str(e)}[/red]")
            return None


    def should_close_position(self, position: Dict, contract: str = None, breakdown_data: dict = None) -> bool:
        """ตรวจสอบเงื่อนไขปิด position ตามเปอร์เซ็นต์กำไร หรือเมื่อราคาสูงกว่าราคาสูงสุดของ S"""
        try:
            latest_price = self.get_latest_price(contract)
            if latest_price is None: return False
            
            size = float(position['size'])
            entry_price = float(position['entry_price'])
            
            if size < 0:  # SHORT position
                # คำนวณ P&L เป็นเปอร์เซ็นต์สำหรับ SHORT
                pnl_percentage = ((entry_price - latest_price) / entry_price * 100)
                
                # เงื่อนไขปิด position ตามข้อกำหนดใหม่: กำไรเกิน 100% หรือราคาสูงกว่า S_high
                if pnl_percentage >= self.profit_take_percent:
                    self.console.print(f"[green]🟡 เข้าเงื่อนไขปิด SHORT: กำไร {pnl_percentage:.2f}% เกินกว่า {self.profit_take_percent}%[/green]")
                    return True
                elif breakdown_data is not None and 's_high' in breakdown_data and latest_price > breakdown_data['s_high']:
                    self.console.print(f"[yellow]🟡 เข้าเงื่อนไขปิด SHORT: ราคาล่าสุด {latest_price:.6f} สูงกว่าราคาสูงสุดของ S {breakdown_data['s_high']:.6f}[/yellow]")
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
        """สแกน positions ที่เปิดอยู่เพื่อทำการปิดตามเงื่อนไขกำไร/ขาดทุนที่กำหนด"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            positions_checked, positions_closed = 0, 0
            
            # สร้าง dictionary เพื่อเก็บข้อมูล breakdown ของแต่ละสัญญา
            breakdown_data_values = {}
            
            # ดึงข้อมูลแท่งเทียนและคำนวณ breakdown data สำหรับแต่ละสัญญาที่มี position
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                if not df.empty:
                    breakdown_data = self.calculate_breakdown(df)
                    if breakdown_data:
                        breakdown_data_values[contract] = breakdown_data
            
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
                
                # ตรวจสอบเงื่อนไขการปิด position ตามกำไรและราคาเทียบกับ s_high
                breakdown_data = breakdown_data_values.get(contract, None)
                close_position = self.should_close_position(pos, contract, breakdown_data)
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
        stats = {'contracts_scanned': 0, 'sell_signals': 0, 'short_opened': 0, 'positions_closed': 0}
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                if current_time.minute % 5 == 0:  
                    if current_time.minute == 0:
                        first_run = True
                    else:
                        self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                        scan_stats = {'positions_closed': 0}
                        scan_stats['positions_closed'] = self.scan_positions()
                        time.sleep(60)
                        
                    
                if current_time.minute == 0 or first_run:  # สแกนทุกชั่วโมงเต็ม หรือครั้งแรกที่เริ่มโปรแกรม
                    self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    first_run = False
                    scan_stats = {'contracts_scanned': 0, 'sell_signals': 0, 'short_opened': 0, 'positions_closed': 0}
                    
                    # ตรวจสอบ Positions ที่มีอยู่
                    self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                    scan_stats['positions_closed'] = self.scan_positions()
                    
                    # ตรวจหาสัญญาณเทรดใหม่
                    self.console.print(f"[blue]📊 ตรวจหาสัญญาณเทรดใหม่[/blue]")
                    contracts = self.get_futures_contracts()
                    for i, contract in enumerate(contracts, 1):
                        self.console.print(f"[cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract}[/cyan]")
                        df = self.get_candlesticks(contract)
                        if df.empty:
                            self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                            continue
                            
                        breakdown_data = self.calculate_breakdown(df)
                        if not breakdown_data:
                            self.console.print(f"[red]❌ ไม่สามารถคำนวณ Breakdown สำหรับ {contract} ได้[/red]")
                            continue
                            
                        latest_price = self.get_latest_price(contract)
                        self.console.print(f"[magenta]   Breakdown Data:[/magenta]")
                        if 't_high' in breakdown_data:
                            candle_color = "🟥 สีแดง" if breakdown_data.get('is_red_candle', False) else "🟩 สีเขียว"
                            self.console.print(f"[magenta]   T_High={breakdown_data['t_high']:.6f}, S_High={breakdown_data['s_high']:.6f}, S_Low={breakdown_data['s_low']:.6f}, Candle_High={breakdown_data['candle_high']:.6f}, Candle_Low={breakdown_data['candle_low']:.6f}, ราคาล่าสุด={latest_price:.6f}, Candle={candle_color}[/magenta]")
                        
                        # แสดงข้อมูลแท่งเทียนล่าสุด
                        if len(df) >= 2:
                            latest_candle = df.iloc[-1]
                            candle_type = "สีเขียว 🟩" if latest_candle['close'] > latest_candle['open'] else "สีแดง 🟥" if latest_candle['close'] < latest_candle['open'] else "Doji ⬛"
                            self.console.print(f"[magenta]   แท่งเทียนล่าสุด: {candle_type} - O: {latest_candle['open']:.6f}, H: {latest_candle['high']:.6f}, L: {latest_candle['low']:.6f}, C: {latest_candle['close']:.6f}[/magenta]")
                        
                        signal = self.check_trading_signal(df, breakdown_data, contract)
                        if signal:
                            # เราสนใจเฉพาะสัญญาณ SELL ตามโจทย์
                            if signal == "SELL":
                                scan_stats['sell_signals'] += 1
                                # ตรวจสอบ position ที่มีอยู่
                                existing_position = self.check_existing_position(contract)
                                
                                if existing_position:
                                    if existing_position['type'] == "SHORT":
                                        # มี SHORT อยู่แล้ว ไม่ทำอะไร
                                        self.console.print(f"[yellow]⚠️ มี SHORT position อยู่แล้ว ไม่เปิดเพิ่ม[/yellow]")
                                    else:  # มี LONG อยู่
                                        self.console.print(f"[yellow]🔄 มี LONG position อยู่ แต่เราต้องการ SHORT ตามสัญญาณ SELL[/yellow]")
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
                    self.console.print(f"[blue]📊 สัญญาที่สแกน: {scan_stats['contracts_scanned']}/{len(contracts)}[/blue]")
                    self.console.print(f"[red]📉 สัญญาณ SELL: {scan_stats['sell_signals']}[/red]")
                    self.console.print(f"[red]📉 เปิด SHORT: {scan_stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position: {scan_stats['positions_closed']}[/yellow]")
                    
                    # แสดงสถิติรวมทั้งหมด
                    self.console.print(f"[blue]===== สถิติรวมทั้งหมด =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกนทั้งหมด: {stats['contracts_scanned']}[/blue]")
                    self.console.print(f"[red]📉 สัญญาณ SELL ทั้งหมด: {stats['sell_signals']}[/red]")
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
        trader = GateIOBreakdownTrader()
        trader.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย Breakdown Strategy...[/blue]")
        trader.scan_market()
    except KeyboardInterrupt:
        print("\nโปรแกรมถูกหยุดโดยผู้ใช้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดร้ายแรง: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()