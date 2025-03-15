import os
import time
import re
from typing import List, Dict, Tuple
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi

class GateIOLinearRegressionTrader:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys missing")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5  # ค่า leverage ที่ใช้
        self.order_amount = 50  # จำนวนเงิน USD ที่ใช้ต่อออเดอร์
        self.lookback_period = 100  # จำนวนแท่งที่ใช้ในการคำนวณ Linear Regression
        self.deviation = 2.0  # ค่า deviation ของ Linear Regression Channel
        
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
        """ดึงข้อมูลแท่งเทียนของสัญญา"""
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
        if not candles: return pd.DataFrame()
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        # ระบุสีของแท่งเทียน (สีเขียว=1, สีแดง=0)
        df['candle_color'] = np.where(df['close'] >= df['open'], 1, 0)  # 1=เขียว, 0=แดง
        return df.sort_values('timestamp')
    
    def calculate_linear_regression_channel(self, df: pd.DataFrame) -> Dict:
        """คำนวณ Linear Regression Channel ตามวิธีใน TradingView"""
        if len(df) < self.lookback_period: 
            print(f"ข้อมูลไม่เพียงพอ ต้องการอย่างน้อย {self.lookback_period} แท่ง แต่มีเพียง {len(df)} แท่ง", flush=True)
            return {}
            
        # ใช้เฉพาะข้อมูล lookback_period ล่าสุด
        df = df.iloc[-self.lookback_period:].copy().reset_index(drop=True)
        
        # ข้อมูลแท่งเทียนล่าสุด
        latest_candle = df.iloc[-1].copy()
        
        # คำนวณ Linear Regression Channel ตาม TradingView script
        src = df['close'].values
        len_period = self.lookback_period
        
        # คำนวณค่า mid
        mid = np.sum(src) / len_period
        
        # คำนวณค่า slope ตามวิธีการของ TradingView
        # slope = linreg(src, len, 0) - linreg(src, len, 1)
        # ต้องจำลองฟังก์ชั่น linreg ของ TradingView
        x = np.arange(len_period)
        slope_now = np.polyfit(x, src, 1)[0]
        slope_prev = np.polyfit(np.arange(1, len_period+1), np.append(src[0], src[:-1]), 1)[0]
        slope = slope_now - slope_prev
        
        # คำนวณค่า intercept ตามวิธีการของ TradingView
        # intercept = mid - slope * floor(len / 2) + ((1 - (len % 2)) / 2) * slope
        intercept = mid - slope * np.floor(len_period / 2) + ((1 - (len_period % 2)) / 2) * slope
        
        # คำนวณค่า endy
        # endy = intercept + slope * (len - 1)
        endy = intercept + slope * (len_period - 1)
        
        # คำนวณค่า dev
        # for x = 0 to len - 1
        #     dev := dev + pow(src[x] - (slope * (len - x) + intercept), 2)
        # dev := sqrt(dev/len)
        dev = 0.0
        for x in range(len_period):
            dev += (src[x] - (slope * (len_period - x) + intercept)) ** 2
        dev = np.sqrt(dev / len_period)
        
        # คำนวณจุดของเส้นบน เส้นกลาง และเส้นล่างสำหรับแท่งล่าสุด
        middle_line = endy
        upper_line = middle_line + dev * self.deviation
        lower_line = middle_line - dev * self.deviation
        
        # ตรวจสอบว่าแท่งล่าสุดทับเส้นบนหรือเส้นล่างหรือไม่
        touches_upper_line = (latest_candle['high'] >= upper_line and latest_candle['low'] <= upper_line)
        touches_lower_line = (latest_candle['high'] >= lower_line and latest_candle['low'] <= lower_line)
        
        # สร้าง dict ผลลัพธ์
        result = {
            'candle': latest_candle.to_dict(),
            'slope': slope,
            'intercept': intercept,
            'middle_line': middle_line,
            'upper_line': upper_line,
            'lower_line': lower_line,
            'dev': dev,
            'touches_upper_line': touches_upper_line,
            'touches_lower_line': touches_lower_line
        }
        
        print(f"Linear Regression ค่าที่คำนวณได้:", flush=True)
        print(f"  slope={slope:.6f}, intercept={intercept:.6f}, dev={dev:.6f}", flush=True)
        print(f"  เส้นกลาง={middle_line:.4f}, เส้นบน={upper_line:.4f}, เส้นล่าง={lower_line:.4f}", flush=True)
        print(f"  แท่งทับเส้นบน={touches_upper_line}, แท่งทับเส้นล่าง={touches_lower_line}", flush=True)
        print(f"  แท่งเป็นสี{'เขียว' if latest_candle['candle_color'] == 1 else 'แดง'}", flush=True)
        
        return result
    
    def check_trading_signal(self, channel_data: Dict) -> str:
        """ตรวจสอบสัญญาณการซื้อขายตามเงื่อนไขที่กำหนด"""
        if not channel_data: return None
        
        candle = channel_data['candle']
        touches_upper_line = channel_data['touches_upper_line']
        touches_lower_line = channel_data['touches_lower_line']
        is_green_candle = candle['candle_color'] == 1
        is_red_candle = candle['candle_color'] == 0
        
        # BUY=CANDLE เป็นสีเขียว และ CANDLE ทับเส้นบน
        if is_green_candle and touches_upper_line:
            print(f"สัญญาณ BUY: แท่งเขียว, แท่งทับเส้นบน", flush=True)
            return "BUY"
        
        # SELL=CANDLE เป็นสีแดง และ CANDLE ทับเส้นล่าง
        if is_red_candle and touches_lower_line:
            print(f"สัญญาณ SELL: แท่งแดง, แท่งทับเส้นล่าง", flush=True)
            return "SELL"
        
        print(f"ไม่พบสัญญาณซื้อขาย", flush=True)
        return None
    
    def check_close_position_signal(self, channel_data: Dict, position_type: str, last_price: float) -> bool:
        """ตรวจสอบเงื่อนไขการปิด position"""
        if not channel_data: return False
        
        middle_line = channel_data['middle_line']
        
        # ปิด long position ถ้า position เดิมที่เปิดอยู่เป็น long และ ราคาล่าสุดต่ำกว่า MIDDLE
        if position_type == "LONG" and last_price < middle_line:
            print(f"สัญญาณปิด LONG: ราคาล่าสุด={last_price:.4f} ต่ำกว่าเส้นกลาง={middle_line:.4f}", flush=True)
            return True
        
        # ปิด short position ถ้า position เดิมที่เปิดอยู่เป็น short และ ราคาล่าสุดสูงกว่า MIDDLE
        if position_type == "SHORT" and last_price > middle_line:
            print(f"สัญญาณปิด SHORT: ราคาล่าสุด={last_price:.4f} สูงกว่าเส้นกลาง={middle_line:.4f}", flush=True)
            return True
        
        return False
    
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
                    channel_data = self.calculate_linear_regression_channel(df)
                    if not channel_data: continue
                    
                    # ดึงราคาล่าสุด
                    last_price = self.get_latest_price(contract)
                    if not last_price: continue
                    
                    size = float(pos['size'])
                    position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                    
                    # ตรวจสอบเงื่อนไขการปิด position
                    if self.check_close_position_signal(channel_data, position_type, last_price):
                        self.close_position(contract, pos)
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสแกน positions: {str(e)}", flush=True)
        
    def scan_market(self):
        """สแกนตลาดเพื่อหาโอกาสในการเทรดตามเงื่อนไขใหม่"""
        first_run = True
        while True:
            current_time = pd.Timestamp.now(tz='Asia/Bangkok')
            if current_time.minute % 15 == 0 or first_run:
                print(f"เริ่มสแกนตลาด ณ เวลา {current_time}", flush=True)
                first_run = False
                
                # สแกน positions ที่มีอยู่เพื่อปิดตามเงื่อนไข
                self.scan_positions()
                
                # ดึงรายการสัญญาที่มีสภาพคล่องดี
                contracts = self.get_futures_contracts()
                
                # สแกนทุกสัญญาเพื่อตรวจหาสัญญาณการเทรดใหม่
                for contract in contracts:
                    df = self.get_candlesticks(contract)
                    if df.empty: continue
                    
                    channel_data = self.calculate_linear_regression_channel(df)
                    if not channel_data: continue
                    
                    # ตรวจหาสัญญาณการเทรด
                    signal = self.check_trading_signal(channel_data)
                    existing_pos = self.check_existing_position(contract)
                    
                    if signal == "BUY":
                        # ถ้ามี position short ให้ปิดก่อน
                        if existing_pos and float(existing_pos['size']) < 0:
                            if self.close_position(contract, existing_pos):
                                self.create_long_order(contract)
                        # ถ้าไม่มี position ให้เปิด long เลย
                        elif not existing_pos:
                            self.create_long_order(contract)
                    
                    elif signal == "SELL":
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
    trader = GateIOLinearRegressionTrader()
    print("เริ่มต้นระบบสแกนตลาด Futures ด้วย Linear Regression Channel...", flush=True)
    trader.scan_market()

if __name__ == "__main__":
    main()