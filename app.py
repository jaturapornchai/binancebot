import os, time, re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console

class GateIOEMATrader:
    def __init__(self):
        load_dotenv()
        self.api_key, self.secret_key = os.getenv('GATEIO_API_KEY'), os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client, self.futures_api = ApiClient(config), FuturesApi(ApiClient(config))
        self.leverage, self.order_amount = 5, 20
        self.console = Console()

    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ"""
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = [c.contract for c in ticket if re.match(r'^\D+_USDT$', c.contract) and c.contract not in ['USDC_USDT', 'DOGS_USDT'] and float(c.volume_24h) * float(c.last) > 100000]
        self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา[/blue]")
        return valid_contracts

    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนจาก API"""
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
        if not candles: return pd.DataFrame()
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')

    def calculate_ema(self, df: pd.DataFrame) -> dict:
        """คำนวณ EMA 5, 10, 30"""
        if len(df) < 30: return {}
        df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
        df['ema30'] = df['close'].ewm(span=30, adjust=False).mean()
        latest = df.iloc[-1]
        return {'ema5': latest['ema5'], 'ema10': latest['ema10'], 'ema30': latest['ema30'], 'close': latest['close'], 'open': latest['open']}

    def get_latest_price(self, contract: str) -> float:
        """ดึงราคาล่าสุดของสัญญา"""
        for t in self.futures_api.list_futures_tickers(settle='usdt'):
            if t.contract == contract: return float(t.last)
        self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
        return None

    def check_trading_signal(self, df: pd.DataFrame, ema_data: dict, contract: str = None) -> str:
        """ตรวจสอบสัญญาณการเทรดตาม EMA"""
        if not ema_data or len(df) < 2: return None
        is_green = ema_data['close'] > ema_data['open']
        is_red = ema_data['close'] < ema_data['open']
        buy_condition = (ema_data['ema5'] > ema_data['ema10']) and (ema_data['ema10'] > ema_data['ema30']) and (ema_data['close'] > ema_data['ema10']) and is_green
        sell_condition = (ema_data['ema5'] < ema_data['ema10']) and (ema_data['ema10'] < ema_data['ema30']) and (ema_data['close'] < ema_data['ema10']) and is_red
        
        self.console.print(f"[blue]   ตรวจสอบสัญญาณ: EMA5={ema_data['ema5']:.6f}, EMA10={ema_data['ema10']:.6f}, EMA30={ema_data['ema30']:.6f}[/blue]")
        self.console.print(f"[blue]   เงื่อนไข BUY: EMA5>EMA10={ema_data['ema5']>ema_data['ema10']}, EMA10>EMA30={ema_data['ema10']>ema_data['ema30']}, Close>EMA10={ema_data['close']>ema_data['ema10']}, เขียว={is_green}[/blue]")
        self.console.print(f"[blue]   เงื่อนไข SELL: EMA5<EMA10={ema_data['ema5']<ema_data['ema10']}, EMA10<EMA30={ema_data['ema10']<ema_data['ema30']}, Close<EMA10={ema_data['close']<ema_data['ema10']}, แดง={is_red}[/blue]")
        
        if buy_condition:
            self.console.print(f"[green]🟢 สัญญาณ BUY: EMA5>EMA10, EMA10>EMA30, ราคา>EMA10, แท่งเทียนเขียว[/green]")
            return "BUY"
        elif sell_condition:
            self.console.print(f"[red]🔴 สัญญาณ SELL: EMA5<EMA10, EMA10<EMA30, ราคา<EMA10, แท่งเทียนแดง[/red]")
            return "SELL"
        return None

    def check_existing_position(self, contract: str) -> Dict:
        """ตรวจสอบว่ามี position ที่เปิดอยู่หรือไม่"""
        for p in self.futures_api.list_positions(settle='usdt', holding=True):
            if p.contract == contract:
                pos_info = p.to_dict()
                size = float(pos_info['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                self.console.print(f"[yellow]พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                return pos_info
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
        """สแกน positions ที่เปิดอยู่เพื่อทำการปิดตามเงื่อนไข"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            positions_checked, positions_closed = 0, 0
            
            for pos in positions:
                contract, size = pos['contract'], float(pos['size'])
                if size == 0: continue
                position_type = "LONG 📈" if size > 0 else "SHORT 📉"
                entry_price = float(pos['entry_price'])
                self.console.print(f"[cyan]▶ ตรวจสอบ: {contract} ({position_type}) - ราคาเข้า: {entry_price:.6f} - ขนาด: {abs(size)}[/cyan]")
                
                latest_price = self.get_latest_price(contract)
                if not latest_price:
                    self.console.print(f"[red]❌ ไม่สามารถดึงราคาล่าสุดของ {contract} ได้[/red]")
                    continue
                
                # คำนวณ P&L เป็นเปอร์เซ็นต์
                pnl_percentage = ((latest_price - entry_price) / entry_price) * 100 if size > 0 else ((entry_price - latest_price) / entry_price) * 100
                self.console.print(f"[{'green' if pnl_percentage > 0 else 'red'}]   P&L: {pnl_percentage:.2f}%[/{'green' if pnl_percentage > 0 else 'red'}]")
                
                # ตรวจสอบเงื่อนไขกำไร/ขาดทุน (กำไรสูงกว่า 1.5% หรือ ขาดทุนมากกว่า 1%)
                close_position = (pnl_percentage > 1.5) or (pnl_percentage < -1.0)
                
                if close_position:
                    reason = "กำไร > 1.5%" if pnl_percentage > 1.5 else "ขาดทุน > 1.0%"
                    self.console.print(f"[yellow]🔔 เข้าเงื่อนไขปิด position: {reason}[/yellow]")
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
                        self.console.print(f"[magenta]   ข้อมูล EMA: EMA5={ema_data['ema5']:.6f}, EMA10={ema_data['ema10']:.6f}, EMA30={ema_data['ema30']:.6f}, Open={ema_data['open']:.6f}, Close={ema_data['close']:.6f}, ราคาล่าสุด={latest_price:.6f}[/magenta]")
                        
                        signal = self.check_trading_signal(df, ema_data, contract)
                        
                        if signal:
                            existing_position = self.check_existing_position(contract)
                            
                            if signal == "BUY":
                                scan_stats['buy_signals'] += 1
                                
                                # ถ้ามี SHORT position ให้ปิดก่อน
                                if existing_position and float(existing_position['size']) < 0:
                                    self.console.print(f"[yellow]🔄 ปิด SHORT position ก่อนเปิด LONG[/yellow]")
                                    self.close_position(contract, existing_position)
                                    existing_position = None
                                
                                # ถ้าไม่มี LONG position ให้เปิดใหม่
                                if not existing_position or float(existing_position['size']) <= 0:
                                    self.console.print(f"[green]🆕 เปิด LONG position ตามสัญญาณ BUY[/green]")
                                    if self.create_order(contract, True): scan_stats['long_opened'] += 1
                                else:
                                    self.console.print(f"[green]✅ มี LONG position อยู่แล้ว ไม่ต้องเปิดเพิ่ม[/green]")
                            
                            elif signal == "SELL":
                                scan_stats['sell_signals'] += 1
                                
                                # ถ้ามี LONG position ให้ปิดก่อน
                                if existing_position and float(existing_position['size']) > 0:
                                    self.console.print(f"[yellow]🔄 ปิด LONG position ก่อนเปิด SHORT[/yellow]")
                                    self.close_position(contract, existing_position)
                                    existing_position = None
                                
                                # ถ้าไม่มี SHORT position ให้เปิดใหม่
                                if not existing_position or float(existing_position['size']) >= 0:
                                    self.console.print(f"[red]🆕 เปิด SHORT position ตามสัญญาณ SELL[/red]")
                                    if self.create_order(contract, False): scan_stats['short_opened'] += 1
                                else:
                                    self.console.print(f"[red]✅ มี SHORT position อยู่แล้ว ไม่ต้องเปิดเพิ่ม[/red]")
                        else:
                            self.console.print(f"[blue]   ไม่พบสัญญาณเทรด[/blue]")
                        
                        scan_stats['contracts_scanned'] += 1
                    
                    # อัปเดตสถิติรวม
                    for key in stats: stats[key] += scan_stats[key]
                    
                    # แสดงสรุปการสแกน
                    self.console.print(f"[blue]===== สรุปการสแกนรอบนี้ =====\n📊 สัญญาที่สแกน: {scan_stats['contracts_scanned']}/{len(contracts)}\n[green]📈 สัญญาณ BUY: {scan_stats['buy_signals']}[/green]\n[red]📉 สัญญาณ SELL: {scan_stats['sell_signals']}[/red]\n[green]📈 เปิด LONG: {scan_stats['long_opened']}[/green]\n[red]📉 เปิด SHORT: {scan_stats['short_opened']}[/red]\n[yellow]🔄 ปิด Position: {scan_stats['positions_closed']}[/yellow][/blue]")
                    
                    # แสดงสถิติรวมทั้งหมด
                    self.console.print(f"[blue]===== สถิติรวมทั้งหมด =====\n📊 สัญญาที่สแกนทั้งหมด: {stats['contracts_scanned']}\n[green]📈 สัญญาณ BUY ทั้งหมด: {stats['buy_signals']}[/green]\n[red]📉 สัญญาณ SELL ทั้งหมด: {stats['sell_signals']}[/red]\n[green]📈 เปิด LONG ทั้งหมด: {stats['long_opened']}[/green]\n[red]📉 เปิด SHORT ทั้งหมด: {stats['short_opened']}[/red]\n[yellow]🔄 ปิด Position ทั้งหมด: {stats['positions_closed']}[/yellow][/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    
                    time.sleep(30)
                
                time.sleep(10)
            except Exception as e:
                self.console.print(f"[red]❌ เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}[/red]")
                time.sleep(60)


def main():
    trader = GateIOEMATrader()
    trader.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย EMA Crossover...[/blue]")
    trader.scan_market()


if __name__ == "__main__":
    main()