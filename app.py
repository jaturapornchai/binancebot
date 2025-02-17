import os
import time
import re
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi

class GateIORSIScanner:
    def __init__(self):
        load_dotenv()
        self.api_key = self._get_env_variable('GATEIO_API_KEY')
        self.secret_key = self._get_env_variable('GATEIO_SECRET_KEY')
        self.client = self._initialize_client()
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5
        self.order_amount = 20  # USD
        
        # RSI parameters
        self.rsi_period = 14

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
        """ดึงรายชื่อคู่เทรดที่มี volume สูง"""
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
        """ดึงข้อมูล candlesticks ราย 15 นาที"""
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

    def calculate_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """คำนวณ RSI ตาม TradingView"""
        try:
            # คำนวณการเปลี่ยนแปลงของราคา
            change = df['close'].diff()
            
            # ใช้ RMA แทน SMA สำหรับการคำนวณ
            up = pd.Series(0.0, index=df.index)
            down = pd.Series(0.0, index=df.index)
            
            # First value initialization
            first_change = change.dropna().iloc[0]
            up.iloc[self.rsi_period] = max(first_change, 0)
            down.iloc[self.rsi_period] = max(-first_change, 0)
            
            # Calculate subsequent values
            for i in range(self.rsi_period + 1, len(df)):
                up.iloc[i] = (up.iloc[i-1] * (self.rsi_period - 1) + max(change.iloc[i], 0)) / self.rsi_period
                down.iloc[i] = (down.iloc[i-1] * (self.rsi_period - 1) + max(-change.iloc[i], 0)) / self.rsi_period
            
            # คำนวณ RSI
            df['RSI'] = np.where(down == 0, 100, 
                               np.where(up == 0, 0, 
                                      100 - (100 / (1 + up / down))))
            
            return df
        except Exception as e:
            print(f"ไม่สามารถคำนวณ RSI: {str(e)}", flush=True)
            return df

    def check_rsi_signal(self, current: pd.Series, previous: pd.Series) -> str:
        """ตรวจสอบสัญญาณจาก RSI"""
        try:
            # ตรวจสอบสัญญาณ RSI
            if current['RSI'] > 75:
                return "LONG"  
            elif current['RSI'] < 25:
                return "SHORT"   
            return None
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการตรวจสอบ RSI: {str(e)}", flush=True)
            return None

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
        """ดึงราคาล่าสุด"""
        ticker = self.futures_api.list_futures_tickers(settle='usdt')        
        for t in ticker:
            if t.contract == symbol:
                return float(t.last)
        return None

    def check_existing_position(self, contract: str) -> Dict:
        """ตรวจสอบ Position ที่มีอยู่และคืนค่าข้อมูล"""
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
        """ปิด Position ที่มีอยู่"""
        try:
            if current_position:
                current_size = float(current_position['size']) # ขนาด Position ที่มีอยู่
                print(f"ปิด Position ของ {contract} (ขนาด: {current_size})", flush=True)
                
                if current_size > 0:
                    self.futures_api.create_futures_order('usdt', 
                        {
                            'contract': contract,
                            'size': -current_size,  # ปิด Position ที่เป็น Long
                            'price': 0,  # Market order
                            'tif': 'ioc',
                            'reduce_only': True  # เป็นการปิด Position
                        }
                    )
                else:
                    self.futures_api.create_futures_order('usdt', 
                        {
                            'contract': contract,
                            'size': -current_size,  # ปิด Position ที่เป็น Short
                            'price': 0,  # Market order
                            'tif': 'ioc',
                            'reduce_only': True  # เป็นการปิด Position
                        }
                    )
                print(f"ปิด Position ของ {contract} (ขนาด: {abs(current_size)}) สำเร็จ", flush=True)
                return True
                
            return False
            
        except Exception as e:
            print(f"ไม่สามารถปิด Position: {str(e)}", flush=True)
            return False

    def create_order(self, contract: str, size: float, is_long: bool) -> Dict:
        """เปิด Position ใหม่"""
        try:
            if not self.set_leverage(contract):
                return None

            position_type = "LONG" if is_long else "SHORT"
            print(f"\nกำลังเปิด {position_type} Position: {contract}\n", flush=True)
            
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            price = self.get_latest_price(contract)
            
            json_data = contract_info.to_dict()
            contract_multiplier = float(json_data['quanto_multiplier'])
            min_order_size = float(json_data['order_size_min'])
            
            usd_value = size * self.leverage
            contract_size = usd_value / (price * contract_multiplier)
            contract_size = max(min_order_size, round(contract_size))
            
            # สร้าง Order (ใช้เครื่องหมาย +/- ตามทิศทาง)
            entry_result = self.futures_api.create_futures_order('usdt', 
                {
                    'contract': contract,
                    'size': contract_size if is_long else -contract_size,
                    'price': 0,  # Market order
                    'tif': 'ioc',
                    'reduce_only': False  # เป็นการเปิด Position ใหม่
                }
            )
            
            return entry_result

        except Exception as e:
            print(f"ไม่สามารถเปิด Position: {str(e)}", flush=True)
            return None

    def take_profit_or_stop_loss(self):
        """ตรวจสอบและปิด Position ตาม profit/loss"""
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
        """สแกนตลาดและตรวจสอบสัญญาณ RSI"""
        first_run = True
        try:
            while True:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                if current_time.minute % 15 == 0 or first_run:
                    first_run = False
                    # stop loss และ take profit
                    print("-" * 80, flush=True)
                    self.take_profit_or_stop_loss()
                    print("-" * 80, flush=True)
                    # ดึงรายชื่อคู่เทรดเมื่อรันครั้งแรก 
                    print("\nกำลังดึงรายชื่อคู่เทรด...", flush=True)
                    contracts = self.get_futures_contracts()
                    print(f"พบ {len(contracts)} คู่เทรด", flush=True)
                                
                    for contract in contracts:
                        df = self.get_candlesticks(contract)
                        if not df.empty:
                            df = self.calculate_rsi(df)
                            current = df.iloc[-1]
                            previous = df.iloc[-2]
                            
                            # ตรวจสอบสัญญาณจาก RSI
                            signal = self.check_rsi_signal(current, previous)
                            status = ""
                            
                            if signal == "LONG":
                                status = f"🟢 LONG SIGNAL (RSI: {current['RSI']:.2f})"
                            elif signal == "SHORT":
                                status = f"🔴 SHORT SIGNAL (RSI: {current['RSI']:.2f})"
                                
                            print(f"{contract:12} | Price: {current['close']:10.4f} | RSI: {current['RSI']:8.2f} | {status}", flush=True)
                            
                            if signal:
                                # ตรวจสอบ Position ปัจจุบัน
                                current_position = self.check_existing_position(contract)
                                
                                # ถ้ามี Position อยู่ ให้ปิดก่อน
                                if current_position is None:
                                    # เปิด Position ใหม่ตามสัญญาณ
                                    print(f"ไม่มี Position ใน {contract} ให้เปิดใหม่", flush=True)
                                    self.create_order(
                                        contract=contract,
                                        size=self.order_amount,
                                        is_long=(signal == "LONG")
                                    )
                                    time.sleep(1) # รอให้ระบบประมวลผลการเปิด Position
                    time.sleep(120)  # รอ 2 นาทีก่อนที่จะดึงข้อมูลใหม่            

                time.sleep(10)  # รอ 10 วินาทีก่อนที่จะดึงข้อมูลใหม่

        except KeyboardInterrupt:
            print("\nหยุดการสแกนตลาด", flush=True)
        except Exception as e:
            print(f"\nเกิดข้อผิดพลาด: {str(e)}", flush=True)
            print("จะทำการสแกนใหม่ใน 1 นาที...", flush=True)
            time.sleep(60)

def main():
    try:
        scanner = GateIORSIScanner()
        print("เริ่มสแกนตลาด Futures...", flush=True)
        scanner.scan_market()
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {str(e)}", flush=True)

if __name__ == "__main__":
    main()