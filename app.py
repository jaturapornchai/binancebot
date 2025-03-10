import os
import time
import re
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from datetime import datetime, timezone


class GateIOLRC15mScanner:
    def __init__(self):
        # โหลดข้อมูลจากไฟล์ .env
        load_dotenv()
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key:
            raise ValueError("กรุณาตั้งค่า GATEIO_API_KEY และ GATEIO_SECRET_KEY ในไฟล์ .env")
        
        # ตั้งค่า API client
        self.client = ApiClient(Configuration(
            key=self.api_key,
            secret=self.secret_key,
            host="https://api.gateio.ws/api/v4"
        ))
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5  # ค่าเลเวอเรจเริ่มต้น
        self.order_amount = 40  # ขนาดคำสั่งเริ่มต้น
        self.lrc_length = 100  # ความยาวของ LRC
        self.dev_multiplier = 2.0  # ตัวคูณส่วนเบี่ยงเบน
        self.settle = 'usdt'  # สกุลเงินสำหรับการชำระ

    def get_futures_contracts(self) -> list:
        # ดึงรายการสัญญาฟิวเจอร์ส
        try:
            tickers = self.futures_api.list_futures_tickers(settle='usdt')
            valid_contracts = []
            pattern = re.compile(r'^\D+_USDT$')
            ignore_contracts = ['DOGS_USDT', 'USDC_USDT', 'HEI_USDT']
            
            for ticker in tickers:
                contract = ticker.contract
                if (pattern.match(contract) and
                    contract not in ignore_contracts and
                    float(ticker.volume_24h) * float(ticker.last) > 1000000):
                    valid_contracts.append(contract)
            # สุ่มลำดับของสัญญา
            np.random.shuffle(valid_contracts)
            return valid_contracts
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงสัญญา: {str(e)}", flush=True)
            return []

    def get_candlesticks(self, contract: str, limit: int = 100) -> pd.DataFrame:
        # ดึงข้อมูลแท่งเทียน
        try:
            candles = self.futures_api.list_futures_candlesticks(
                settle='usdt',
                contract=contract,
                interval='15m',
                limit=limit
            )
            if not candles:
                return pd.DataFrame()
                
            df = pd.DataFrame([{
                'timestamp': float(c.t),
                'open': float(c.o),
                'high': float(c.h),
                'low': float(c.l),
                'close': float(c.c),
                'volume': float(c.v)
            } for c in candles])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            return df.sort_values('timestamp')
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงแท่งเทียนสำหรับ {contract}: {str(e)}", flush=True)
            return pd.DataFrame()

    def calculate_lrc(self, df: pd.DataFrame) -> pd.DataFrame:
        # คำนวณ Linear Regression Channel
        if len(df) < self.lrc_length:
            return df
        
        prices = df['close'].values
        x = np.arange(len(prices))
        
        # คำนวณการถดถอยเชิงเส้น
        A = np.vstack([x, np.ones(len(x))]).T
        slope, intercept = np.linalg.lstsq(A, prices, rcond=None)[0]
        
        # คำนวณเส้นกลาง
        mid_line = intercept + slope * x
        deviations = prices - mid_line
        std_dev = np.std(deviations) * self.dev_multiplier
        
        # คำนวณสามเส้น: บน (T), กลาง (C), ล่าง (B)
        df['lrc_top'] = mid_line + std_dev      # T
        df['lrc_bottom'] = mid_line - std_dev   # B
        df['lrc_center'] = mid_line             # C
        
        return df.tail(1)

    def check_trading_signal(self, df: pd.DataFrame, current_price: float) -> str:
        # ตรวจสอบสัญญาณการซื้อขาย
        if df.empty:
            return None
            
        latest = df.iloc[-1]
        
        # ตรวจสอบประเภทของแท่งเทียน (Bullish/Bearish)
        is_bullish = latest['close'] > latest['open']
        is_bearish = latest['close'] < latest['open']
        
        # สัญญาณ LONG:
        # - แท่งเทียนสูงสุดแตะเส้นบนพอดี
        # - ต้องเป็นแท่งเทียนขาขึ้น (Bullish Candle)
        # - ราคาล่าสุดสูงกว่าเส้นบน
        if (abs(latest['high'] - latest['lrc_top']) < 0.0001 and
            is_bullish and
            current_price > latest['lrc_top']):
            return "LONG"
            
        # สัญญาณ SHORT:
        # - แท่งเทียนต่ำสุดแตะเส้นล่างพอดี
        # - ต้องเป็นแท่งเทียนขาลง (Bearish Candle)
        # - ราคาล่าสุดต่ำกว่าเส้นล่าง
        if (abs(latest['low'] - latest['lrc_bottom']) < 0.0001 and
            is_bearish and
            current_price < latest['lrc_bottom']):
            return "SHORT"
            
        return None

    def check_close_position(self, df: pd.DataFrame, position_type: str, current_price: float, position: dict) -> bool:
        # ตรวจสอบเงื่อนไขการปิดสถานะ
        if df.empty:
            return False
            
        latest = df.iloc[-1]
        
        # ปิด LONG ถ้าราคาต่ำกว่าเส้นกลาง
        if position_type == "LONG" and current_price < latest['lrc_center']:
            return True
            
        # ปิด SHORT ถ้าราคาสูงกว่าเส้นกลาง
        if position_type == "SHORT" and current_price > latest['lrc_center']:
            return True
            
        return False

    def set_leverage(self, contract: str) -> bool:
        # ตั้งค่าเลเวอเรจ
        try:
            self.futures_api.update_position_leverage(
                contract=contract,
                settle='usdt',
                leverage=str(self.leverage)
            )
            return True
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการตั้งค่าเลเวอเรจ: {str(e)}", flush=True)
            return False

    def get_latest_price(self, contract: str) -> float:
        # ดึงราคาล่าสุด
        try:
            ticker = self.futures_api.list_futures_tickers(settle='usdt')
            return float(next(t.last for t in ticker if t.contract == contract))
        except Exception:
            return None

    def check_existing_position(self, contract: str) -> dict:
        # ตรวจสอบสถานะที่มีอยู่
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            return next((p for p in positions if p['contract'] == contract), None)
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการตรวจสอบสถานะ: {str(e)}", flush=True)
            return None

    def close_position(self, contract: str, position: dict) -> bool:
        # ปิดสถานะ
        try:
            if not position:
                return False
                
            size = float(position['size'])
            if size != 0:
                self.futures_api.create_futures_order('usdt', {
                    'contract': contract,
                    'size': -size,
                    'price': 0,
                    'tif': 'ioc',
                    'reduce_only': True
                })
                print(f"ปิดสถานะสำหรับ {contract} (ขนาด: {abs(size)})", flush=True)
                return True
            return False
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการปิดสถานะ: {str(e)}", flush=True)
            return False

    def create_order(self, contract: str, size: float, is_long: bool) -> dict:
        # สร้างคำสั่งซื้อขาย
        try:
            existing = self.check_existing_position(contract)
            position_type = "LONG" if is_long else "SHORT"
            
            if existing:
                current_size = float(existing['size'])
                # ถ้ามีสถานะตรงข้ามอยู่ ให้ปิดก่อน
                if (is_long and current_size < 0) or (not is_long and current_size > 0):
                    self.close_position(contract, existing)
                    time.sleep(2)
                # ถ้ามีสถานะทิศทางเดียวกันอยู่แล้ว ให้ข้าม
                elif (is_long and current_size > 0) or (not is_long and current_size < 0):
                    return None

            if not self.set_leverage(contract):
                return None
                
            price = self.get_latest_price(contract)
            contract_info = self.futures_api.get_futures_contract(
                contract=contract,
                settle='usdt'
            )
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            
            usd_value = size * self.leverage
            contract_size = max(min_size, round(usd_value / (price * multiplier)))
            
            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract,
                'size': contract_size if is_long else -contract_size,
                'price': 0,
                'tif': 'ioc',
                'reduce_only': False
            })
            print(f"เปิดสถานะ {position_type} สำหรับ {contract}", flush=True)
            return order
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสร้างคำสั่ง: {str(e)}", flush=True)
            return None

    def scan_positions(self):
        # สแกนสถานะที่เปิดอยู่
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            for pos in positions:
                contract = pos['contract']
                print(f"กำลังสแกนสถานะสำหรับ {contract}...", flush=True)
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df['contract'] = contract
                    df = self.calculate_lrc(df)
                    current_price = self.get_latest_price(contract)
                    
                    if current_price:
                        pos_type = "LONG" if float(pos['size']) > 0 else "SHORT"
                        if self.check_close_position(df, pos_type, current_price, pos):
                            self.close_position(contract, pos)
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสแกนสถานะ: {str(e)}", flush=True)

    def get_futures_balance(self) -> dict:
        # ดึงข้อมูลยอดเงินในบัญชีฟิวเจอร์ส
        try:
            account = self.futures_api.list_futures_accounts(settle=self.settle)
            if not account:
                raise ValueError("ไม่พบบัญชีฟิวเจอร์ส")
            balance_info = {
                'total': float(account.total or 0),
                'available': float(account.available or 0),
                'unrealized_pnl': float(account.unrealised_pnl or 0),
                'currency': account.currency or self.settle,
            }
            return balance_info
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงยอดเงิน: {str(e)}", flush=True)
            return None

    def scan_market(self):
        # สแกนตลาด
        first_run = True
        while True:
            try:
                now = datetime.now(timezone.utc)
                if now.minute % 15 == 0 or first_run:                  
                    first_run = False
                    self.scan_positions()
                    balance_info = self.get_futures_balance()
                    print(f"ยอดเงิน: {balance_info['total']} {balance_info['currency']} | "
                          f"ใช้ได้: {balance_info['available']} {balance_info['currency']} | "
                          f"กำไร/ขาดทุนที่ยังไม่รับรู้: {balance_info['unrealized_pnl']} {balance_info['currency']}", flush=True)
                    self.order_amount = balance_info['total'] / 75
                    print(f"ขนาดคำสั่ง: {self.order_amount}", flush=True)
                    
                    contracts = self.get_futures_contracts()
                    
                    for contract in contracts:
                        df = self.get_candlesticks(contract)
                        if not df.empty:
                            df = self.calculate_lrc(df)
                            current_price = self.get_latest_price(contract)
                            signal = self.check_trading_signal(df, current_price)
                            
                            if signal == "LONG":
                                self.create_order(contract, self.order_amount, True)
                            elif signal == "SHORT":
                                self.create_order(contract, self.order_amount, False)
                            
                            latest = df.iloc[-1]
                            print(f"{contract} | ปิด: {latest['close']} | "
                                  f"บน: {latest['lrc_top']} | "
                                  f"กลาง: {latest['lrc_center']} | "
                                  f"ล่าง: {latest['lrc_bottom']} | "
                                  f"สัญญาณ: {signal or 'ไม่มี'}", flush=True)
                    time.sleep(60)
                else:
                    if now.minute % 3 == 0:
                        if now.minute % 15 == 0:
                            first_run = True
                        else:
                            self.scan_positions()
                            time.sleep(60)
                time.sleep(10)
                
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในวงจรสแกน: {str(e)}", flush=True)
                time.sleep(60)


def main():
    # ฟังก์ชันหลัก
    scanner = GateIOLRC15mScanner()
    print("เริ่มสแกนเนอร์ฟิวเจอร์ส LRC 15 นาที...", flush=True)
    scanner.scan_market()


if __name__ == "__main__":
    main()