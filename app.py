import os
import time
import re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
class GateIOShortScanner:
    def __init__(self):
        load_dotenv() #โหลดตัวแปรจาก .env
        self.api_key = os.getenv('GATEIO_API_KEY') #ดึง API key
        self.secret_key = os.getenv('GATEIO_SECRET_KEY') #ดึง Secret key
        if not self.api_key or not self.secret_key: raise ValueError("ต้องกำหนด GATEIO_API_KEY และ GATEIO_SECRET_KEY ใน .env") #ตรวจสอบ key
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4") #ตั้งค่า API
        self.client = ApiClient(config) #สร้าง client
        self.futures_api = FuturesApi(self.client) #เชื่อมต่อ Futures API
        self.leverage = 5 #กำหนด leverage 5 เท่า
        self.order_amount = 20 #ขนาดออเดอร์ 20 USD
        self.lookback_period = 100 #ระยะย้อนหลัง 100 แท่ง
    def get_futures_contracts(self) -> List[str]:
        ticket = self.futures_api.list_futures_tickers(settle='usdt') #ดึงรายชื่อ futures
        valid_contracts = [] #ลิสต์เก็บสัญญาที่ผ่านเงื่อนไข
        pattern = re.compile(r'^\D+_USDT$') #pattern ชื่อสัญญา
        for contract in ticket: #วนลูปทุกสัญญา
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']: #กรอง _USDT ไม่เอา USDC, DOGS
                json_data = contract.to_dict() #แปลงเป็น dict
                if float(json_data['volume_24h']) * float(json_data['last']) > 500000: #volume > 500,000 USD
                    valid_contracts.append(contract.contract) #เพิ่มสัญญา
        return valid_contracts #คืนลิสต์สัญญา
    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='5m', limit=500) #ดึงแท่งเทียน 5 นาที 500 แท่ง
        if not candles: return pd.DataFrame() #ถ้าไม่มีข้อมูล คืนว่าง
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles] #แปลงข้อมูล
        df = pd.DataFrame(data) #สร้าง DataFrame
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s') #แปลง timestamp
        return df.sort_values('timestamp') #เรียงตามเวลา
    def calculate_linear_regression(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.lookback_period: return df #ถ้าข้อมูลน้อยเกิน คืนเดิม
        def calc_lr(values): #ฟังก์ชันคำนวณ LR
            x = np.arange(len(values)) #array index
            slope, intercept = np.polyfit(x, values, 1) #คำนวณ slope, intercept
            return slope * (self.lookback_period - 1) + intercept #ค่าสุดท้ายของเส้น
        df['middle_line'] = df['close'].rolling(window=self.lookback_period).apply(calc_lr, raw=True) #เส้นกลาง
        df['dev'] = df['close'].rolling(window=self.lookback_period).std() * 2 #deviation 2SD
        df['upper_line'] = df['middle_line'] + df['dev'] #เส้นบน
        df['lower_line'] = df['middle_line'] - df['dev'] #เส้นล่าง
        return df.dropna() #ลบ NaN
    def check_trading_signal(self, df: pd.DataFrame) -> str:
        if len(df) < 2: return None #ถ้าน้อยกว่า 2 แท่ง คืน None
        current = df.iloc[-1] #แท่งล่าสุด
        previous = df.iloc[-2] #แท่งก่อนหน้า
        if previous['high'] >= previous['upper_line'] and current['close'] < current['upper_line']: return "SELL" #SELL: ทะลุเส้นบนและต่ำกว่า
        if previous['low'] <= previous['lower_line'] and current['close'] > current['lower_line']: return "BUY" #BUY: ทะลุเส้นล่างและสูงกว่า
        return None #ไม่มีสัญญาณ
    def set_leverage(self, contract: str) -> bool:
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage)) #ตั้ง leverage
            return True #สำเร็จ
        except Exception as e:
            print(f"ตั้ง leverage ไม่ได้: {str(e)}", flush=True) #ผิดพลาด
            return False
    def get_latest_price(self, contract: str) -> float:
        ticker = self.futures_api.list_futures_tickers(settle='usdt') #ดึง ticker
        for t in ticker: #หาสัญญา
            if t.contract == contract: return float(t.last) #คืนราคาล่าสุด
        return None #ไม่พบ
    def check_existing_position(self, contract: str) -> Dict:
        positions = self.futures_api.list_positions(settle='usdt', holding=True) #ดึง position
        for p in positions: #วนลูป
            if p.contract == contract: return p.to_dict() #พบ position
        return None #ไม่พบ
    def close_position(self, contract: str, position: Dict) -> bool:
        try:
            size = float(position['size']) #ขนาด position
            if size < 0: #ถ้าเป็น Short
                self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': abs(size), 'price': 0, 'tif': 'ioc', 'reduce_only': True}) #ปิด Short
                print(f"ปิด Short Position {contract} ขนาด {abs(size)}", flush=True) #แจ้งปิด
                return True #สำเร็จ
            return False #ไม่ใช่ Short
        except Exception as e:
            print(f"ปิด Position ไม่ได้: {str(e)}", flush=True) #ผิดพลาด
            return False
    def create_short_order(self, contract: str) -> Dict:
        try:
            if not self.set_leverage(contract): return None #ตั้ง leverage
            price = self.get_latest_price(contract) #ราคาล่าสุด
            if not price: return None #ไม่มีราคา
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt') #ข้อมูลสัญญา
            multiplier = float(contract_info.to_dict()['quanto_multiplier']) #ตัวคูณ
            min_size = float(contract_info.to_dict()['order_size_min']) #ขนาดขั้นต่ำ
            usd_value = self.order_amount * self.leverage #มูลค่า USD
            size = max(min_size, round(usd_value / (price * multiplier))) #คำนวณ size
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': -size, 'price': 0, 'tif': 'ioc', 'reduce_only': False}) #เปิด Short
            print(f"เปิด Short Position: {contract} ขนาด {size}", flush=True) #แจ้งเปิด
            return order #คืนออเดอร์
        except Exception as e:
            print(f"เปิด Short ไม่ได้: {str(e)}", flush=True) #ผิดพลาด
            return None
    def scan_positions(self):
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)] #ดึง position
            for pos in positions: #วนลูป position
                contract = pos['contract'] #ชื่อสัญญา
                df = self.get_candlesticks(contract) #ดึงแท่งเทียน
                if not df.empty: #ถ้ามีข้อมูล
                    df = self.calculate_linear_regression(df) #คำนวณ LR
                    signal = self.check_trading_signal(df) #ตรวจสัญญาณ
                    current = df.iloc[-1] #แท่งล่าสุด
                    if float(pos['size']) < 0 and (signal == "BUY" or current['close'] > current['upper_line']): #ถ้า Short และ (สัญญาณ BUY หรือ ราคา > เส้นบน)
                        print(f"ตรวจพบสัญญาณปิด Short: {contract}", flush=True) #แจ้งปิด
                        self.close_position(contract, pos) #ปิด Short
                    print(f"Position: {contract:12} | Size: {abs(float(pos['size'])):8.4f} | Entry: {float(pos['entry_price']):10.4f} | PNL: {float(pos['unrealised_pnl']):10.4f}", flush=True) #แสดง position
        except Exception as e:
            print(f"สแกน position ผิดพลาด: {str(e)}", flush=True) #ผิดพลาด
    def scan_market(self):
        first_run = True #รอบแรก
        while True: #วนลูปตลอด
            current_time = pd.Timestamp.now(tz='Asia/Bangkok') #เวลาไทย
            if current_time.minute % 5 == 0 or first_run: #ทุก 5 นาทีหรือรอบแรก
                first_run = False #ไม่ใช่รอบแรก
                self.scan_positions() #สแกน position
                contracts = self.get_futures_contracts() #ดึงสัญญา
                print(f"พบ {len(contracts)} คู่เทรด", flush=True) #แสดงจำนวน
                for contract in contracts: #วนลูปสัญญา
                    if self.check_existing_position(contract): continue #มี position ข้าม
                    df = self.get_candlesticks(contract) #ดึงแท่งเทียน
                    if not df.empty: #ถ้ามีข้อมูล
                        df = self.calculate_linear_regression(df) #คำนวณ LR
                        signal = self.check_trading_signal(df) #ตรวจสัญญาณ
                        if signal == "SELL": #ถ้า SELL
                            self.create_short_order(contract) #เปิด Short
                        status = "🔴 SELL" if signal == "SELL" else "🟢 BUY" if signal == "BUY" else "" #สถานะ
                        print(f"{contract:12} | Close: {df.iloc[-1]['close']:10.4f} | Upper: {df.iloc[-1]['upper_line']:10.4f} | Lower: {df.iloc[-1]['lower_line']:10.4f} | {status}", flush=True) #แสดงข้อมูล
                time.sleep(30) 
            time.sleep(10) 
def main():
    scanner = GateIOShortScanner() #สร้าง scanner
    print("เริ่มสแกนตลาด Futures (Short เท่านั้น)...", flush=True) #แจ้งเริ่ม
    scanner.scan_market() #เริ่มสแกน
if __name__ == "__main__":
    main() #รันหลัก