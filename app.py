import os
import time
import re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console
class GateIOSwingTradeScanner:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key:
            raise ValueError("API keys missing")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5
        self.order_amount = 50
        self.lookback_period = 100
        self.devlen = 2.0
        self.console = Console()
    def get_futures_contracts(self) -> List[str]:
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = []
        pattern = re.compile(r'^\D+_USDT$')
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                json_data = contract.to_dict()
                if float(json_data['volume_24h']) * float(json_data['last']) > 500000:
                    valid_contracts.append(contract.contract)
        self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา[/blue]")
        return valid_contracts
    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
        if not candles:
            return pd.DataFrame()
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')
    def calculate_linear_regression(self, src: np.ndarray) -> tuple:
        """ฟังก์ชันคำนวณ Linear Regression Channel ตามสูตร TradingView"""
        length = len(src)
        if length < 3:  # ต้องมีข้อมูลอย่างน้อย 3 จุด
            return None, None, None, None
        x = np.arange(length)
        # คำนวณค่าเฉลี่ย
        mid = np.sum(src) / length
        # คำนวณค่า linear regression
        sum_x = np.sum(x)
        sum_y = np.sum(src)
        sum_xy = np.sum(x * src)
        sum_x2 = np.sum(x * x)
        slope = (length * sum_xy - sum_x * sum_y) / (length * sum_x2 - sum_x * sum_x)
        intercept = (sum_y - slope * sum_x) / length
        # คำนวณจุดสิ้นสุด
        endy = intercept + slope * (length - 1)
        # คำนวณค่าเบี่ยงเบนมาตรฐาน
        dev = 0.0
        for i in range(length):
            y_pred = slope * i + intercept
            dev += (src[i] - y_pred) ** 2
        dev = np.sqrt(dev / length)
        return intercept, endy, dev, slope
    def calculate_linear_regression_channel(self, contract: str, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.lookback_period:
            return pd.DataFrame()
        # ใช้ข้อมูลล่าสุดตามจำนวน lookback_period
        recent_data = df['close'].iloc[-self.lookback_period:].values
        # คำนวณ Linear Regression Channel
        intercept, endy, dev, slope = self.calculate_linear_regression(recent_data)
        if intercept is None:
            return pd.DataFrame()
        result_df = df.tail(1).copy()
        # จุดกึ่งกลางของ channel คือค่า y ล่าสุดจาก linear regression
        result_df['MIDDLE'] = endy
        # จุดบนและล่างของ channel
        result_df['TOP'] = endy + dev * self.devlen
        result_df['BOTTOM'] = endy - dev * self.devlen
        # จุดกึ่งกลางระหว่าง TOP กับ MIDDLE และ MIDDLE กับ BOTTOM
        result_df['TMID'] = (result_df['TOP'] + result_df['MIDDLE']) / 2
        result_df['BMID'] = (result_df['MIDDLE'] + result_df['BOTTOM']) / 2
        self.console.print(f"[cyan]{contract}[/cyan] slope={slope:.6f}, dev={dev:.6f} "
                        f"TOP={result_df['TOP'].iloc[-1]:.6f}, BOTTOM={result_df['BOTTOM'].iloc[-1]:.6f}, "
                        f"MIDDLE={result_df['MIDDLE'].iloc[-1]:.6f}")
        return result_df
    def check_trading_signal(self, df: pd.DataFrame) -> str:
        if len(df) < 1:
            return None
        candle = df.iloc[-1]
        is_green = candle['close'] > candle['open']
        is_red = candle['close'] < candle['open']
        # แท่งเทียนทับเส้นบน = high > TOP
        high_above_top = candle['high'] > candle['TOP']
        # แท่งเทียนทับเส้นล่าง = low < BOTTOM
        low_below_bottom = candle['low'] < candle['BOTTOM']
        if is_green and high_above_top:
            self.console.print(f"[green]สัญญาณ BUY: CANDLE สีเขียว (close={candle['close']:.6f} > open={candle['open']:.6f}) "
                            f"และ high={candle['high']:.6f} > TOP={candle['TOP']:.6f}[/green]")
            return "BUY"
        elif is_red and low_below_bottom:
            self.console.print(f"[red]สัญญาณ SELL: CANDLE สีแดง (close={candle['close']:.6f} < open={candle['open']:.6f}) "
                            f"และ low={candle['low']:.6f} < BOTTOM={candle['BOTTOM']:.6f}[/red]")
            return "SELL"
        return None
    def set_leverage(self, contract: str) -> bool:
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            self.console.print(f"[yellow]ตั้งค่า leverage {self.leverage}x สำหรับ {contract}[/yellow]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถตั้งค่า leverage สำหรับ {contract}: {str(e)}[/red]")
            return False
    def get_latest_price(self, contract: str) -> float:
        ticker = self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract == contract:
                price = float(t.last)
                return price
        self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
        return None
    def check_existing_position(self, contract: str) -> Dict:
        positions = self.futures_api.list_positions(settle='usdt', holding=True)
        for p in positions:
            if p.contract == contract:
                position_info = p.to_dict()
                size = float(position_info['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                self.console.print(f"[yellow]พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                return position_info
        return None
    def close_position(self, contract: str, position: Dict) -> bool:
        try:
            size = float(position['size'])
            if size != 0:
                direction = abs(size) if size < 0 else -size
                self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': direction, 'price': 0, 'tif': 'ioc', 'reduce_only': True})
                position_type = "LONG" if size > 0 else "SHORT"
                self.console.print(f"[yellow]ปิด position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                return True
            return False
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถปิด position สำหรับ {contract}: {str(e)}[/red]")
            return False
    def create_long_order(self, contract: str) -> Dict:
        try:
            if not self.set_leverage(contract):
                return None
            price = self.get_latest_price(contract)
            if not price:
                return None
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': size, 'price': 0, 'tif': 'ioc', 'reduce_only': False})
            self.console.print(f"[green]เปิด position LONG: {contract} ขนาด={size}[/green]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด LONG สำหรับ {contract}: {str(e)}[/red]")
            return None
    def create_short_order(self, contract: str) -> Dict:
        try:
            if not self.set_leverage(contract):
                return None
            price = self.get_latest_price(contract)
            if not price:
                return None
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': -size, 'price': 0, 'tif': 'ioc', 'reduce_only': False})
            self.console.print(f"[red]เปิด position SHORT: {contract} ขนาด={size}[/red]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด SHORT สำหรับ {contract}: {str(e)}[/red]")
            return None
    def scan_positions(self):
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]สแกน {len(positions)} positions ที่เปิดอยู่[/blue]")
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df = self.calculate_linear_regression_channel(contract, df)
                    if not df.empty:
                        latest_price = self.get_latest_price(contract)
                        if latest_price:
                            tmid = df['TMID'].iloc[-1]
                            bmid = df['BMID'].iloc[-1]
                            size = float(pos['size'])
                            if size > 0 and latest_price < tmid:
                                self.console.print(f"[yellow]ปิด LONG position: {contract} เนื่องจากราคาล่าสุด={latest_price:.6f} < TMID={tmid:.6f}[/yellow]")
                                self.close_position(contract, pos)
                            elif size < 0 and latest_price > bmid:
                                self.console.print(f"[yellow]ปิด SHORT position: {contract} เนื่องจากราคาล่าสุด={latest_price:.6f} > BMID={bmid:.6f}[/yellow]")
                                self.close_position(contract, pos)
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน positions: {str(e)}[/red]")
    def scan_market(self):
        first_run = True
        while True:
            current_time = pd.Timestamp.now(tz='Asia/Bangkok')
            if current_time.minute % 15 == 0 or first_run:
                self.console.print(f"[blue]เริ่มสแกนตลาด ณ เวลา {current_time}[/blue]")
                first_run = False
                self.scan_positions()
                contracts = self.get_futures_contracts()
                for contract in contracts:
                    df = self.get_candlesticks(contract)
                    if not df.empty:
                        df = self.calculate_linear_regression_channel(contract, df)
                        if not df.empty:
                            signal = self.check_trading_signal(df)
                            existing_pos = self.check_existing_position(contract)
                            if signal == "BUY":
                                if existing_pos and float(existing_pos['size']) < 0:
                                    if self.close_position(contract, existing_pos):
                                        self.create_long_order(contract)
                                elif not existing_pos:
                                    self.create_long_order(contract)
                            elif signal == "SELL":
                                if existing_pos and float(existing_pos['size']) > 0:
                                    if self.close_position(contract, existing_pos):
                                        self.create_short_order(contract)
                                elif not existing_pos:
                                    self.create_short_order(contract)
                time.sleep(30)
            if current_time.minute % 3 == 0:
                if current_time.minute % 15 == 0:
                    first_run = True
                else:
                    self.scan_positions()
                    time.sleep(60)
            time.sleep(10)
def main():
    scanner = GateIOSwingTradeScanner()
    scanner.console.print("[blue]เริ่มต้นระบบสแกนตลาด Futures ด้วย Linear Regression Channel...[/blue]")
    scanner.scan_market()
if __name__ == "__main__":
    main()