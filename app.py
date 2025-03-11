import os
import time
import re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi

class GateIOShortScanner:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys missing")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5
        self.order_amount = 20
        self.lookback_period = 100
        self.dev_multiplier = 2.0
        
    def get_futures_contracts(self) -> List[str]:
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = []
        pattern = re.compile(r'^\D+_USDT$')
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                json_data = contract.to_dict()
                if float(json_data['volume_24h']) * float(json_data['last']) > 1000000:
                    valid_contracts.append(contract.contract)
        print(f"Found {len(valid_contracts)} valid contracts", flush=True)
        return valid_contracts
        
    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
        if not candles: return pd.DataFrame()
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')
        
    def calculate_linear_regression(self, contract: str, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.lookback_period: return pd.DataFrame()
        
        # คำนวณค่าเฉลี่ย (mid) ของราคาปิด
        df['middle'] = df['close'].rolling(self.lookback_period).mean()
        
        # คำนวณ slope ของเส้น linear regression
        x = np.arange(self.lookback_period)
        df['slope'] = df['close'].rolling(self.lookback_period).apply(
            lambda y: np.polyfit(x, y, 1)[0], raw=True)
        
        # คำนวณค่า intercept (จุดตัดแกน y)
        df['intercept'] = df['middle'] - df['slope'] * (self.lookback_period // 2)
        
        # คำนวณจุดสิ้นสุดของเส้น regression
        df['end_line'] = df['intercept'] + df['slope'] * (self.lookback_period - 1)
        
        # คำนวณค่าเบี่ยงเบนมาตรฐานตามสูตร TradingView
        def calculate_deviation(prices):
            # ถ้าข้อมูลไม่พอ, ให้คืนค่า NaN
            if len(prices) < self.lookback_period:
                return np.nan
                
            y_actual = prices.values
            x_values = np.arange(len(y_actual))
            
            # คำนวณ slope และ intercept ด้วย linear regression
            slope, intercept = np.polyfit(x_values, y_actual, 1)
            
            # คำนวณค่าทำนายจาก regression line
            y_pred = slope * x_values + intercept
            
            # คำนวณผลรวมกำลังสองของความแตกต่าง (sum of squared differences)
            squared_diff_sum = np.sum(np.power(y_actual - y_pred, 2))
            
            # คำนวณ standard deviation
            dev = np.sqrt(squared_diff_sum / len(y_actual))
            return dev
        
        # ใช้ rolling window เพื่อคำนวณค่าเบี่ยงเบน
        df['dev'] = df['close'].rolling(self.lookback_period).apply(
            calculate_deviation, raw=False) * self.dev_multiplier
        
        # สร้างเส้นบนและเส้นล่างของ channel
        df['upper_line'] = df['end_line'] + df['dev']
        df['lower_line'] = df['end_line'] - df['dev']
        
        print(f"{contract} {len(df)} candles with slope={df.iloc[-1]['slope']:.4f}, dev={df.iloc[-1]['dev']:.4f} Upper: {df.iloc[-1]['upper_line']:.4f}, Lower: {df.iloc[-1]['lower_line']:.4f}", flush=True)
        return df.dropna()
        
    def check_trading_signal(self, df: pd.DataFrame) -> str:
        if len(df) < 2 or 'upper_line' not in df.columns: return None
        current = df.iloc[-1]
        previous = df.iloc[-2]
        if previous['high'] >= previous['upper_line'] and previous['close'] < previous['open'] and current['close'] < current['upper_line']:
            print(f"SELL signal detected: Close={current['close']:.4f}, Upper={current['upper_line']:.4f}", flush=True)
            return "SELL"
        return None
        
    def set_leverage(self, contract: str) -> bool:
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            print(f"Set leverage {self.leverage}x for {contract}", flush=True)
            return True
        except Exception as e:
            print(f"Failed to set leverage for {contract}: {str(e)}", flush=True)
            return False
            
    def get_latest_price(self, contract: str) -> float:
        ticker = self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract == contract: return float(t.last)
        print(f"No price found for {contract}", flush=True)
        return None
        
    def check_existing_position(self, contract: str) -> Dict:
        positions = self.futures_api.list_positions(settle='usdt', holding=True)
        for p in positions:
            if p.contract == contract:
                print(f"Found existing position for {contract}: Size={p.size}", flush=True)
                return p.to_dict()
        return None
        
    def close_position(self, contract: str, position: Dict) -> bool:
        try:
            size = float(position['size'])
            if size != 0:
                direction = abs(size) if size < 0 else -size
                self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': direction, 'price': 0, 'tif': 'ioc', 'reduce_only': True})
                print(f"Closed position for {contract}: Size={abs(size)}", flush=True)
                return True
            return False
        except Exception as e:
            print(f"Failed to close position for {contract}: {str(e)}", flush=True)
            return False
            
    def create_short_order(self, contract: str) -> Dict:
        try:
            if not self.set_leverage(contract): return None
            price = self.get_latest_price(contract)
            if not price: return None
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': -size, 'price': 0, 'tif': 'ioc', 'reduce_only': False})
            print(f"Opened SHORT position: {contract} Size={size}", flush=True)
            return order
        except Exception as e:
            print(f"Failed to open SHORT for {contract}: {str(e)}", flush=True)
            return None
            
    def scan_positions(self):
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            print(f"Scanning {len(positions)} open positions", flush=True)
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df = self.calculate_linear_regression(contract, df)
                    size = float(pos['size'])
                    current_price = self.get_latest_price(contract)
                    if size < 0 and current_price and current_price > df.iloc[-1]['upper_line']:
                        self.close_position(contract, pos)
        except Exception as e:
            print(f"Error scanning positions: {str(e)}", flush=True)
            
    def scan_market(self):
        first_run = True
        while True:
            current_time = pd.Timestamp.now(tz='Asia/Bangkok')
            if current_time.minute % 15 == 0 or first_run:
                print(f"Starting market scan at {current_time}", flush=True)
                first_run = False
                self.scan_positions()
                contracts = self.get_futures_contracts()
                for contract in contracts:
                    existing_pos = self.check_existing_position(contract)
                    df = self.get_candlesticks(contract)
                    if not df.empty:
                        df = self.calculate_linear_regression(contract, df)
                        signal = self.check_trading_signal(df)
                        if signal == "SELL" and not existing_pos:
                            self.create_short_order(contract)
                time.sleep(30)
            time.sleep(10)

def main():
    scanner = GateIOShortScanner()
    print("Starting Futures market scanner...", flush=True)
    scanner.scan_market()

if __name__ == "__main__":
    main()