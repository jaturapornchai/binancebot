import os
import time
import re
from typing import List, Dict
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
        self.leverage = 5  # ค่า leverage ที่ใช้
        self.order_amount = 20  # จำนวนเงิน USD ที่ใช้ต่อออเดอร์
        self.lookback_period = 100  # จำนวนแท่งที่ใช้ในการคำนวณ Linear Regression
        self.dev_multiplier = 2.0  # ตัวคูณของค่าเบี่ยงเบนมาตรฐาน
    
    def get_futures_contracts(self) -> List[str]:
        """ดึงรายการสัญญา Futures ที่มีปริมาณซื้อขายมากกว่า 1 ล้าน USD ใน 24 ชั่วโมง"""
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
    
    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนของสัญญา"""
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
        if not candles: return pd.DataFrame()
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')
    
    def calculate_linear_regression(self, contract: str, df: pd.DataFrame) -> pd.DataFrame:
        """คำนวณ Linear Regression และช่องราคา"""
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
        
        print(f"{contract} - แท่งเทียนจำนวน {len(df)} แท่ง, slope={df.iloc[-1]['slope']:.4f}, dev={df.iloc[-1]['dev']:.4f}, Upper: {df.iloc[-1]['upper_line']:.4f}, Lower: {df.iloc[-1]['lower_line']:.4f}", flush=True)
        return df.dropna()
    
    def check_trading_signal(self, df: pd.DataFrame, latest_price: float) -> str:
        """ตรวจสอบสัญญาณการซื้อขายตามเงื่อนไขที่กำหนดใหม่"""
        if len(df) < 2 or 'upper_line' not in df.columns: return None
        
        current = df.iloc[-1]
        
        # BUY: แท่งเทียนล่าสุดเป็นแท่งเขียว และ ((แท่งเทียนทับเส้นล่างพอดี และราคาล่าสุดสูงกว่าเส้นล่าง) หรือ (แท่งเทียนทับเส้นบนพอดี และราคาล่าสุดสูงกว่าเส้นบน))
        if current['is_bullish'] and ((current['low'] <= current['lower_line'] and latest_price > current['lower_line']) or 
                                      (current['high'] >= current['upper_line'] and latest_price > current['upper_line'])):
            print(f"สัญญาณ BUY: ราคาล่าสุด={latest_price:.4f}, เส้นล่าง={current['lower_line']:.4f}, เส้นบน={current['upper_line']:.4f}", flush=True)
            return "BUY"
        
        # SELL: แท่งเทียนล่าสุดเป็นแท่งแดง และ ((แท่งเทียนทับเส้นบนพอดี และราคาล่าสุดต่ำกว่าเส้นบน) หรือ (แท่งเทียนทับเส้นล่างพอดี และราคาล่าสุดต่ำกว่าเส้นล่าง))
        if current['is_bearish'] and ((current['high'] >= current['upper_line'] and latest_price < current['upper_line']) or 
                                      (current['low'] <= current['lower_line'] and latest_price < current['lower_line'])):
            print(f"สัญญาณ SELL: ราคาล่าสุด={latest_price:.4f}, เส้นบน={current['upper_line']:.4f}, เส้นล่าง={current['lower_line']:.4f}", flush=True)
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
        """สแกน positions ที่มีอยู่และปิดตามเงื่อนไขใหม่"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            print(f"สแกน {len(positions)} positions ที่เปิดอยู่", flush=True)
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df = self.calculate_linear_regression(contract, df)
                    if df.empty: continue
                    
                    size = float(pos['size'])
                    current_price = self.get_latest_price(contract)
                    current = df.iloc[-1]
                    
                    # ตรวจสอบสัญญาณการเทรด
                    signal = self.check_trading_signal(df, current_price)
                    
                    # ปิด long position ถ้า position เป็น long และเกิดสัญญาณ SELL
                    if size > 0 and signal == "SELL":
                        print(f"สัญญาณปิด LONG: {contract} เนื่องจากเกิดสัญญาณ SELL", flush=True)
                        self.close_position(contract, pos)
                    
                    # ปิด short position ถ้า position เป็น short และเกิดสัญญาณ BUY
                    if size < 0 and signal == "BUY":
                        print(f"สัญญาณปิด SHORT: {contract} เนื่องจากเกิดสัญญาณ BUY", flush=True)
                        self.close_position(contract, pos)
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสแกน positions: {str(e)}", flush=True)
            
    def scan_market(self):
        """สแกนตลาดเพื่อหาโอกาสในการเทรด"""
        first_run = True
        while True:
            current_time = pd.Timestamp.now(tz='Asia/Bangkok')
            # แสดงเวลา hh:mm:ss
            print(f"เวลาปัจจุบัน: {current_time.strftime('%H:%M:%S')}", flush=True)
            if current_time.minute % 15 == 0 or first_run:
                print(f"********* เริ่มสแกนตลาด ณ เวลา {current_time}", flush=True)
                first_run = False
                
                # สแกน positions ที่มีอยู่เพื่อปิดตามเงื่อนไข
                self.scan_positions()
                
                # ดึงรายการสัญญาที่มีสภาพคล่องดี
                contracts = self.get_futures_contracts()
                
                # สแกนทุกสัญญาเพื่อตรวจหาสัญญาณการเทรดใหม่
                for contract in contracts:
                    df = self.get_candlesticks(contract)
                    if df.empty: continue
                    
                    df = self.calculate_linear_regression(contract, df)
                    if df.empty: continue
                    
                    current_price = self.get_latest_price(contract)
                    if not current_price: continue
                    
                    # ตรวจหาสัญญาณการเทรด
                    signal = self.check_trading_signal(df, current_price)
                    existing_pos = self.check_existing_position(contract)
                    
                    """
                    if signal == "BUY":
                        # ถ้ามี position short ให้ปิดก่อน
                        if existing_pos and float(existing_pos['size']) < 0:
                            if self.close_position(contract, existing_pos):
                                self.create_long_order(contract)
                        # ถ้าไม่มี position ให้เปิด long เลย
                        elif not existing_pos:
                            self.create_long_order(contract)
                    """
                    
                    if signal == "SELL":
                        # ถ้ามี position long ให้ปิดก่อน
                        if existing_pos and float(existing_pos['size']) > 0:
                            if self.close_position(contract, existing_pos):
                                self.create_short_order(contract)
                        # ถ้าไม่มี position ให้เปิด short เลย
                        elif not existing_pos:
                            self.create_short_order(contract)
                
                # รอ 30 วินาทีก่อนสแกนรอบถัดไป
                time.sleep(30)
            
            # ตรวจสอบทุก 10 วินาที
            time.sleep(10)

def main():
    scanner = GateIOSwingTradeScanner()
    print("เริ่มต้นระบบสแกนตลาด Futures...", flush=True)
    scanner.scan_market()

if __name__ == "__main__":
    main()