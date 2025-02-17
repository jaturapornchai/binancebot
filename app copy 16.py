import os
import time
import re
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi

class GateIOEMAScanner:
    def __init__(self):
        load_dotenv()
        self.api_key = self._get_env_variable('GATEIO_API_KEY')
        self.secret_key = self._get_env_variable('GATEIO_SECRET_KEY')
        self.client = self._initialize_client()
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5
        self.ema_short_period = 20
        self.ema_long_period = 200
        self.order_amount = 20  # USD

    def _get_env_variable(self, var_name: str) -> str:
        value = os.getenv(var_name)
        if not value:
            raise ValueError(f"กรุณากำหนดค่า {var_name} ใน .env file")
        return value

    def _initialize_client(self) -> ApiClient:
        config = Configuration(
            key=self.api_key,
            secret=self.secret_key,
            host="https://api.gateio.ws/api/v4"            
        )
        return ApiClient(config)

    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อคู่เทรดที่ไม่มีตัวเลข"""
        try:
            ticket = self.futures_api.list_futures_tickers(settle='usdt')
            valid_contracts = []
            pattern = re.compile(r'^\D+_USDT$')
            
            for contract in ticket:
                if pattern.match(contract.contract):
                    json_data = contract.to_dict()
                    volume = float(json_data['volume_24h'])
                    last_price = float(json_data['last'])
                    volume_usd = volume * last_price
                    if volume_usd > 100000:
                        valid_contracts.append(contract.contract)
            return valid_contracts
        except Exception as e:
            print(f"ไม่สามารถดึงรายชื่อคู่เทรดได้: {str(e)}", flush=True)
            return []

    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูล candlesticks รายชั่วโมง"""
        try:
            candles = self.futures_api.list_futures_candlesticks(
                settle='usdt',
                contract=contract,
                interval='15m',
                limit=500
            )
            
            if not candles:
                return pd.DataFrame()

            data = []
            for candle in candles:
                try:
                    row = {
                        'timestamp': float(candle.t),
                        'open': float(candle.o),
                        'high': float(candle.h),
                        'low': float(candle.l),
                        'close': float(candle.c),
                        'volume': float(candle.v)
                    }
                    data.append(row)
                except (AttributeError, ValueError, TypeError) as e:
                    continue
            
            df = pd.DataFrame(data)
            
            if df.empty:
                return df
                
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            return df.sort_values('timestamp')
            
        except Exception as e:
            print(f"ไม่สามารถดึงข้อมูล candlesticks สำหรับ {contract}: {str(e)}", flush=True)
            return pd.DataFrame()

    def calculate_ema(self, df: pd.DataFrame) -> pd.DataFrame:
        """คำนวณ EMA 20 และ EMA 200"""
        try:
            df['EMA20'] = df['close'].ewm(span=self.ema_short_period, adjust=False).mean()
            df['EMA200'] = df['close'].ewm(span=self.ema_long_period, adjust=False).mean()
            return df
        except Exception as e:
            print(f"ไม่สามารถคำนวณ EMA: {str(e)}", flush=True)
            return df

    def set_leverage(self, contract: str) -> bool:
        """ตั้งค่า leverage"""
        try:
            self.futures_api.update_position_leverage(
                contract=contract,
                settle='usdt',
                leverage=str(self.leverage)
            )
            return True
        except Exception as e:
            print(f"ไม่สามารถตั้งค่า leverage: {str(e)}", flush=True)
            return False

    def get_latest_price(self, symbol):
        ticker = self.futures_api.list_futures_tickers(settle='usdt')        
        for t in ticker:
            if t.contract == symbol:
                return float(t.last)
        return None

    def check_existing_position(self, contract: str) -> bool:
        try:
            positions = self.futures_api.list_positions(settle='usdt', holding=True)
            positions = [p.to_dict() for p in positions]
            
            for position in positions:
                if position['contract'] == contract:
                    return True
            return False
            
        except Exception as e:
            print(f"ไม่สามารถตรวจสอบ Position: {str(e)}", flush=True)
            return False

    def create_order(self, contract: str, size: float) -> Dict:
        try:
            if not self.set_leverage(contract):
                return None

            print(f"\nกำลังเปิด Position: {contract}\n", flush=True)
            
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            price = self.get_latest_price(contract)
            
            json_data = contract_info.to_dict()
            contract_multiplier = float(json_data['quanto_multiplier'])
            min_order_size = float(json_data['order_size_min'])
            
            usd_value = size * self.leverage
            contract_size = usd_value / (price * contract_multiplier)
            contract_size = max(min_order_size, round(contract_size))

            entry_result = self.futures_api.create_futures_order('usdt', 
                {
                    'contract': contract,
                    'size': -contract_size,  # Short position
                    'price': 0,
                    'tif': 'ioc',
                    'reduce_only': False
                }
            )
            
            return entry_result

        except Exception as e:
            print(f"ไม่สามารถเปิด Position: {str(e)}", flush=True)
            return None

    def scan_market(self):
        """สแกนตลาดและตรวจสอบ EMA"""
        try:
            while True:
                print("\nกำลังดึงรายชื่อคู่เทรด...", flush=True)
                contracts = self.get_futures_contracts()
                print(f"พบ {len(contracts)} คู่เทรด", flush=True)
                            
                for contract in contracts:
                    df = self.get_candlesticks(contract)
                    if not df.empty:
                        df = self.calculate_ema(df)
                        current = df.iloc[-1]
                        
                        # เงื่อนไขการเข้า Short - EMA20 ตัดลงตัด EMA200
                        previous = df.iloc[-2]
                        
                        # ตรวจสอบการตัดลงของ EMA20
                        ema_crossdown = (previous['EMA20'] > previous['EMA200']) and (current['EMA20'] < current['EMA200'])
                        
                        status = "🔴 SHORT SIGNAL" if ema_crossdown else ""
                        print(f"{contract:12} | Price: {current['close']:10.4f} | EMA20: {current['EMA20']:10.4f} | EMA200: {current['EMA200']:10.4f} | {status}", flush=True)
                        
                        if status != "":
                            if self.check_existing_position(contract):
                                print(f"ไม่เปิด Order ใหม่เนื่องจากมี Position {contract} อยู่แล้ว", flush=True)
                            else:
                                self.create_order(
                                    contract=contract,
                                    size=self.order_amount
                                )

                print("-" * 80, flush=True)
                self.take_profit_or_stop_loss()
                print("-" * 80, flush=True)
                time.sleep(120)

        except KeyboardInterrupt:
            print("\nหยุดการสแกนตลาด", flush=True)
        except Exception as e:
            print(f"\nเกิดข้อผิดพลาด: {str(e)}", flush=True)
            print("จะทำการสแกนใหม่ใน 1 นาที...", flush=True)
            time.sleep(60)

    def take_profit_or_stop_loss(self):
        try:
            positions = self.futures_api.list_positions(settle='usdt', holding=True)
            positions = [p.to_dict() for p in positions]

            for position in positions:
                unrealised_pnl = float(position['unrealised_pnl'])
                print(f"{position['contract']} | Unrealised PnL: {unrealised_pnl}", flush=True)
                if unrealised_pnl > 5 or unrealised_pnl < -5:
                    self.futures_api.create_futures_order('usdt', 
                        {
                            'contract': position['contract'],
                            'size': -float(position['size']),
                            'price': 0,
                            'tif': 'ioc',
                            'reduce_only': True
                        }
                    )
                    print(f"ปิด Position {position['contract']}", flush=True)
            
        except Exception as e:
            print(f"ไม่สามารถตรวจสอบ Position: {str(e)}", flush=True)
            return False

def main():
    try:
        scanner = GateIOEMAScanner()
        print("เริ่มสแกนตลาด Futures...", flush=True)
        scanner.scan_market()
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {str(e)}", flush=True)

if __name__ == "__main__":
    main()