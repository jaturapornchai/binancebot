import os
import time
import re
from typing import List, Dict, Optional
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
        
        # Breakout parameters
        self.lookback_period = 20  # จำนวนแท่งเทียนย้อนหลังที่ใช้หาแนวต้านแนวรับ

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
                    if volume_usd > 75000:
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

    def calculate_breakout_levels(self, df: pd.DataFrame) -> pd.DataFrame:
        """คำนวณแนวต้านและแนวรับ"""
        try:
            # คำนวณแนวต้านและแนวรับจากข้อมูลย้อนหลัง
            df['resistance'] = df['high'].rolling(window=self.lookback_period).max()
            df['support'] = df['low'].rolling(window=self.lookback_period).min()
            
            return df
        except Exception as e:
            print(f"ไม่สามารถคำนวณแนวต้านแนวรับ: {str(e)}", flush=True)
            return df

    def calculate_linear_regression(self, df: pd.DataFrame, length: int = 100) -> tuple:
        """คำนวณ Linear Regression Channel
        
        Returns:
            tuple: (slope, deviation) โดย slope > 0 คือแนวโน้มขึ้น, slope < 0 คือแนวโน้มลง
        """
        try:
            # ใช้ข้อมูล close price length แท่งล่าสุด
            prices = df['close'].tail(length).values
            x = np.arange(len(prices))
            
            # คำนวณ Linear Regression
            slope, intercept = np.polyfit(x, prices, 1)
            
            # คำนวณ Standard Deviation
            reg_line = slope * x + intercept
            deviation = np.std(prices - reg_line)
            
            return slope, deviation
            
        except Exception as e:
            print(f"ไม่สามารถคำนวณ Linear Regression: {str(e)}", flush=True)
            return 0, 0

    def get_hourly_candlesticks(self, contract: str) -> pd.DataFrame:
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
            print(f"ไม่สามารถดึงข้อมูล candlesticks ราย 15 นาทีสำหรับ {contract}: {str(e)}", flush=True)
            return pd.DataFrame()

    def check_breakout_signal(self, current: pd.Series, previous: pd.Series, contract: str) -> str:
        """ตรวจสอบสัญญาณ Breakout พร้อมกับ Linear Regression Channel"""
        try:
            # ตรวจสอบ Breakout ขึ้น
            if current['close'] > previous['resistance']:
                # ดึงข้อมูลราย 15 นาทีเพื่อคำนวณ Linear Regression
                hourly_df = self.get_hourly_candlesticks(contract)
                if hourly_df.empty:
                    return None
                    
                # คำนวณ Linear Regression จากข้อมูล
                slope, deviation = self.calculate_linear_regression(hourly_df)
                
                # เปิด LONG เมื่อ slope < 0 (แนวโน้มลง)
                return "SHORT" if slope < 0 else None
                
            # ตรวจสอบ Breakout ลง    
            elif current['close'] < previous['support']:
                # ดึงข้อมูลราย 15 นาทีเพื่อคำนวณ Linear Regression
                hourly_df = self.get_hourly_candlesticks(contract)
                if hourly_df.empty:
                    return None
                    
                # คำนวณ Linear Regression จากข้อมูล
                slope, deviation = self.calculate_linear_regression(hourly_df)
                
                # เปิด SHORT เมื่อ slope > 0 (แนวโน้มขึ้น)
                return "LONG" if slope > 0 else None
            return None
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการตรวจสอบ Breakout: {str(e)}", flush=True)
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
        """สแกนตลาดและตรวจสอบสัญญาณ Breakout"""
        first_run = True
        try:
            while True:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                if current_time.minute % 15 == 0 or first_run:
                    first_run = False
                    # ดึงรายชื่อคู่เทรดเมื่อรันครั้งแรก 
                    print("\nกำลังดึงรายชื่อคู่เทรด...", flush=True)
                    contracts = self.get_futures_contracts()
                    print(f"พบ {len(contracts)} คู่เทรด", flush=True)
                                
                    for contract in contracts:
                        df = self.get_candlesticks(contract)
                        if not df.empty:
                            df = self.calculate_breakout_levels(df)
                            current = df.iloc[-1]
                            previous = df.iloc[-2]
                            
                            # ตรวจสอบสัญญาณ Breakout
                            signal = self.check_breakout_signal(current, previous, contract)
                            status = ""
                            
                            if signal == "LONG":
                                status = f"🟢 BREAKOUT UP (Resistance: {previous['resistance']:.2f})"
                            elif signal == "SHORT":
                                status = f"🔴 BREAKOUT DOWN (Support: {previous['support']:.2f})"
                                
                            print(f"{contract:12} | Price: {current['close']:10.4f} | R: {current['resistance']:8.2f} | S: {current['support']:8.2f} | {status}", flush=True)
                            
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
                    time.sleep(60)  # รอ 1 นาที
                    # stop loss และ take profit
                    print("-" * 80, flush=True)
                    self.take_profit_or_stop_loss()
                    print("-" * 80, flush=True)
                    time.sleep(120)  # รอ 2 นาที

                time.sleep(10)  # รอ 10 วินาทีก่อนที่จะดึงข้อมูลใหม่

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