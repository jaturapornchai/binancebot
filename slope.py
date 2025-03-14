import os
import time
import re
from typing import List, Dict, Tuple
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi

class GateIOSwingTradeScanner:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys missing")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        self.leverage = 2  # ค่า leverage ที่ใช้ - เปลี่ยนเป็น 2 ตามที่ต้องการ
        self.order_amount = 1000  # จำนวนเงิน USD ที่ใช้ต่อออเดอร์ - เปลี่ยนเป็น 1000 ตามที่ต้องการ
        self.lookback_period = 100  # จำนวนแท่งที่ใช้ในการคำนวณ Linear Regression
        self.dev_multiplier = 2.0  # ตัวคูณของค่าเบี่ยงเบนมาตรฐาน
        self.all_slopes = {}  # เก็บค่า slope ของทุกเหรียญ
        self.target_symbol = "BTC_USDT"  # ซื้อขายเฉพาะ BTC_USDT
    
    def get_futures_contracts(self) -> List[str]:
        """ดึงรายการสัญญา Futures ที่มีปริมาณซื้อขายมากกว่า 1 ล้าน USD ใน 24 ชั่วโมง"""
        try:
            ticket = self.futures_api.list_futures_tickers(settle='usdt')
            valid_contracts = []
            pattern = re.compile(r'^\D+_USDT$')
            for contract in ticket:
                if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                    json_data = contract.to_dict()
                    if float(json_data['volume_24h']) * float(json_data['last']) > 500000:
                        valid_contracts.append(contract.contract)
            print(f"พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา", flush=True)
            return valid_contracts
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงรายการสัญญา: {str(e)}", flush=True)
            return []
    
    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนของสัญญา"""
        try:
            candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
            if not candles: return pd.DataFrame()
            data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            return df.sort_values('timestamp')
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงข้อมูลแท่งเทียนของ {contract}: {str(e)}", flush=True)
            return pd.DataFrame()
    
    def calculate_linear_regression(self, contract: str, df: pd.DataFrame) -> pd.DataFrame:
        """คำนวณ Linear Regression และช่องราคา"""
        if len(df) < self.lookback_period: return pd.DataFrame()
        
        # คำนวณค่าเฉลี่ย (mid) ของราคาปิด
        df['middle'] = df['close'].rolling(self.lookback_period).mean()
        
        # คำนวณ slope ของเส้น linear regression
        x = np.arange(self.lookback_period)
        df['slope'] = df['close'].rolling(self.lookback_period).apply(
            lambda y: np.polyfit(x, y, 1)[0] if len(y) == self.lookback_period else np.nan, raw=True)
        
        # คำนวณค่า intercept (จุดตัดแกน y)
        df['intercept'] = df['middle'] - df['slope'] * (self.lookback_period // 2)
        
        # คำนวณจุดสิ้นสุดของเส้น regression
        df['end_line'] = df['intercept'] + df['slope'] * (self.lookback_period - 1)
        
        # คำนวณค่าเบี่ยงเบนมาตรฐานตามสูตร
        def calculate_deviation(prices):
            if len(prices) < self.lookback_period:
                return np.nan
            
            y_actual = prices.values
            x_values = np.arange(len(y_actual))
            
            # คำนวณ slope และ intercept ด้วย linear regression
            slope, intercept = np.polyfit(x_values, y_actual, 1)
            
            # คำนวณค่าทำนายจาก regression line
            y_pred = slope * x_values + intercept
            
            # คำนวณผลรวมกำลังสองของความแตกต่าง
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
        
        # เพิ่มคอลัมน์เพื่อระบุว่าแท่งเทียนเป็นสีเขียวหรือแดง (bullish/bearish)
        df['is_bullish'] = df['close'] > df['open']
        df['is_bearish'] = df['close'] < df['open']
        
        # เก็บค่า slope ล่าสุดของเหรียญนี้
        if not df.empty and not np.isnan(df.iloc[-1]['slope']):
            self.all_slopes[contract] = df.iloc[-1]['slope']
        
        print(f"{contract} - แท่งเทียนจำนวน {len(df)} แท่ง, slope={df.iloc[-1]['slope']:.6f}, dev={df.iloc[-1]['dev']:.4f}, Upper: {df.iloc[-1]['upper_line']:.4f}, Lower: {df.iloc[-1]['lower_line']:.4f}", flush=True)
        return df.dropna()
    
    def calculate_average_slope(self) -> float:
        """คำนวณค่าเฉลี่ย slope ของทุกเหรียญและแสดงรายละเอียด"""
        if not self.all_slopes:
            print("ไม่พบข้อมูล slope ของเหรียญใดๆ", flush=True)
            return 0.0
        
        total_slope = sum(self.all_slopes.values())
        avg_slope = total_slope / len(self.all_slopes)
        
        # เรียงลำดับเหรียญตาม slope จากมากไปน้อย
        sorted_slopes = {k: v for k, v in sorted(self.all_slopes.items(), key=lambda item: item[1], reverse=True)}
        
        # แบ่งกลุ่มตามค่า slope
        uptrend_coins = {k: v for k, v in sorted_slopes.items() if v > 0}
        downtrend_coins = {k: v for k, v in sorted_slopes.items() if v < 0}
        
        print("\n====================================================", flush=True)
        print(f"สรุปค่า Slope ของทุกเหรียญ", flush=True)
        print("====================================================", flush=True)
        print(f"จำนวนเหรียญทั้งหมด: {len(self.all_slopes)}", flush=True)
        print(f"ค่าเฉลี่ย Slope: {avg_slope:.6f}", flush=True)
        print(f"จำนวนเหรียญที่อยู่ใน Uptrend (Slope > 0): {len(uptrend_coins)}", flush=True)
        print(f"จำนวนเหรียญที่อยู่ใน Downtrend (Slope < 0): {len(downtrend_coins)}", flush=True)
        
        if sorted_slopes:
            print("\nเหรียญที่มี Slope สูงสุด 5 อันดับ:", flush=True)
            for i, (coin, slope) in enumerate(list(sorted_slopes.items())[:5]):
                print(f"{i+1}. {coin}: {slope:.6f}", flush=True)
            
            print("\nเหรียญที่มี Slope ต่ำสุด 5 อันดับ:", flush=True)
            for i, (coin, slope) in enumerate(list(sorted_slopes.items())[-5:]):
                print(f"{i+1}. {coin}: {slope:.6f}", flush=True)
        
        print("====================================================", flush=True)
        return avg_slope
    
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
        try:
            ticker = self.futures_api.list_futures_tickers(settle='usdt')
            for t in ticker:
                if t.contract == contract: return float(t.last)
            print(f"ไม่พบราคาสำหรับ {contract}", flush=True)
            return None
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงราคาล่าสุดของ {contract}: {str(e)}", flush=True)
            return None
    
    def check_existing_position(self, contract: str) -> Dict:
        """ตรวจสอบว่ามี position เปิดอยู่หรือไม่"""
        try:
            positions = self.futures_api.list_positions(settle='usdt', holding=True)
            for p in positions:
                if p.contract == contract:
                    position_info = p.to_dict()
                    size = float(position_info['size'])
                    position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                    print(f"พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}", flush=True)
                    return position_info
            return None
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการตรวจสอบ position ของ {contract}: {str(e)}", flush=True)
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
            print(f"เปิด position LONG: {contract} ขนาด={size} ($1,000)", flush=True)
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
            print(f"เปิด position SHORT: {contract} ขนาด={size} ($1,000)", flush=True)
            return order
        except Exception as e:
            print(f"ไม่สามารถเปิด SHORT สำหรับ {contract}: {str(e)}", flush=True)
            return None
    
    def scan_market(self):
        """สแกนตลาดเพื่อวิเคราะห์และทำการซื้อขายตามเงื่อนไขที่กำหนด"""
        first_run = True
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                if current_time.minute % 15 == 0 or first_run:
                    print(f"\nเริ่มสแกนตลาด ณ เวลา {current_time}", flush=True)
                    print("====================================================", flush=True)
                    self.all_slopes = {}  # รีเซ็ตข้อมูล slope ในแต่ละรอบ
                    first_run = False
                    
                    # ดึงรายการสัญญาที่มีสภาพคล่องดี
                    contracts = self.get_futures_contracts()
                    
                    # สแกนทุกสัญญาเพื่อคำนวณ slope
                    print("\nกำลังคำนวณค่า slope ของแต่ละเหรียญ...", flush=True)
                    for contract in contracts:
                        df = self.get_candlesticks(contract)
                        if df.empty: continue
                        
                        df = self.calculate_linear_regression(contract, df)
                        if df.empty: continue
                    
                    # คำนวณและแสดงค่าเฉลี่ย slope
                    avg_slope = self.calculate_average_slope()
                    
                    # ตรวจสอบ position ปัจจุบันของ BTC_USDT
                    btc_position = self.check_existing_position(self.target_symbol)
                    
                    # ใช้เงื่อนไขใหม่ในการซื้อขาย
                    print("\n====================================================", flush=True)
                    print(f"กำลังตรวจสอบเงื่อนไขการซื้อขาย {self.target_symbol}...", flush=True)
                    print(f"ค่าเฉลี่ย Slope: {avg_slope:.6f}", flush=True)
                    
                    # เงื่อนไขการปิด position
                    if btc_position:
                        size = float(btc_position['size'])
                        # ถ้ามี position เป็น long และค่าเฉลี่ย slope < 0.1 ให้ปิด position
                        if size > 0 and avg_slope < 0.1:
                            print(f"ปิด LONG เนื่องจากค่าเฉลี่ย slope ({avg_slope:.6f}) น้อยกว่า 0.1", flush=True)
                            self.close_position(self.target_symbol, btc_position)
                            btc_position = None  # อัพเดทสถานะ position หลังจากปิด
                        
                        # ถ้ามี position เป็น short และค่าเฉลี่ย slope > -0.1 ให้ปิด position
                        elif size < 0 and avg_slope > -0.1:
                            print(f"ปิด SHORT เนื่องจากค่าเฉลี่ย slope ({avg_slope:.6f}) มากกว่า -0.1", flush=True)
                            self.close_position(self.target_symbol, btc_position)
                            btc_position = None  # อัพเดทสถานะ position หลังจากปิด
                    
                    # เงื่อนไขการเปิด position ใหม่
                    if not btc_position:  # ถ้าไม่มี position อยู่
                        # ถ้าค่าเฉลี่ย slope > 0.1 ให้เปิด long
                        if avg_slope > 0.1:
                            print(f"เปิด LONG เนื่องจากค่าเฉลี่ย slope ({avg_slope:.6f}) มากกว่า 0.1", flush=True)
                            self.create_long_order(self.target_symbol)
                        
                        # ถ้าค่าเฉลี่ย slope < -0.1 ให้เปิด short
                        elif avg_slope < -0.1:
                            print(f"เปิด SHORT เนื่องจากค่าเฉลี่ย slope ({avg_slope:.6f}) น้อยกว่า -0.1", flush=True)
                            self.create_short_order(self.target_symbol)
                    
                    # รอ 30 วินาทีก่อนสแกนรอบถัดไป
                    print(f"\nการสแกนเสร็จสิ้น รอถึงช่วงเวลาถัดไป...", flush=True)
                    time.sleep(30)
                
                # ตรวจสอบทุก 10 วินาที
                time.sleep(10)
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}", flush=True)
                time.sleep(30)  # รอเวลาในกรณีเกิดข้อผิดพลาด

def main():
    scanner = GateIOSwingTradeScanner()
    print("เริ่มต้นระบบวิเคราะห์และซื้อขาย Futures...", flush=True)
    scanner.scan_market()

if __name__ == "__main__":
    main()