import os
import time
import re
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from datetime import datetime, timezone

class GateIOLinearRegressionChannelScanner:
    def __init__(self):
        """Initialize the scanner with API credentials and default settings."""
        load_dotenv() # โหลดการตั้งค่าจากไฟล์ .env
        self.api_key = os.getenv('GATEIO_API_KEY') # ดึง API key จาก environment variables
        self.secret_key = os.getenv('GATEIO_SECRET_KEY') # ดึง Secret key จาก environment variables
        if not self.api_key or not self.secret_key:
            raise ValueError("Please set GATEIO_API_KEY and GATEIO_SECRET_KEY in .env file") # ตรวจสอบว่ามีการตั้งค่า API key และ Secret key
        
        # สร้าง API client เพื่อเชื่อมต่อกับ Gate.io
        self.client = ApiClient(Configuration(
            key=self.api_key,
            secret=self.secret_key,
            host="https://api.gateio.ws/api/v4"
        ))
        self.futures_api = FuturesApi(self.client) # สร้าง object สำหรับใช้งาน Futures API
        
        # ตั้งค่าพารามิเตอร์เริ่มต้น
        self.leverage = 5 # ค่าเลเวอเรจที่ใช้ในการเทรด
        self.order_amount = 40 # จำนวนเงินที่ใช้ในการเปิด order
        self.len = 100 # จำนวนแท่งเทียนที่ใช้ในการคำนวณ Linear Regression
        self.devlen = 2.0 # ระยะห่างของเส้น deviation
        self.settle = 'usdt' # สกุลเงินที่ใช้ในการเทรด
        self.timeframe = '5m' # เปลี่ยนเป็น timeframe 5 นาทีตามที่ต้องการ

    def get_futures_contracts(self) -> list:
        """Retrieve a list of valid futures contracts with sufficient volume."""
        try:
            tickers = self.futures_api.list_futures_tickers(settle='usdt') # ดึงข้อมูล tickers ทั้งหมด
            valid_contracts = []
            pattern = re.compile(r'^\D+_USDT$') # รูปแบบเพื่อตรวจสอบสัญญาที่ถูกต้อง
            ignore_contracts = ['DOGS_USDT', 'USDC_USDT', 'HEI_USDT'] # สัญญาที่ต้องการข้าม
            
            for ticker in tickers:
                contract = ticker.contract
                # ตรวจสอบว่าเป็นสัญญาที่ถูกต้องและมีปริมาณการซื้อขายเพียงพอ
                if (pattern.match(contract) and
                    contract not in ignore_contracts and
                    float(ticker.volume_24h) * float(ticker.last) > 1000000):
                    valid_contracts.append(contract)
            np.random.shuffle(valid_contracts) # สลับลำดับสัญญาแบบสุ่ม
            return valid_contracts
        except Exception as e:
            print(f"Error fetching contracts: {str(e)}", flush=True)
            return []

    def get_candlesticks(self, contract: str, limit: int = 100) -> pd.DataFrame:
        """Fetch candlestick data for a given contract."""
        try:
            candles = self.futures_api.list_futures_candlesticks(
                settle='usdt',
                contract=contract,
                interval=self.timeframe, # ใช้ timeframe ที่กำหนดในคลาส (5m)
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
            print(f"Error fetching candlesticks for {contract}: {str(e)}", flush=True)
            return pd.DataFrame()

    def get_linear_regression_channel(self, df: pd.DataFrame) -> dict:
        """Calculate the Linear Regression Channel for the given data."""
        if len(df) < self.len:
            return None
        
        src = df['close'].tail(self.len).values # ใช้ราคาปิดสำหรับการคำนวณ
        x = np.arange(self.len)
        slope, intercept = np.polyfit(x, src, 1) # คำนวณ slope และ intercept ของเส้น Linear Regression
        endy = intercept + slope * (self.len - 1) # คำนวณค่า y ที่จุดสุดท้าย
        residuals = src - (slope * x + intercept) # คำนวณค่าคลาดเคลื่อน
        dev = np.std(residuals) # คำนวณค่าเบี่ยงเบนมาตรฐานของค่าคลาดเคลื่อน
        
        T = endy + dev * self.devlen # เส้นบนของช่อง Linear Regression
        B = endy - dev * self.devlen # เส้นล่างของช่อง Linear Regression
        
        return {'T': T, 'B': B, 'slope': slope}

    def check_buy_signal(self, df: pd.DataFrame, channel: dict) -> bool:
        """Check if there is a Buy Lin Reg signal (crossunder close, lower regression channel)."""
        if len(df) < 2:
            return False
        
        # คำนวณค่าปัจจุบันและก่อนหน้าของเส้นล่าง
        current_dm = channel['B']
        
        # ตรวจสอบว่าราคาปิดข้ามเส้นล่างจากล่างขึ้นบน (crossunder)
        prev_close = df['close'].iloc[-2]
        current_close = df['close'].iloc[-1]
        
        return prev_close < current_dm and current_close > current_dm

    def check_sell_signal(self, df: pd.DataFrame, channel: dict) -> bool:
        """Check if there is a Sell Lin Reg signal (crossover close, upper regression channel)."""
        if len(df) < 2:
            return False
        
        # คำนวณค่าปัจจุบันและก่อนหน้าของเส้นบน
        current_dp = channel['T']
        
        # ตรวจสอบว่าราคาปิดข้ามเส้นบนจากบนลงล่าง (crossover)
        prev_close = df['close'].iloc[-2]
        current_close = df['close'].iloc[-1]
        
        return prev_close > current_dp and current_close < current_dp

    def set_leverage(self, contract: str) -> bool:
        """Set leverage for a specific contract."""
        try:
            self.futures_api.update_position_leverage(
                contract=contract,
                settle='usdt',
                leverage=str(self.leverage)
            )
            return True
        except Exception as e:
            print(f"Error setting leverage: {str(e)}", flush=True)
            return False

    def get_latest_price(self, contract: str) -> float:
        """Get the latest price for a contract."""
        try:
            ticker = self.futures_api.list_futures_tickers(settle='usdt')
            return float(next(t.last for t in ticker if t.contract == contract))
        except Exception:
            return None

    def check_existing_position(self, contract: str) -> dict:
        """Check if there is an existing position for a contract."""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            return next((p for p in positions if p['contract'] == contract), None)
        except Exception as e:
            print(f"Error checking position: {str(e)}", flush=True)
            return None

    def close_position(self, contract: str, position: dict) -> bool:
        """Close an existing position for a contract."""
        try:
            if not position:
                return False
            
            size = float(position['size'])
            if size != 0:
                self.futures_api.create_futures_order('usdt', {
                    'contract': contract,
                    'size': -size, # ขนาดตรงข้ามเพื่อปิด position
                    'price': 0, # ใช้ราคาตลาด
                    'tif': 'ioc', # Immediate or Cancel
                    'reduce_only': True # ใช้เพื่อปิด position เท่านั้น
                })
                print(f"Closed position for {contract} (size: {abs(size)})", flush=True)
                return True
            return False
        except Exception as e:
            print(f"Error closing position: {str(e)}", flush=True)
            return False

    def create_order(self, contract: str, size: float, is_long: bool) -> dict:
        """Create a new futures order."""
        try:
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
                'size': contract_size if is_long else -contract_size, # ค่าบวกสำหรับ long, ค่าลบสำหรับ short
                'price': 0, # ใช้ราคาตลาด
                'tif': 'ioc', # Immediate or Cancel
                'reduce_only': False # สามารถเปิด position ใหม่ได้
            })
            print(f"Opened {'LONG' if is_long else 'SHORT'} position for {contract}", flush=True)
            return order
        except Exception as e:
            print(f"Error creating order: {str(e)}", flush=True)
            return None

    def scan_positions(self):
        """Scan and manage existing positions based on channel conditions."""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            # เรียงลำดับตามชื่อสัญญา
            positions = sorted(positions, key=lambda x: x['contract'])
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                if not df.empty and len(df) >= self.len:
                    channel = self.get_linear_regression_channel(df)
                    if channel:
                        latest_price = self.get_latest_price(contract)
                        pos_size = float(pos['size'])
                        
                        # ตรวจสอบสัญญาณ Buy Lin Reg
                        buy_signal = self.check_buy_signal(df, channel)
                        
                        # ถ้า position เป็น short และ (เกิดสัญญาณ Buy Lin Reg หรือ ราคาปัจจุบันสูงกว่าเส้นบน) ให้ปิด position
                        if pos_size < 0 and (buy_signal or latest_price > channel['T']):
                            if buy_signal:
                                print(f"Closing SHORT position for {contract}: Buy Lin Reg signal detected", flush=True)
                            else:
                                print(f"Closing SHORT position for {contract}: Price {latest_price:.4f} > T {channel['T']:.4f}", flush=True)
                            self.close_position(contract, pos)
                        # กรณี Long position ยังคงปิดตามเงื่อนไขเดิม
                        elif pos_size > 0 and latest_price < channel['B']:
                            print(f"Closing LONG position for {contract}: Price {latest_price:.4f} < B {channel['B']:.4f}", flush=True)
                            self.close_position(contract, pos)
        except Exception as e:
            print(f"Error scanning positions: {str(e)}", flush=True)
        print("Position scan completed", flush=True)
        print("", flush=True)

    def get_futures_balance(self) -> dict:
        """Retrieve the current futures account balance."""
        try:
            account = self.futures_api.list_futures_accounts(settle=self.settle)
            if not account:
                raise ValueError("No futures account found")
            balance_info = {
                'total': float(account.total or 0),
                'available': float(account.available or 0),
                'unrealized_pnl': float(account.unrealised_pnl or 0),
                'currency': account.currency or self.settle,
            }
            return balance_info
        except Exception as e:
            print(f"Error fetching futures balance: {str(e)}", flush=True)
            return None

    def scan_market(self):
        """Main loop to scan the market and execute trades."""
        first_run = True
        while True:
            try:
                now = datetime.now(timezone.utc)
                if now.minute % 5 == 0 or first_run:  # ปรับให้ตรวจสอบทุก 5 นาทีตาม timeframe
                    first_run = False
                    self.scan_positions()
                    balance_info = self.get_futures_balance()
                    print(f"Balance: {balance_info['total']} {balance_info['currency']} | "
                          f"Available: {balance_info['available']} {balance_info['currency']} | "
                          f"Unrealized PNL: {balance_info['unrealized_pnl']} {balance_info['currency']}", flush=True)
                    self.order_amount = balance_info['total'] / 100
                    print(f"Order amount: {self.order_amount}", flush=True)
                    
                    contracts = self.get_futures_contracts()
                    
                    for contract in contracts:
                        df = self.get_candlesticks(contract)
                        if not df.empty and len(df) >= self.len:
                            channel = self.get_linear_regression_channel(df)
                            if channel:
                                latest_price = self.get_latest_price(contract)
                                
                                # ตรวจจับสัญญาณ Sell Lin Reg
                                sell_signal = self.check_sell_signal(df, channel)
                                
                                # ใช้สัญญาณ Sell Lin Reg สำหรับเปิด SHORT position
                                if sell_signal:
                                    # ตรวจสอบ position ที่มีอยู่
                                    existing = self.check_existing_position(contract)
                                    
                                    # ถ้าเกิดสัญญาณ Sell Lin Reg ให้ตรวจดูว่ามี position short เดิมแล้วหรือไม่
                                    if not existing or (existing and float(existing['size']) >= 0):
                                        # ถ้าเป็น long ให้ปิดก่อน
                                        if existing and float(existing['size']) > 0:
                                            self.close_position(contract, existing)
                                            time.sleep(2)
                                        # เปิด short ใหม่
                                        self.create_order(contract, self.order_amount, False)
                                
                                # สำหรับ signal LONG ยังคงใช้ตามเงื่อนไขเดิม
                                if df['low'].iloc[-1] <= channel['B'] and df['close'].iloc[-1] < df['open'].iloc[-1] and latest_price < channel['B']:
                                    existing = self.check_existing_position(contract)
                                    if not existing or (existing and float(existing['size']) <= 0):
                                        if existing and float(existing['size']) < 0:
                                            self.close_position(contract, existing)
                                            time.sleep(2)
                                        self.create_order(contract, self.order_amount, True)
                                
                                print(f"{contract} | T: {channel['T']:.4f} | B: {channel['B']:.4f} | "
                                      f"Latest Price: {latest_price:.4f} | Sell Signal: {sell_signal}", flush=True)
                    time.sleep(60)
                time.sleep(10)
            except Exception as e:
                print(f"Error in scan loop: {str(e)}", flush=True)
                time.sleep(60)

def main():
    """Entry point to start the scanner."""
    scanner = GateIOLinearRegressionChannelScanner()
    print("Starting 5m Linear Regression Channel futures scanner...", flush=True)
    scanner.scan_market()

if __name__ == "__main__":
    main()