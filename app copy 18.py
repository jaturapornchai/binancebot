import os
import time
import re
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi

class GateIOLinearRegressionScanner:
    def __init__(self):
        load_dotenv()
        self.api_key = self._get_env_variable('GATEIO_API_KEY')
        self.secret_key = self._get_env_variable('GATEIO_SECRET_KEY')
        self.client = self._initialize_client()
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5
        self.order_amount = 20
        self.lookback_period = 100

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
                # ไม่มี USDC ในการเทรด                
                if pattern.match(contract.contract) and contract.contract != 'USDC_USDT' and contract.contract != 'DOGS_USDT':
                    json_data = contract.to_dict()
                    volume = float(json_data['volume_24h'])
                    last_price = float(json_data['last'])
                    volume_usd = volume * last_price
                    if volume_usd > 500000:
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

    def calculate_linear_regression(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            if df.empty or len(df) < self.lookback_period:
                print(f"ข้อมูลไม่เพียงพอสำหรับการคำนวณ Linear Regression (ต้องการอย่างน้อย {self.lookback_period} แถว)", flush=True)
                return df

            length = self.lookback_period

            # ฟังก์ชันช่วยคำนวณ Linear Regression สำหรับ rolling window
            def calc_lr(values):
                x = np.arange(len(values))
                slope, intercept = np.polyfit(x, values, 1)
                return slope * (length - 1) + intercept  # ค่าเส้น regression ที่จุดสุดท้ายของ window

            def calc_slope(values):
                x = np.arange(len(values))
                slope, _ = np.polyfit(x, values, 1)
                return slope

            # คำนวณ middle_line และ slope ด้วย rolling window
            df['middle_line'] = df['close'].rolling(window=length, min_periods=length).apply(calc_lr, raw=True)
            df['slope'] = df['close'].rolling(window=length, min_periods=length).apply(calc_slope, raw=True)

            # คำนวณ deviation แบบ rolling เพื่อให้สะท้อนความผันผวนในแต่ละช่วง
            def calc_deviation(values):
                x = np.arange(len(values))
                slope, intercept = np.polyfit(x, values, 1)
                regression_line = slope * x + intercept
                return np.std(values - regression_line)

            df['deviation'] = df['close'].rolling(window=length, min_periods=length).apply(calc_deviation, raw=True)
            df['upper_line'] = df['middle_line'] + df['deviation'] * 2
            df['lower_line'] = df['middle_line'] - df['deviation'] * 2

            # ลบคอลัมน์ deviation ถ้าไม่ต้องการเก็บไว้
            df.drop(columns=['deviation'], inplace=True)

            return df.dropna()  # ลบแถวที่มี NaN จากการ rolling

        except Exception as e:
            print(f"ไม่สามารถคำนวณ Linear Regression: {str(e)}", flush=True)
            return df

    def check_trading_signal(self, df: pd.DataFrame) -> str:
        try:
            if df.empty or len(df) < 2:
                return None
            current = df.iloc[-1]
            previous = df.iloc[-2]
            current_close = current['close']
            if abs(current_close - current['lower_line']) < 0.0001:
                return "SHORT"
            elif abs(current_close - current['upper_line']) < 0.0001:
                return "LONG"
            return None
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการตรวจสอบสัญญาณ: {str(e)}", flush=True)
            return None

    def check_close_position(self, df: pd.DataFrame, position_type: str) -> bool:
        try:
            if df.empty:
                return False
            current = df.iloc[-1]
            if position_type == "LONG" and current['close'] < current['middle_line']:
                return True
            elif position_type == "SHORT" and current['close'] > current['middle_line']:
                return True
            return False
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการตรวจสอบการปิด Position: {str(e)}", flush=True)
            return False

    def set_leverage(self, contract: str) -> bool:
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
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

    def check_existing_position(self, contract: str) -> Dict:
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

    def create_order(self, contract: str, size: float, is_long: bool) -> Dict:
        
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

    def scan_positions(self):
        """
        สแกนและจัดการ positions ที่เปิดอยู่
        """
        try:
            positions = self.futures_api.list_positions(settle='usdt', holding=True)
            positions = [p.to_dict() for p in positions]
            
            for position in positions:
                contract = position['contract']
                df = self.get_candlesticks(contract)
                
                if not df.empty:
                    df = self.calculate_linear_regression(df)
                    position_type = "LONG" if float(position['size']) > 0 else "SHORT"
                    
                    profit_or_loss = float(position['unrealised_pnl'])  
                    # แสดงสถานะ position
                    print(f"Position: {contract:12} | Type: {position_type:5} | Size: {abs(float(position['size'])):8.4f} | " \
                        f"Entry: {float(position['entry_price']):10.4f} | Current: {df.iloc[-1]['close']:10.4f} | " \
                        f"PNL: {profit_or_loss:10.4f}"  
                        , flush=True)

                    if self.check_close_position(df, position_type):
                        print(f"\nตรวจพบสัญญาณปิด Position สำหรับ {contract}", flush=True)
                        self.close_position(contract, position)                                        
                    
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสแกน positions: {str(e)}", flush=True)

    def scan_market(self):
        first_run = True
        try:
            while True:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                                
                # สแกนหาโอกาสเปิด position ใหม่ทุก 15 นาที
                if current_time.minute % 15 == 0 or first_run:
                    first_run = False
                    self.scan_positions()
                    print("\nกำลังดึงรายชื่อคู่เทรด...", flush=True)
                    contracts = self.get_futures_contracts()
                    print(f"พบ {len(contracts)} คู่เทรด", flush=True)
                    
                    for contract in contracts:
                        # ข้ามคู่เทรดที่มี position อยู่แล้ว
                        if self.check_existing_position(contract):
                            continue
                            
                        df = self.get_candlesticks(contract)
                        if not df.empty:
                            df = self.calculate_linear_regression(df)
                            signal = self.check_trading_signal(df)
                            
                            if signal:
                                self.create_order(
                                    contract=contract,
                                    size=self.order_amount,
                                    is_long=(signal == "LONG")
                                )
                                
                            status = ""
                            if signal == "LONG":
                                status = "🟢 LONG SIGNAL (Price at Upper Line)"
                            elif signal == "SHORT":
                                status = "🔴 SHORT SIGNAL (Price at Lower Line)"
                                
                            print(f"{contract:12} | Close: {df.iloc[-1]['close']:10.4f} | " \
                                f"Middle: {df.iloc[-1]['middle_line']:10.4f} | Status: {status}", flush=True)
                                
                    time.sleep(60)
                time.sleep(30)
                
        except KeyboardInterrupt:
            print("\nหยุดการสแกนตลาด", flush=True)
        except Exception as e:
            print(f"\nเกิดข้อผิดพลาด: {str(e)}", flush=True)
            print("จะทำการสแกนใหม่ใน 1 นาที...", flush=True)
            time.sleep(60)
            
def main():
    try:
        scanner = GateIOLinearRegressionScanner()
        print("เริ่มสแกนตลาด Futures...", flush=True)
        scanner.scan_market()
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {str(e)}", flush=True)

if __name__ == "__main__":
    main()