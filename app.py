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
    
    def calculate_linear_regression_channel(self, df: pd.DataFrame) -> pd.DataFrame:
        """คำนวณ Linear Regression Channel ตามวิธีใน TradingView"""
        if len(df) < self.lookback_period: 
            print(f"ข้อมูลไม่เพียงพอ ต้องการอย่างน้อย {self.lookback_period} แท่ง แต่มีเพียง {len(df)} แท่ง", flush=True)
            return pd.DataFrame()
            
        # ใช้เฉพาะข้อมูล lookback_period ล่าสุด
        df = df.iloc[-self.lookback_period:].copy().reset_index(drop=True)
        
        # สร้าง x และ y สำหรับการคำนวณ
        x = np.arange(len(df))
        y = df['close'].values
        
        # คำนวณเส้น Linear Regression
        slope, intercept = np.polyfit(x, y, 1)
        
        # คำนวณจุดเริ่มต้นและจุดสิ้นสุดของเส้นกลาง
        start_middle = intercept
        end_middle = intercept + slope * (len(df) - 1)
        
        # คำนวณค่าเบี่ยงเบนมาตรฐาน
        y_pred = intercept + slope * x
        dev = np.sqrt(np.sum((y - y_pred) ** 2) / len(df))
        
        # คำนวณเส้นบนและเส้นล่างของ channel
        start_upper = start_middle + dev * self.deviation
        end_upper = end_middle + dev * self.deviation
        start_lower = start_middle - dev * self.deviation
        end_lower = end_middle - dev * self.deviation
        
        print(f"Linear Regression ค่าที่คำนวณได้: slope={slope:.6f}, intercept={intercept:.6f}, dev={dev:.6f}", flush=True)
        print(f"จุดของเส้นกลาง: เริ่มต้น={start_middle:.4f}, สิ้นสุด={end_middle:.4f}", flush=True)
        print(f"จุดของเส้นบน: เริ่มต้น={start_upper:.4f}, สิ้นสุด={end_upper:.4f}", flush=True)
        print(f"จุดของเส้นล่าง: เริ่มต้น={start_lower:.4f}, สิ้นสุด={end_lower:.4f}", flush=True)
        
        # คำนวณค่าเส้นสำหรับแท่งเทียนล่าสุด (แท่งสุดท้าย)
        latest_middle = end_middle
        latest_upper = end_upper
        latest_lower = end_lower
        
        # เพิ่มข้อมูลเข้าไปใน DataFrame
        df_result = df.copy()
        df_result['middle_line'] = intercept + slope * x
        df_result['upper_line'] = df_result['middle_line'] + dev * self.deviation
        df_result['lower_line'] = df_result['middle_line'] - dev * self.deviation
        
        # เพิ่มค่าล่าสุดสำหรับใช้ในการตัดสินใจ
        latest_candle = df_result.iloc[-1].copy()
        latest_candle['latest_middle_line'] = latest_middle
        latest_candle['latest_upper_line'] = latest_upper
        latest_candle['latest_lower_line'] = latest_lower
        
        return latest_candle
    
    def check_trading_signal(self, candle: pd.Series, last_price: float) -> str:
        """ตรวจสอบสัญญาณการซื้อขายตามเงื่อนไขที่กำหนด"""
        if candle.empty: return None
        
        # ตรวจสอบว่าแท่งล่าสุดอยู่ที่เส้นบนหรือเส้นล่างหรือไม่
        touches_upper_line = (candle['high'] >= candle['latest_upper_line'] and candle['low'] <= candle['latest_upper_line'])
        touches_lower_line = (candle['high'] >= candle['latest_lower_line'] and candle['low'] <= candle['latest_lower_line'])
        
        is_green_candle = candle['candle_color'] == 1
        is_red_candle = candle['candle_color'] == 0
        
        # เงื่อนไขการเกิดสัญญาณ BUY
        # BUY=CANDLE เป็นสีเขียว และ ((CANDLE ทับเส้นล่าง และ LAST PRICE สูงกว่าเส้นล่าง) หรือ (CANDLE ทับเส้นบน และ LAST PRICE สูงกว่าเส้นบน))
        if is_green_candle and ((touches_lower_line and last_price > candle['latest_lower_line']) or 
                               (touches_upper_line and last_price > candle['latest_upper_line'])):
            print(f"สัญญาณ BUY: แท่งเขียว, แท่งทับเส้น, ราคาล่าสุด={last_price:.4f}, เส้นบน={candle['latest_upper_line']:.4f}, เส้นล่าง={candle['latest_lower_line']:.4f}", flush=True)
            return "BUY"
        
        # เงื่อนไขการเกิดสัญญาณ SELL
        # SELL=CANDLE เป็นสีแดง และ ((CANDLE ทับเส้นบน และ LAST PRICE ต่ำกว่าเส้นบน) หรือ (CANDLE ทับเส้นล่าง และ LAST PRICE ต่ำกว่าเส้นล่าง))
        if is_red_candle and ((touches_upper_line and last_price < candle['latest_upper_line']) or 
                             (touches_lower_line and last_price < candle['latest_lower_line'])):
            print(f"สัญญาณ SELL: แท่งแดง, แท่งทับเส้น, ราคาล่าสุด={last_price:.4f}, เส้นบน={candle['latest_upper_line']:.4f}, เส้นล่าง={candle['latest_lower_line']:.4f}", flush=True)
            return "SELL"
        
        print(f"ไม่พบสัญญาณซื้อขาย: แท่ง{'เขียว' if is_green_candle else 'แดง'}, ทับเส้นบน={touches_upper_line}, ทับเส้นล่าง={touches_lower_line}, ราคาล่าสุด={last_price:.4f}", flush=True)
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
                    latest_candle = self.calculate_linear_regression_channel(df)
                    if latest_candle.empty: continue
                    
                    # ดึงราคาล่าสุด
                    last_price = self.get_latest_price(contract)
                    if not last_price: continue
                    
                    # ตรวจสอบสัญญาณซื้อขาย
                    signal = self.check_trading_signal(latest_candle, last_price)
                    size = float(pos['size'])
                    
                    # ปิด long position ถ้า position เป็น long และมีสัญญาณ SELL
                    if size > 0 and signal == "SELL":
                        print(f"สัญญาณปิด LONG: {contract} เนื่องจากได้รับสัญญาณ SELL", flush=True)
                        self.close_position(contract, pos)
                    
                    # ปิด short position ถ้า position เป็น short และมีสัญญาณ BUY
                    if size < 0 and signal == "BUY":
                        print(f"สัญญาณปิด SHORT: {contract} เนื่องจากได้รับสัญญาณ BUY", flush=True)
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
                    
                    latest_candle = self.calculate_linear_regression_channel(df)
                    if latest_candle.empty: continue
                    
                    # ดึงราคาล่าสุด
                    last_price = self.get_latest_price(contract)
                    if not last_price: continue
                    
                    # ตรวจหาสัญญาณการเทรด
                    signal = self.check_trading_signal(latest_candle, last_price)
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