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
        if not self.api_key or not self.secret_key:
            raise ValueError("ต้องกำหนด GATEIO_API_KEY และ GATEIO_SECRET_KEY ใน .env")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5
        self.order_amount = 20
        self.lookback_period = 100
        
    def get_futures_contracts(self) -> List[str]:
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = []
        pattern = re.compile(r'^\D+_USDT$')
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                json_data = contract.to_dict()
                if float(json_data['volume_24h']) * float(json_data['last']) > 500000:
                    valid_contracts.append(contract.contract)
        return valid_contracts
        
    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='5m', limit=500)
        if not candles:
            return pd.DataFrame()
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')
        
    def calculate_linear_regression(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.lookback_period:
            return df
        def calc_lr(values):
            x = np.arange(len(values))
            slope, intercept = np.polyfit(x, values, 1)
            regression_line = slope * x + intercept
            return regression_line[-1]
        x = np.arange(self.lookback_period)
        df['is_green'] = df['close'] > df['open']
        df['is_red'] = df['close'] < df['open']
        for i in range(len(df) - self.lookback_period + 1):
            window = df.iloc[i:i+self.lookback_period]
            y = window['close'].values
            slope, intercept = np.polyfit(x, y, 1)
            regression_line = slope * x + intercept
            deviation = np.sqrt(np.sum((y - regression_line)**2) / self.lookback_period)
            df.loc[df.index[i+self.lookback_period-1], 'middle_line'] = regression_line[-1]
            df.loc[df.index[i+self.lookback_period-1], 'upper_line'] = regression_line[-1] + deviation * 2
            df.loc[df.index[i+self.lookback_period-1], 'lower_line'] = regression_line[-1] - deviation * 2
        return df.dropna()
        
    def check_trading_signal(self, df: pd.DataFrame) -> str:
        if len(df) < 2:
            return None
        current = df.iloc[-1]
        previous = df.iloc[-2]
        if previous['high'] >= previous['upper_line'] and previous['is_red'] and current['close'] < current['upper_line']:
            return "SELL"
        if previous['low'] <= previous['lower_line'] and previous['is_green'] and current['close'] > current['lower_line']:
            return "BUY"
        return None
        
    def set_leverage(self, contract: str) -> bool:
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            return True
        except Exception as e:
            print(f"ตั้ง leverage ไม่ได้: {str(e)}", flush=True)
            return False
            
    def get_latest_price(self, contract: str) -> float:
        ticker = self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract == contract:
                return float(t.last)
        return None
        
    def check_existing_position(self, contract: str) -> Dict:
        positions = self.futures_api.list_positions(settle='usdt', holding=True)
        for p in positions:
            if p.contract == contract:
                return p.to_dict()
        return None
        
    def close_position(self, contract: str, position: Dict) -> bool:
        try:
            size = float(position['size'])
            if size < 0:
                self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': abs(size), 'price': 0, 'tif': 'ioc', 'reduce_only': True})
                print(f"ปิด Short Position {contract} ขนาด {abs(size)}", flush=True)
                return True
            return False
        except Exception as e:
            print(f"ปิด Position ไม่ได้: {str(e)}", flush=True)
            return False
            
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
            print(f"เปิด Short Position: {contract} ขนาด {size}", flush=True)
            return order
        except Exception as e:
            print(f"เปิด Short ไม่ได้: {str(e)}", flush=True)
            return None
            
    def scan_positions(self):
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df = self.calculate_linear_regression(df)
                    signal = self.check_trading_signal(df)
                    current = df.iloc[-1]
                    if float(pos['size']) < 0 and (signal == "BUY" or current['close'] > current['upper_line']):
                        print(f"ตรวจพบสัญญาณปิด Short: {contract}", flush=True)
                        self.close_position(contract, pos)
                    print(f"Position: {contract:12} | Size: {abs(float(pos['size'])):8.4f} | Entry: {float(pos['entry_price']):10.4f} | PNL: {float(pos['unrealised_pnl']):10.4f}", flush=True)
        except Exception as e:
            print(f"สแกน position ผิดพลาด: {str(e)}", flush=True)
            
    def scan_market(self):
        first_run = True
        while True:
            current_time = pd.Timestamp.now(tz='Asia/Bangkok')
            if current_time.minute % 5 == 0 or first_run:
                first_run = False
                self.scan_positions()
                contracts = self.get_futures_contracts()
                print(f"พบ {len(contracts)} คู่เทรด", flush=True)
                for contract in contracts:
                    if self.check_existing_position(contract):
                        continue
                    df = self.get_candlesticks(contract)
                    if not df.empty:
                        df = self.calculate_linear_regression(df)
                        signal = self.check_trading_signal(df)
                        if signal == "SELL":
                            self.create_short_order(contract)
                        status = "🔴 SELL" if signal == "SELL" else "🟢 BUY" if signal == "BUY" else ""
                        print(f"{contract:12} | Close: {df.iloc[-1]['close']:10.4f} | Upper: {df.iloc[-1]['upper_line']:10.4f} | Lower: {df.iloc[-1]['lower_line']:10.4f} | {status}", flush=True)
                time.sleep(30)
            time.sleep(10)

def main():
    scanner = GateIOShortScanner()
    print("เริ่มสแกนตลาด Futures (Short เท่านั้น)...", flush=True)
    scanner.scan_market()

if __name__ == "__main__":
    main()