import os
import time
import re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
class GateIOLinearRegressionTrader:
    def __init__(self):
        load_dotenv() # โหลดไฟล์ .env เพื่อดึงค่า API keys
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys missing")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5  # ค่า leverage ที่ใช้
        self.order_amount = 50  # จำนวนเงิน USD ที่ใช้ต่อออเดอร์
        self.lookback_period = 100  # จำนวนแท่งที่ใช้ในการคำนวณ Linear Regression
        self.deviation = 2.0  # ค่าเบี่ยงเบนมาตรฐานที่ใช้ในการกำหนดเส้นบนและเส้นล่าง
    def get_futures_contracts(self) -> List[str]:
        """ดึงรายการสัญญา Futures ที่มีปริมาณซื้อขายมากกว่า 1,000,000 USD ใน 24 ชั่วโมง"""
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = []
        pattern = re.compile(r'^\D+_USDT$')
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                json_data = contract.to_dict()
                if float(json_data['volume_24h']) * float(json_data['last']) > 1000000:
                    valid_contracts.append(contract.contract)
        print(f"พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา", flush=True)
        return valid_contracts
    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนของสัญญาใช้ timeframe 15 นาที"""
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
        if not candles: return pd.DataFrame()
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df['color'] = np.where(df['close'] > df['open'], 'green', 'red')  # กำหนดสีแท่งเทียน เขียว=ราคาปิดสูงกว่าเปิด, แดง=ราคาปิดต่ำกว่าเปิด
        return df.sort_values('timestamp')
    def calculate_linear_regression_channel(self, df: pd.DataFrame) -> pd.DataFrame:
        """คำนวณ Linear Regression Channel (เส้นกลาง, เส้นบน, เส้นล่าง)"""
        if len(df) < self.lookback_period: return pd.DataFrame()
        latest_data = df.iloc[-self.lookback_period:].copy()
        x = np.arange(self.lookback_period)
        y = latest_data['close'].values
        slope, intercept = np.polyfit(x, y, 1)  # คำนวณ slope และ intercept ของเส้นตรง
        latest_data['reg_middle'] = intercept + slope * x  # เส้นกลาง
        y_pred = intercept + slope * x
        dev = np.sqrt(np.sum((y - y_pred) ** 2) / len(y))  # คำนวณค่าเบี่ยงเบนมาตรฐาน
        latest_data['reg_upper'] = latest_data['reg_middle'] + self.deviation * dev  # เส้นบน
        latest_data['reg_lower'] = latest_data['reg_middle'] - self.deviation * dev  # เส้นล่าง
        result = df.copy()
        result.iloc[-self.lookback_period:, result.columns.get_indexer(['reg_middle', 'reg_upper', 'reg_lower'])] = latest_data[['reg_middle', 'reg_upper', 'reg_lower']].values
        return result
    def check_trading_signal(self, df: pd.DataFrame, last_price: float) -> str:
        """ตรวจสอบสัญญาณการซื้อขายตามเงื่อนไขใหม่
        BUY: แท่งเทียนล่าสุดเป็นสีเขียว และ แท่งเทียนทับเส้นล่าง และ ราคาล่าสุดสูงกว่าเส้นล่าง
        SELL: แท่งเทียนล่าสุดเป็นสีแดง และ แท่งเทียนทับเส้นบน และ ราคาล่าสุดต่ำกว่าเส้นบน"""
        if df.empty or 'reg_middle' not in df.columns: return None
        latest_candle = df.iloc[-1]  # แท่งเทียนล่าสุด
        # ตรวจสอบเงื่อนไข BUY
        candle_touches_lower = latest_candle['low'] <= latest_candle['reg_lower'] and latest_candle['high'] >= latest_candle['reg_lower']
        if latest_candle['color'] == 'green' and candle_touches_lower and last_price > latest_candle['reg_lower']:
            print(f"สัญญาณ BUY: แท่งเทียนสีเขียว, ทับเส้นล่าง, ราคาล่าสุด {last_price:.4f} > เส้นล่าง {latest_candle['reg_lower']:.4f}", flush=True)
            return "BUY"
        # ตรวจสอบเงื่อนไข SELL
        candle_touches_upper = latest_candle['high'] >= latest_candle['reg_upper'] and latest_candle['low'] <= latest_candle['reg_upper'] 
        if latest_candle['color'] == 'red' and candle_touches_upper and last_price < latest_candle['reg_upper']:
            print(f"สัญญาณ SELL: แท่งเทียนสีแดง, ทับเส้นบน, ราคาล่าสุด {last_price:.4f} < เส้นบน {latest_candle['reg_upper']:.4f}", flush=True)
            return "SELL"
        return None
    def set_leverage(self, contract: str) -> bool:
        """ตั้งค่า leverage สำหรับสัญญา"""
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            print(f"ตั้งค่า leverage {self.leverage}x สำหรับ {contract}", flush=True)
            return True
        except Exception as e:
            print(f"ไม่สามารถตั้งค่า leverage สำหรับ {contract}: {str(e)}", flush=True)
            return False
    def get_latest_price(self, contract: str) -> float:
        """ดึงราคาล่าสุดของสัญญา"""
        ticker = self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract == contract: return float(t.last)
        print(f"ไม่พบราคาสำหรับ {contract}", flush=True)
        return None
    def check_existing_position(self, contract: str) -> Dict:
        """ตรวจสอบว่ามี position เปิดอยู่หรือไม่"""
        positions = self.futures_api.list_positions(settle='usdt', holding=True)
        for p in positions:
            if p.contract == contract:
                position_info = p.to_dict()
                size = float(position_info['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                print(f"พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}", flush=True)
                return position_info
        return None
    def close_position(self, contract: str, position: Dict) -> bool:
        """ปิด position ที่มีอยู่"""
        try:
            size = float(position['size'])
            if size != 0:
                direction = abs(size) if size < 0 else -size
                self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': direction, 'price': 0, 'tif': 'ioc', 'reduce_only': True})
                position_type = "LONG" if size > 0 else "SHORT"
                print(f"ปิด position {position_type} สำหรับ {contract}: ขนาด={abs(size)}", flush=True)
                return True
            return False
        except Exception as e:
            print(f"ไม่สามารถปิด position สำหรับ {contract}: {str(e)}", flush=True)
            return False
    def create_long_order(self, contract: str) -> Dict:
        """สร้างคำสั่งซื้อ (LONG)"""
        try:
            if not self.set_leverage(contract): return None
            price = self.get_latest_price(contract)
            if not price: return None
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': size, 'price': 0, 'tif': 'ioc', 'reduce_only': False})
            print(f"เปิด position LONG: {contract} ขนาด={size}", flush=True)
            return order
        except Exception as e:
            print(f"ไม่สามารถเปิด LONG สำหรับ {contract}: {str(e)}", flush=True)
            return None
    def create_short_order(self, contract: str) -> Dict:
        """สร้างคำสั่งขาย (SHORT)"""
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
            print(f"เปิด position SHORT: {contract} ขนาด={size}", flush=True)
            return order
        except Exception as e:
            print(f"ไม่สามารถเปิด SHORT สำหรับ {contract}: {str(e)}", flush=True)
            return None
    def scan_positions(self):
        """สแกน positions ที่มีอยู่และปิดตามเงื่อนไข
        ปิด long position ถ้า position เป็น long และมีสัญญาณ SELL
        ปิด short position ถ้า position เป็น short และมีสัญญาณ BUY"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            print(f"สแกน {len(positions)} positions ที่เปิดอยู่", flush=True)
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                last_price = self.get_latest_price(contract)
                if not df.empty and last_price:
                    df = self.calculate_linear_regression_channel(df)
                    if df.empty: continue
                    size = float(pos['size'])
                    signal = self.check_trading_signal(df, last_price)
                    if size > 0 and signal == "SELL":
                        print(f"สัญญาณปิด LONG: {contract} เนื่องจากได้รับสัญญาณ SELL", flush=True)
                        self.close_position(contract, pos)
                    if size < 0 and signal == "BUY":
                        print(f"สัญญาณปิด SHORT: {contract} เนื่องจากได้รับสัญญาณ BUY", flush=True)
                        self.close_position(contract, pos)
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสแกน positions: {str(e)}", flush=True)
    def scan_market(self):
        """สแกนตลาดเพื่อหาโอกาสในการเทรดตามเงื่อนไข"""
        first_run = True
        while True:
            current_time = pd.Timestamp.now(tz='Asia/Bangkok')
            if current_time.minute % 15 == 0 or first_run:  # ทำงานทุกๆ 15 นาที หรือเมื่อเริ่มต้นโปรแกรม
                print(f"เริ่มสแกนตลาด ณ เวลา {current_time}", flush=True)
                first_run = False
                # สแกน positions ที่มีอยู่เพื่อปิดตามเงื่อนไข
                self.scan_positions()
                # ดึงรายการสัญญาที่มีสภาพคล่องดี
                contracts = self.get_futures_contracts()
                # สแกนทุกสัญญาเพื่อตรวจหาสัญญาณการเทรดใหม่
                for contract in contracts:
                    df = self.get_candlesticks(contract)
                    last_price = self.get_latest_price(contract)
                    if df.empty or not last_price: continue
                    df = self.calculate_linear_regression_channel(df)
                    if df.empty: continue
                    # ตรวจหาสัญญาณการเทรด
                    signal = self.check_trading_signal(df, last_price)
                    existing_pos = self.check_existing_position(contract)
                    print(f"สัญญาณการเทรดสำหรับ {contract}: {signal}", flush=True)
                    if signal == "BUY":
                        # ถ้ามี position short ให้ปิดก่อน แล้วค่อยเปิด long
                        if existing_pos and float(existing_pos['size']) < 0:
                            if self.close_position(contract, existing_pos):
                                self.create_long_order(contract)
                        # ถ้าไม่มี position ให้เปิด long เลย
                        elif not existing_pos:
                            self.create_long_order(contract)
                    elif signal == "SELL":
                        # ถ้ามี position long ให้ปิดก่อน แล้วค่อยเปิด short
                        if existing_pos and float(existing_pos['size']) > 0:
                            if self.close_position(contract, existing_pos):
                                self.create_short_order(contract)
                        # ถ้าไม่มี position ให้เปิด short เลย
                        elif not existing_pos:
                            self.create_short_order(contract)
                time.sleep(30)  # รอ 30 วินาทีก่อนสแกนรอบถัดไป
            time.sleep(10)  # ตรวจสอบทุก 10 วินาที
def main():
    trader = GateIOLinearRegressionTrader()
    print("เริ่มต้นระบบเทรด Futures ด้วย Linear Regression Channel...", flush=True)
    trader.scan_market()
if __name__ == "__main__":
    main()