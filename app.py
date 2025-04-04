import os, time, re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console

class GateIORSITrader:
    def __init__(self):
        load_dotenv()
        self.api_key, self.secret_key = os.getenv('GATEIO_API_KEY'), os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client, self.futures_api = ApiClient(config), FuturesApi(ApiClient(config))
        self.leverage, self.order_amount, self.rsi_period, self.rsi_overbought = 5, 20, 14, 75
        self.console = Console()

    def get_futures_contracts(self) -> List[str]:
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = [c.contract for c in ticket if re.match(r'^\D+_USDT$', c.contract) and c.contract not in ['USDC_USDT', 'DOGS_USDT'] and float(c.volume_24h) * float(c.last) > 100000]
        self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา[/blue]")
        return valid_contracts

    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
        if not candles: return pd.DataFrame()
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')

    def calculate_rsi(self, df: pd.DataFrame) -> pd.Series:
        if len(df) < self.rsi_period + 1: return pd.Series()
        delta = df['close'].diff()
        gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
        avg_gain, avg_loss = gain.rolling(window=self.rsi_period).mean(), loss.rolling(window=self.rsi_period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def get_latest_price(self, contract: str) -> float:
        for t in self.futures_api.list_futures_tickers(settle='usdt'):
            if t.contract == contract: return float(t.last)
        self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
        return None

    def check_trading_signal(self, df: pd.DataFrame, contract: str = None) -> str:
        if len(df) < self.rsi_period + 1: return None
        rsi = self.calculate_rsi(df)
        latest_rsi = rsi.iloc[-1]
        self.console.print(f"[blue]   ตรวจสอบสัญญาณ: RSI={latest_rsi:.2f}[/blue]")
        if latest_rsi > self.rsi_overbought:
            self.console.print(f"[red]🔴 สัญญาณ SELL: RSI ({latest_rsi:.2f}) สูงกว่า {self.rsi_overbought}[/red]")
            return "SELL"
        return None

    def check_existing_position(self, contract: str) -> Dict:
        for p in self.futures_api.list_positions(settle='usdt', holding=True):
            if p.contract == contract:
                pos_info = p.to_dict()
                size = float(pos_info['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                self.console.print(f"[yellow]พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                return pos_info
        return None

    def set_leverage(self, contract: str) -> bool:
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            self.console.print(f"[yellow]ตั้งค่า leverage {self.leverage}x สำหรับ {contract}[/yellow]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถตั้งค่า leverage สำหรับ {contract}: {str(e)}[/red]")
            return False

    def close_position(self, contract: str, position: Dict) -> bool:
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
        try:
            if not self.set_leverage(contract): return None
            price = self.get_latest_price(contract)
            if not price: return None
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier, min_size = float(contract_info.to_dict()['quanto_multiplier']), float(contract_info.to_dict()['order_size_min'])
            size = max(min_size, round(self.order_amount * self.leverage / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': size if is_long else -size, 'price': 0, 'tif': 'ioc', 'reduce_only': False})
            position_type = "LONG" if is_long else "SHORT"
            self.console.print(f"[{'green' if is_long else 'red'}]✅ เปิด position {position_type}: {contract} ขนาด={size}[/{'green' if is_long else 'red'}]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด {'LONG' if is_long else 'SHORT'} สำหรับ {contract}: {str(e)}[/red]")
            return None

    def scan_positions(self):
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            positions_checked, positions_closed = 0, 0
            for pos in positions:
                contract, size = pos['contract'], float(pos['size'])
                if size >= 0: continue  # เราสนใจแค่ SHORT position
                entry_price = float(pos['entry_price'])
                self.console.print(f"[cyan]▶ ตรวจสอบ: {contract} (SHORT 📉) - ราคาเข้า: {entry_price:.6f} - ขนาด: {abs(size)}[/cyan]")
                latest_price = self.get_latest_price(contract)
                if not latest_price:
                    self.console.print(f"[red]❌ ไม่สามารถดึงราคาล่าสุดของ {contract} ได้[/red]")
                    continue
                pnl_percentage = ((entry_price - latest_price) / entry_price) * 100
                self.console.print(f"[{'green' if pnl_percentage > 0 else 'red'}]   P&L: {pnl_percentage:.2f}%[/{'green' if pnl_percentage > 0 else 'red'}]")
                if pnl_percentage > 1.5 or pnl_percentage < -1.0:
                    close_reason = "กำไร > 1.5%" if pnl_percentage > 1.5 else "ขาดทุน > 1.0%"
                    self.console.print(f"[yellow]🔔 เข้าเงื่อนไขปิด SHORT: {close_reason} ({pnl_percentage:.2f}%)[/yellow]")
                    if self.close_position(contract, pos): positions_closed += 1
                else: self.console.print(f"[blue]   ยังไม่เข้าเงื่อนไขการปิด position[/blue]")
                positions_checked += 1
            self.console.print(f"[blue]สรุป: ตรวจสอบ {positions_checked}/{len(positions)}, ปิด {positions_closed} positions[/blue]")
            return positions_closed
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน positions: {str(e)}[/red]")
            return 0

    def scan_market(self):
        first_run, stats = True, {'contracts_scanned': 0, 'sell_signals': 0, 'short_opened': 0, 'positions_closed': 0}
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                if current_time.minute % 15 == 0 or first_run:
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
                        rsi = self.calculate_rsi(df)
                        if len(rsi) == 0:
                            self.console.print(f"[red]❌ ไม่สามารถคำนวณ RSI สำหรับ {contract} ได้[/red]")
                            continue
                        latest_price, latest_rsi = self.get_latest_price(contract), rsi.iloc[-1]
                        self.console.print(f"[magenta]   ค่า RSI ล่าสุด: {latest_rsi:.2f}, ราคาล่าสุด: {latest_price:.6f}[/magenta]")
                        signal = self.check_trading_signal(df, contract)
                        if signal == "SELL":
                            scan_stats['sell_signals'] += 1
                            existing_position = self.check_existing_position(contract)
                            if not existing_position:
                                self.console.print(f"[yellow]🆕 เปิด SHORT position ตามสัญญาณ SELL[/yellow]")
                                if self.create_order(contract, False): scan_stats['short_opened'] += 1
                            else: self.console.print(f"[yellow]⚠️ มี position อยู่แล้ว ไม่สามารถเปิด SHORT ได้[/yellow]")
                        else: self.console.print(f"[blue]   ไม่พบสัญญาณเทรด[/blue]")
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
            except Exception as e:
                self.console.print(f"[red]❌ เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}[/red]")
                time.sleep(60)

def main():
    trader = GateIORSITrader()
    trader.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย RSI Strategy...[/blue]")
    trader.scan_market()

if __name__ == "__main__": main()
