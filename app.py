#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, time, re, sys
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console

class GateIOEMACrossTrader:
    def __init__(self):
        try:
            load_dotenv(override=True)
            self.api_key = os.getenv('GATEIO_API_KEY') or os.environ.get('GATEIO_API_KEY')
            self.secret_key = os.getenv('GATEIO_SECRET_KEY') or os.environ.get('GATEIO_SECRET_KEY')
            if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env หรือ environment variables")
            config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
            self.client, self.futures_api = ApiClient(config), FuturesApi(ApiClient(config))
            self.leverage, self.order_amount = 5, 20
            self.ema_short, self.ema_long = 12, 26  # เปลี่ยนค่า EMA จาก 10,30 เป็น 12,26
            self.lookback_period = 14  # จำนวน timeframe ย้อนหลังสำหรับตรวจสอบราคาสูง/ต่ำสุด
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

    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนจาก API"""
        try:
            candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
            if not candles: return pd.DataFrame()
            data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            return df.sort_values('timestamp')
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงข้อมูลแท่งเทียน {contract}: {str(e)}[/red]")
            return pd.DataFrame()

    def calculate_ema(self, df: pd.DataFrame) -> dict:
        """คำนวณ EMA และตรวจสอบจุดตัด"""
        try:
            if len(df) < self.ema_long + 5: return {}
            df['ema_short'] = df['close'].ewm(span=self.ema_short, adjust=False).mean()
            df['ema_long'] = df['close'].ewm(span=self.ema_long, adjust=False).mean()
            current, previous = df.iloc[-1], df.iloc[-2]
            ema_short_current, ema_long_current = current['ema_short'], current['ema_long']
            ema_short_prev, ema_long_prev = previous['ema_short'], previous['ema_long']
            is_golden_cross = ema_short_prev < ema_long_prev and ema_short_current >= ema_long_current
            is_death_cross = ema_short_prev > ema_long_prev and ema_short_current <= ema_long_current
            return {'ema_short': ema_short_current, 'ema_long': ema_long_current, 'is_golden_cross': is_golden_cross, 'is_death_cross': is_death_cross}
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการคำนวณ EMA: {str(e)}[/red]")
            return {}

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

    def check_trading_signal(self, df: pd.DataFrame, ema_data: dict, contract: str = None) -> str:
        """ตรวจสอบสัญญาณการเทรดตามเงื่อนไข EMA Crossover"""
        try:
            if not ema_data: return None
            latest_price = self.get_latest_price(contract)
            if latest_price is None: return None
            self.console.print(f"[blue]   ตรวจสอบสัญญาณ: ราคาล่าสุด={latest_price:.6f}, EMA{self.ema_short}={ema_data['ema_short']:.6f}, EMA{self.ema_long}={ema_data['ema_long']:.6f}[/blue]")
            if ema_data['is_golden_cross']:
                self.console.print(f"[green]🟢 สัญญาณ BUY: EMA{self.ema_short} ตัดขึ้นเหนือ EMA{self.ema_long}[/green]")
                return "BUY"
            elif ema_data['is_death_cross']:
                self.console.print(f"[red]🔴 สัญญาณ SELL: EMA{self.ema_short} ตัดลงใต้ EMA{self.ema_long}[/red]")
                return "SELL"
            return None
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการตรวจสอบสัญญาณ: {str(e)}[/red]")
            return None

    def should_close_position(self, df: pd.DataFrame, position_type: str, contract: str = None) -> bool:
        """ตรวจสอบเงื่อนไขปิด position ตามช่วงราคาสูง/ต่ำสุดย้อนหลังและ EMA26"""
        try:
            if len(df) < self.lookback_period + 2: return False
            latest_price = self.get_latest_price(contract)
            if latest_price is None: return False
            
            # ข้อมูลย้อนหลังไม่รวม timeframe ปัจจุบัน
            lookback_data = df.iloc[-self.lookback_period-1:-1]
            
            # ค่า EMA26 ล่าสุด
            ema_long_current = df.iloc[-1]['ema_long']
            
            if position_type == "LONG":
                lowest_price = lookback_data['low'].min()
                current_candle_low = df.iloc[-1]['low']
                # เงื่อนไขปิด LONG: ราคาต่ำกว่าต่ำสุดย้อนหลัง หรือ ราคาล่าสุดต่ำกว่า EMA26
                if current_candle_low < lowest_price or latest_price < ema_long_current:
                    reason = "ราคาต่ำสุดปัจจุบัน < ราคาต่ำสุดย้อนหลัง" if current_candle_low < lowest_price else "ราคาล่าสุด < EMA26"
                    self.console.print(f"[yellow]🟡 เข้าเงื่อนไขปิด LONG: {reason}[/yellow]")
                    return True
            elif position_type == "SHORT":
                highest_price = lookback_data['high'].max()
                current_candle_high = df.iloc[-1]['high']
                # เงื่อนไขปิด SHORT: ราคาสูงกว่าสูงสุดย้อนหลัง หรือ ราคาล่าสุดสูงกว่า EMA26
                if current_candle_high > highest_price or latest_price > ema_long_current:
                    reason = "ราคาสูงสุดปัจจุบัน > ราคาสูงสุดย้อนหลัง" if current_candle_high > highest_price else "ราคาล่าสุด > EMA26"
                    self.console.print(f"[yellow]🟡 เข้าเงื่อนไขปิด SHORT: {reason}[/yellow]")
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
            position_type = "LONG" if is_long else "SHORT"
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': size if is_long else -size, 'price': 0, 'tif': 'ioc', 'reduce_only': False})
            self.console.print(f"[{'green' if is_long else 'red'}]✅ เปิด position {position_type}: {contract} ขนาด={size}[/{'green' if is_long else 'red'}]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด {'LONG' if is_long else 'SHORT'} สำหรับ {contract}: {str(e)}[/red]")
            return None

    def scan_positions(self):
        """สแกน positions ที่เปิดอยู่เพื่อทำการปิดตามเงื่อนไขใหม่"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            positions_checked, positions_closed = 0, 0
            
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
                
                # ดึงข้อมูลแท่งเทียน
                df = self.get_candlesticks(contract)
                if df.empty:
                    self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                    continue
                
                # คำนวณ EMA สำหรับตรวจสอบเงื่อนไขปิด position
                ema_data = self.calculate_ema(df)
                if not ema_data:
                    self.console.print(f"[red]❌ ไม่สามารถคำนวณ EMA สำหรับ {contract} ได้[/red]")
                    continue
                
                # ตรวจสอบเงื่อนไขการปิด position
                close_position = self.should_close_position(df, position_type, contract)
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
                if current_time.minute % 15 == 0 or first_run:
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
                        df = self.get_candlesticks(contract)
                        if df.empty:
                            self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                            continue
                            
                        ema_data = self.calculate_ema(df)
                        if not ema_data:
                            self.console.print(f"[red]❌ ไม่สามารถคำนวณ EMA สำหรับ {contract} ได้[/red]")
                            continue
                            
                        latest_price = self.get_latest_price(contract)
                        self.console.print(f"[magenta]   EMA Data: EMA{self.ema_short}={ema_data['ema_short']:.6f}, EMA{self.ema_long}={ema_data['ema_long']:.6f}, ราคาล่าสุด={latest_price:.6f}[/magenta]")
                        
                        # แสดงข้อมูลแท่งเทียนล่าสุด
                        if len(df) >= 2:
                            latest_candle = df.iloc[-1]
                            candle_type = "สีเขียว 🟩" if latest_candle['close'] > latest_candle['open'] else "สีแดง 🟥" if latest_candle['close'] < latest_candle['open'] else "Doji ⬛"
                            self.console.print(f"[magenta]   แท่งเทียนล่าสุด: {candle_type} - O: {latest_candle['open']:.6f}, H: {latest_candle['high']:.6f}, L: {latest_candle['low']:.6f}, C: {latest_candle['close']:.6f}[/magenta]")
                        
                        signal = self.check_trading_signal(df, ema_data, contract)
                        if signal:
                            # ตรวจสอบ position ที่มีอยู่
                            existing_position = self.check_existing_position(contract)
                            if signal == "BUY":
                                scan_stats['buy_signals'] += 1
                                if existing_position:
                                    if existing_position['type'] == "SHORT":
                                        self.console.print(f"[yellow]🔄 ปิด SHORT position ก่อนเปิด LONG ตามสัญญาณ BUY[/yellow]")
                                        if self.close_position(contract, existing_position['data']):
                                            scan_stats['positions_closed'] += 1
                                            self.console.print(f"[green]🆕 เปิด LONG position ตามสัญญาณ BUY[/green]")
                                            if self.create_order(contract, True):  # true คือ LONG
                                                scan_stats['long_opened'] += 1
                                    else:  # มี LONG อยู่แล้ว
                                        self.console.print(f"[yellow]⚠️ มี LONG position อยู่แล้ว ไม่เปิดเพิ่ม[/yellow]")
                                else:  # ไม่มี position
                                    self.console.print(f"[green]🆕 เปิด LONG position ตามสัญญาณ BUY[/green]")
                                    if self.create_order(contract, True):  # true คือ LONG
                                        scan_stats['long_opened'] += 1
                            elif signal == "SELL":
                                scan_stats['sell_signals'] += 1
                                if existing_position:
                                    if existing_position['type'] == "LONG":
                                        self.console.print(f"[yellow]🔄 ปิด LONG position ก่อนเปิด SHORT ตามสัญญาณ SELL[/yellow]")
                                        if self.close_position(contract, existing_position['data']):
                                            scan_stats['positions_closed'] += 1
                                            self.console.print(f"[red]🆕 เปิด SHORT position ตามสัญญาณ SELL[/red]")
                                            if self.create_order(contract, False):  # false คือ SHORT
                                                scan_stats['short_opened'] += 1
                                    else:  # มี SHORT อยู่แล้ว
                                        self.console.print(f"[yellow]⚠️ มี SHORT position อยู่แล้ว ไม่เปิดเพิ่ม[/yellow]")
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
        trader = GateIOEMACrossTrader()
        trader.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย EMA Crossover...[/blue]")
        trader.scan_market()
    except KeyboardInterrupt:
        print("\nโปรแกรมถูกหยุดโดยผู้ใช้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดร้ายแรง: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()