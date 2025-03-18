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
        self.profit_target = 0.02 
        self.stop_loss = 0.01     
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
        length = len(src)
        if length < 3:
            return None, None, None, None
        mid = np.sum(src) / length
        x = np.arange(length)
        slope = np.cov(x, src)[0, 1] / np.var(x)
        intercept = mid - slope * (length - 1) / 2
        endy = intercept + slope * (length - 1)
        dev = 0.0
        for i in range(length):
            y_pred = slope * i + intercept
            dev += (src[i] - y_pred) ** 2
        dev = np.sqrt(dev / length)
        return intercept, endy, dev, slope
    
    def calculate_linear_regression_channel(self, contract: str, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.lookback_period:
            return pd.DataFrame()
        recent_data = df['close'].iloc[-self.lookback_period:].values
        intercept, endy, dev, slope = self.calculate_linear_regression(recent_data)
        if intercept is None:
            return pd.DataFrame()
        result_df = df.tail(2).copy()
        if 'MIDDLE' not in result_df.columns:
            result_df['MIDDLE'] = np.nan
            result_df['TOP'] = np.nan
            result_df['BOTTOM'] = np.nan
        for i in range(len(result_df)):
            idx = self.lookback_period - 2 + i
            y_val = intercept + slope * idx
            result_df.iloc[i, result_df.columns.get_loc('MIDDLE')] = y_val
            result_df.iloc[i, result_df.columns.get_loc('TOP')] = y_val + dev * self.devlen
            result_df.iloc[i, result_df.columns.get_loc('BOTTOM')] = y_val - dev * self.devlen
        self.console.print(f"[cyan]{contract}[/cyan] slope={slope:.6f}, dev={dev:.6f} TOP={result_df['TOP'].iloc[-1]:.6f}, BOTTOM={result_df['BOTTOM'].iloc[-1]:.6f}, MIDDLE={result_df['MIDDLE'].iloc[-1]:.6f}")
        return result_df
    
    def check_trading_signal(self, df: pd.DataFrame) -> str:
        if len(df) < 2:
            return None
        current_candle = df.iloc[-1]
        previous_candle = df.iloc[-2]
        is_green = current_candle['close'] > current_candle['open']
        is_red = current_candle['close'] < current_candle['open']
        buy_signal = (is_green and current_candle['low'] <= current_candle['BOTTOM'] and previous_candle['low'] < previous_candle['BOTTOM'])
        sell_signal = (is_red and current_candle['high'] >= current_candle['TOP'] and previous_candle['high'] > previous_candle['TOP'])
        if buy_signal:
            self.console.print(f"[green]สัญญาณ BUY: CANDLE สีเขียว (close={current_candle['close']:.6f} > open={current_candle['open']:.6f}) และ low={current_candle['low']:.6f} <= BOTTOM={current_candle['BOTTOM']:.6f} และแท่งก่อนหน้า low={previous_candle['low']:.6f} < BOTTOM={previous_candle['BOTTOM']:.6f}[/green]")
            return "BUYX"
        elif sell_signal:
            self.console.print(f"[red]สัญญาณ SELL: CANDLE สีแดง (close={current_candle['close']:.6f} < open={current_candle['open']:.6f}) และ high={current_candle['high']:.6f} >= TOP={current_candle['TOP']:.6f} และแท่งก่อนหน้า high={previous_candle['high']:.6f} > TOP={previous_candle['TOP']:.6f}[/red]")
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
                entry_price = float(position_info['entry_price'])
                self.console.print(f"[yellow]พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}, ราคาเข้า={entry_price}[/yellow]")
                return position_info
        return None
    
    def close_position(self, contract: str, position: Dict) -> bool:
        try:
            size = float(position['size'])
            if size != 0:
                direction = abs(size) if size < 0 else -size
                self.futures_api.create_futures_order('usdt', {
                    'contract': contract,
                    'size': direction,
                    'price': 0,
                    'tif': 'ioc',
                    'reduce_only': True
                })
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
            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract,
                'size': size,
                'price': 0,
                'tif': 'ioc',
                'reduce_only': False
            })
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
            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract,
                'size': -size,
                'price': 0,
                'tif': 'ioc',
                'reduce_only': False
            })
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
                entry_price = float(pos['entry_price'])
                current_price = self.get_latest_price(contract)
                if not current_price:
                    continue
                df = self.get_candlesticks(contract)
                if df.empty:
                    continue
                latest_candle = df.iloc[-1]
                is_green = latest_candle['close'] > latest_candle['open']
                is_red = latest_candle['close'] < latest_candle['open']
                size = float(pos['size'])
                if size > 0:  # Long position
                    pnl_percent = (current_price / entry_price - 1)
                    if pnl_percent >= self.profit_target and is_red:
                        self.console.print(f"[yellow]ปิด LONG position: {contract} เนื่องจาก PnL = {pnl_percent:.2%} และแท่งเทียนเป็นสีแดง[/yellow]")
                        self.close_position(contract, pos)
                    elif pnl_percent <= -self.stop_loss:
                        self.console.print(f"[yellow]ปิด LONG position: {contract} เนื่องจาก PnL = {pnl_percent:.2%} ขาดทุนเกินเกณฑ์[/yellow]")
                        self.close_position(contract, pos)
                elif size < 0:  # Short position
                    pnl_percent = (1 - current_price / entry_price)
                    if pnl_percent >= self.profit_target and is_green:
                        self.console.print(f"[yellow]ปิด SHORT position: {contract} เนื่องจาก PnL = {pnl_percent:.2%} และแท่งเทียนเป็นสีเขียว[/yellow]")
                        self.close_position(contract, pos)
                    elif pnl_percent <= -self.stop_loss:
                        self.console.print(f"[yellow]ปิด SHORT position: {contract} เนื่องจาก PnL = {pnl_percent:.2%} ขาดทุนเกินเกณฑ์[/yellow]")
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
                        df_with_channels = self.calculate_linear_regression_channel(contract, df)
                        if not df_with_channels.empty:
                            signal = self.check_trading_signal(df_with_channels)
                            existing_pos = self.check_existing_position(contract)
                            if signal == "BUY":
                                if existing_pos and float(existing_pos['size']) < 0:  # มี SHORT position อยู่
                                    if self.close_position(contract, existing_pos):
                                        self.create_long_order(contract)
                                elif not existing_pos:  # ไม่มี position
                                    self.create_long_order(contract)
                            elif signal == "SELL":
                                if existing_pos and float(existing_pos['size']) > 0:  # มี LONG position อยู่
                                    if self.close_position(contract, existing_pos):
                                        self.create_short_order(contract)
                                elif not existing_pos:  # ไม่มี position
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