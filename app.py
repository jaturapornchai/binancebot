import os
import time
import re
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
class GateIOBreakoutScanner:
    def __init__(self):
        load_dotenv()
        self.api_key = self._get_env_variable('GATEIO_API_KEY')
        self.secret_key = self._get_env_variable('GATEIO_SECRET_KEY')
        self.client = self._initialize_client()
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5
        self.order_amount = 20  # USD
        self.lookback_period = 20  # จำนวนแท่งเทียนย้อนหลังที่ใช้หาแนวต้านแนวรับ
    def _get_env_variable(self, var_name: str) -> str:
        value = os.getenv(var_name)
        if not value:
            raise ValueError(f"กรุณากำหนดค่า {var_name} ใน .env file")
        return value
    def _initialize_client(self) -> ApiClient:
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")            
        return ApiClient(config)
    def get_futures_contracts(self) -> List[str]:
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
                    if volume_usd > 75000:
                        valid_contracts.append(contract.contract)
            return valid_contracts
        except Exception as e:
            print(f"ไม่สามารถดึงรายชื่อคู่เทรดได้: {str(e)}", flush=True)
            return []
    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        try:
            candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
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
    def get_hourly_candlesticks(self, contract: str) -> pd.DataFrame:
        try:
            candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='1h', limit=500)
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
            print(f"ไม่สามารถดึงข้อมูล candlesticks รายชั่วโมงสำหรับ {contract}: {str(e)}", flush=True)
            return pd.DataFrame()
    def calculate_breakout_levels(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df['resistance'] = df['high'].rolling(window=self.lookback_period).max()
            df['support'] = df['low'].rolling(window=self.lookback_period).min()
            return df
        except Exception as e:
            print(f"ไม่สามารถคำนวณแนวต้านแนวรับ: {str(e)}", flush=True)
            return df
    def check_breakout_signal(self, current: pd.Series, previous: pd.Series, contract: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            hourly_df = self.get_hourly_candlesticks(contract)
            if hourly_df.empty:
                return None, None
            if current['close'] > previous['resistance']:
                if current['open'] > current['close']:  # แท่งสีแดง = BU-OB
                    return "LONG", "BU-OB"
                else:  # แท่งสีเขียว = BU-BB
                    return "LONG", "BU-BB"
            elif current['close'] < previous['support']:
                if current['open'] < current['close']:  # แท่งสีเขียว = BE-OB
                    return "SHORT", "BE-OB"
                else:  # แท่งสีแดง = BE-BB
                    return "SHORT", "BE-BB"
            return None, None
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการตรวจสอบสัญญาณ: {str(e)}", flush=True)
            return None, None
    def set_leverage(self, contract: str) -> bool:
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            return True
        except Exception as e:
            print(f"ไม่สามารถตั้งค่า leverage: {str(e)}", flush=True)
            return False
    def get_latest_price(self, symbol: str) -> Optional[float]:
        try:
            ticker = self.futures_api.list_futures_tickers(settle='usdt')        
            for t in ticker:
                if t.contract == symbol:
                    return float(t.last)
            return None
        except Exception as e:
            print(f"ไม่สามารถดึงราคาล่าสุด: {str(e)}", flush=True)
            return None
    def check_existing_position(self, contract: str) -> Optional[Dict]:
        try:
            positions = self.futures_api.list_positions(settle='usdt', holding=True)
            positions = [p.to_dict() for p in positions]
            for position in positions:
                if position['contract'] == contract:
                    return position
            return None
        except Exception as e:
            print(f"ไม่สามารถตรวจสอบ Position: {str(e)}", flush=True)
            return None
    def close_position(self, contract: str, current_position: Dict) -> bool:
        try:
            if current_position:
                current_size = float(current_position['size'])
                print(f"ปิด Position ของ {contract} (ขนาด: {current_size})", flush=True)
                if current_size > 0:
                    self.futures_api.create_futures_order('usdt', {
                        'contract': contract,
                        'size': -current_size,
                        'price': 0,
                        'tif': 'ioc',
                        'reduce_only': True
                    })
                else:
                    self.futures_api.create_futures_order('usdt', {
                        'contract': contract,
                        'size': -current_size,
                        'price': 0,
                        'tif': 'ioc',
                        'reduce_only': True
                    })
                print(f"ปิด Position ของ {contract} (ขนาด: {abs(current_size)}) สำเร็จ", flush=True)
                return True
            return False
        except Exception as e:
            print(f"ไม่สามารถปิด Position: {str(e)}", flush=True)
            return False
    def create_order(self, contract: str, size: float, is_long: bool) -> Optional[Dict]:
        try:
            if not self.set_leverage(contract):
                return None
            position_type = "LONG" if is_long else "SHORT"
            print(f"\nกำลังเปิด {position_type} Position: {contract}\n", flush=True)
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            price = self.get_latest_price(contract)
            if price is None:
                print(f"ไม่สามารถดึงราคาล่าสุดของ {contract}", flush=True)
                return None
            json_data = contract_info.to_dict()
            contract_multiplier = float(json_data['quanto_multiplier'])
            min_order_size = float(json_data['order_size_min'])
            usd_value = size * self.leverage
            contract_size = usd_value / (price * contract_multiplier)
            contract_size = max(min_order_size, round(contract_size))
            entry_result = self.futures_api.create_futures_order('usdt', {
                'contract': contract,
                'size': contract_size if is_long else -contract_size,
                'price': 0,
                'tif': 'ioc',
                'reduce_only': False
            })
            return entry_result
        except Exception as e:
            print(f"ไม่สามารถเปิด Position: {str(e)}", flush=True)
            return None
    def take_profit_or_stop_loss(self):
        try:
            positions = self.futures_api.list_positions(settle='usdt', holding=True)
            positions = [p.to_dict() for p in positions]
            for position in positions:
                unrealised_pnl = float(position['unrealised_pnl'])
                print(f"{position['contract']} | Unrealised PnL: {unrealised_pnl}", flush=True)
                if unrealised_pnl > 4 or unrealised_pnl < -4:
                    self.close_position(position['contract'], position)
        except Exception as e:
            print(f"ไม่สามารถตรวจสอบ Position: {str(e)}", flush=True)
            return False
    def scan_market(self):
        first_run = True
        try:
            while True:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                if current_time.minute % 15 == 0 or first_run:
                    first_run = False
                    print("\nกำลังดึงรายชื่อคู่เทรด...", flush=True)
                    contracts = self.get_futures_contracts()
                    print(f"พบ {len(contracts)} คู่เทรด", flush=True)
                    for contract in contracts:
                        df = self.get_candlesticks(contract)
                        if not df.empty:
                            df = self.calculate_breakout_levels(df)
                            current = df.iloc[-1]
                            previous = df.iloc[-2]
                            signal, signal_type = self.check_breakout_signal(current, previous, contract)
                            status = ""
                            if signal == "LONG":
                                status = f"🟢 {signal_type} (Resistance: {previous['resistance']:.2f})"
                            elif signal == "SHORT":
                                status = f"🔴 {signal_type} (Support: {previous['support']:.2f})"
                            print(f"{contract:12} | Price: {current['close']:10.4f} | R: {current['resistance']:8.2f} | S: {current['support']:8.2f} | {status}", flush=True)
                            if signal:
                                current_position = self.check_existing_position(contract)
                                if current_position is None:
                                    print(f"ไม่มี Position ใน {contract} ให้เปิดใหม่", flush=True)
                                    self.create_order(contract=contract, size=self.order_amount, is_long=(signal == "LONG"))
                                    time.sleep(1)
                    time.sleep(60)
                    print("-" * 80, flush=True)
                    self.take_profit_or_stop_loss()
                    print("-" * 80, flush=True)
                    time.sleep(120)
                time.sleep(10)
        except KeyboardInterrupt:
            print("\nหยุดการสแกนตลาด", flush=True)
        except Exception as e:
            print(f"\nเกิดข้อผิดพลาด: {str(e)}", flush=True)
            print("จะทำการสแกนใหม่ใน 1 นาที...", flush=True)
            time.sleep(60)
def main():
    try:
        scanner = GateIOBreakoutScanner()
        print("เริ่มสแกนตลาด Futures...", flush=True)
        scanner.scan_market()
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {str(e)}", flush=True)
if __name__ == "__main__":
    main()