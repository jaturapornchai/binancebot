import os
import time
import re
from typing import List, Dict, Tuple
import pandas as pd
import numpy as np
from scipy import stats
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console


class GateIOLRCTradeBot:
    def __init__(self):
        # โหลดตัวแปรสภาพแวดล้อมจากไฟล์ .env
        load_dotenv()
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        
        # ตรวจสอบว่ามี API keys หรือไม่
        if not self.api_key or not self.secret_key:
            raise ValueError("ไม่พบ API keys กรุณาตั้งค่าในไฟล์ .env")
            
        # กำหนดค่าเริ่มต้นสำหรับ API
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        
        # ตัวแปรการตั้งค่า
        self.leverage = 5  # คูณเลเวอเรจ
        self.order_amount = 50  # จำนวนเงิน USD สำหรับแต่ละออเดอร์
        self.lookback_period = 100  # จำนวนแท่งเทียนย้อนหลังสำหรับ Linear Regression Channel
        self.devlen = 2.0  # ค่าเบี่ยงเบนมาตรฐานสำหรับช่อง
        self.console = Console()  # สำหรับแสดงผลในคอนโซล
        
    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญาที่มีสภาพคล่องเพียงพอ"""
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = []
        pattern = re.compile(r'^\D+_USDT$')
        
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                json_data = contract.to_dict()
                # ตรวจสอบสภาพคล่อง (Volume 24h > $500,000)
                if float(json_data['volume_24h']) * float(json_data['last']) > 500000:
                    valid_contracts.append(contract.contract)
                    
        self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา[/blue]")
        return valid_contracts
        
    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียน timeframe 1 ชั่วโมง"""
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='1h', limit=500)
        if not candles:
            return pd.DataFrame()
            
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h),
                'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')
    
    def calculate_linear_regression_channel(self, contract: str, df: pd.DataFrame) -> Tuple[pd.DataFrame, float]:
        """คำนวณ Linear Regression Channel โดยใช้วิธีทางสถิติตามสูตร TradingView"""
        if len(df) < self.lookback_period:
            return pd.DataFrame(), 0.0
            
        price = self.get_latest_price(contract)
        if price is None:
            return pd.DataFrame(), 0.0
            
        # ใช้ข้อมูลราคาปิด length ล่าสุด
        recent_df = df.tail(self.lookback_period).copy()
        prices = recent_df['close'].values
        
        # สร้างแกน x (เวลา)
        x = np.arange(len(prices))
        
        # คำนวณเส้นแนวโน้มด้วย Linear Regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, prices)
        
        # คำนวณจุดบนเส้นแนวโน้ม Linear Regression
        line_values = intercept + slope * x
        
        # คำนวณค่าความเบี่ยงเบนมาตรฐานของระยะห่างระหว่างราคาจริงกับเส้นแนวโน้ม
        distances = prices - line_values
        std_dev = np.std(distances)
        
        # คำนวณช่อง Linear Regression (เส้นบน, เส้นกลาง, เส้นล่าง)
        middle_line = intercept + slope * (len(prices) - 1)  # ค่าของเส้นแนวโน้มที่จุดล่าสุด
        upper_line = middle_line + std_dev * self.devlen
        lower_line = middle_line - std_dev * self.devlen
        
        # คำนวณเส้นกลางระหว่างเส้นบนกับเส้นกลาง และเส้นกลางกับเส้นล่าง
        tmid = (upper_line + middle_line) / 2
        bmid = (middle_line + lower_line) / 2
        
        # สร้าง DataFrame ผลลัพธ์
        result_df = df.tail(1).copy()
        result_df['MIDDLE'] = middle_line
        result_df['TOP'] = upper_line
        result_df['BOTTOM'] = lower_line
        result_df['TMID'] = tmid
        result_df['BMID'] = bmid
        
        # แสดงข้อมูลการคำนวณในคอนโซล
        self.console.print(f"[cyan]{contract}[/cyan] "
                        f"price={price:.6f}, "
                        f"slope={slope:.6f}, "
                        f"intercept={intercept:.6f}, "
                        f"std_dev={std_dev:.6f}, "
                        f"TOP={upper_line:.6f}, "
                        f"MIDDLE={middle_line:.6f}, "
                        f"BOTTOM={lower_line:.6f}, "
                        f"TMID={tmid:.6f}, "
                        f"BMID={bmid:.6f}")
                        
        return result_df, slope
        
    def check_trading_signal(self, df: pd.DataFrame, slope: float) -> str:
        """ตรวจสอบสัญญาณการเทรด"""
        if len(df) < 1:
            return None
            
        candle = df.iloc[-1]
        
        # ตรวจสอบสีของแท่งเทียน
        is_green = candle['close'] > candle['open']
        is_red = candle['close'] < candle['open']
        
        # ตรวจสอบว่าแท่งเทียนทะลุเส้นบนหรือเส้นล่าง
        high_above_top = candle['high'] > candle['TOP']
        low_below_bottom = candle['low'] < candle['BOTTOM']
        
        # สัญญาณ BUY: แท่งเทียนสีเขียว + ทะลุเส้นบน
        if is_green and high_above_top:
            self.console.print(f"[green]สัญญาณ BUY: แท่งเทียนสีเขียว (close={candle['close']:.6f} > open={candle['open']:.6f}) "
                            f"และทะลุเส้นบน (high={candle['high']:.6f} > TOP={candle['TOP']:.6f})[/green]")
            return "BUY"
            
        # สัญญาณ SELL: แท่งเทียนสีแดง + ทะลุเส้นล่าง
        elif is_red and low_below_bottom:
            self.console.print(f"[red]สัญญาณ SELL: แท่งเทียนสีแดง (close={candle['close']:.6f} < open={candle['open']:.6f}) "
                            f"และทะลุเส้นล่าง (low={candle['low']:.6f} < BOTTOM={candle['BOTTOM']:.6f})[/red]")
            return "SELL"
            
        return None
        
    def set_leverage(self, contract: str) -> bool:
        """ตั้งค่า leverage สำหรับสัญญา"""
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            self.console.print(f"[yellow]ตั้งค่า leverage {self.leverage}x สำหรับ {contract}[/yellow]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถตั้งค่า leverage สำหรับ {contract}: {str(e)}[/red]")
            return False
            
    def get_latest_price(self, contract: str) -> float:
        """ดึงราคาล่าสุดของสัญญา"""
        ticker = self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract == contract:
                price = float(t.last)
                return price
                
        self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
        return None
        
    def check_existing_position(self, contract: str) -> Dict:
        """ตรวจสอบว่ามี position เปิดอยู่หรือไม่"""
        positions = self.futures_api.list_positions(settle='usdt', holding=True)
        for p in positions:
            if p.contract == contract:
                position_info = p.to_dict()
                size = float(position_info['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                self.console.print(f"[yellow]พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                return position_info
                
        return None
        
    def close_position(self, contract: str, position: Dict) -> bool:
        """ปิด position ที่มีอยู่"""
        try:
            size = float(position['size'])
            if size != 0:
                # กำหนดขนาดในทิศทางตรงข้าม
                direction = abs(size) if size < 0 else -size
                self.futures_api.create_futures_order('usdt', {
                    'contract': contract,
                    'size': direction,
                    'price': 0,
                    'tif': 'ioc',
                    'reduce_only': True
                })
                position_type = "LONG" if size > 0 else "SHORT"
                self.console.print(f"[yellow]ปิด position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                return True
            return False
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถปิด position สำหรับ {contract}: {str(e)}[/red]")
            return False
            
    def create_long_order(self, contract: str) -> Dict:
        """เปิด position LONG"""
        try:
            if not self.set_leverage(contract):
                return None
                
            price = self.get_latest_price(contract)
            if not price:
                return None
                
            # ดึงข้อมูลสัญญาเพื่อคำนวณขนาด position
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            
            # คำนวณขนาด position จากจำนวนเงินและเลเวอเรจ
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            
            # สร้างออเดอร์แบบ market (price=0)
            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract,
                'size': size,
                'price': 0,
                'tif': 'ioc',
                'reduce_only': False
            })
            
            self.console.print(f"[green]เปิด position LONG: {contract} ขนาด={size}[/green]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด LONG สำหรับ {contract}: {str(e)}[/red]")
            return None
            
    def create_short_order(self, contract: str) -> Dict:
        """เปิด position SHORT"""
        try:
            if not self.set_leverage(contract):
                return None
                
            price = self.get_latest_price(contract)
            if not price:
                return None
                
            # ดึงข้อมูลสัญญาเพื่อคำนวณขนาด position
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            
            # คำนวณขนาด position จากจำนวนเงินและเลเวอเรจ
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            
            # สร้างออเดอร์แบบ market (price=0) และขนาดเป็นลบสำหรับ SHORT
            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract,
                'size': -size,
                'price': 0,
                'tif': 'ioc',
                'reduce_only': False
            })
            
            self.console.print(f"[red]เปิด position SHORT: {contract} ขนาด={size}[/red]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด SHORT สำหรับ {contract}: {str(e)}[/red]")
            return None
            
    def scan_positions(self):
        """สแกน positions ที่มีอยู่เพื่อตรวจสอบเงื่อนไขการปิด"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]สแกน {len(positions)} positions ที่เปิดอยู่[/blue]")
            
            for pos in positions:
                contract = pos['contract']
                
                # ดึงข้อมูลแท่งเทียนและคำนวณ Linear Regression Channel
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df, _ = self.calculate_linear_regression_channel(contract, df)
                    if not df.empty:
                        latest_price = self.get_latest_price(contract)
                        if latest_price:
                            tmid = df['TMID'].iloc[-1]
                            bmid = df['BMID'].iloc[-1]
                            size = float(pos['size'])
                            
                            # ปิด LONG ถ้าราคาต่ำกว่า TMID
                            if size > 0 and latest_price < tmid:
                                self.console.print(f"[yellow]ปิด LONG position: {contract} เนื่องจากราคาล่าสุด={latest_price:.6f} < TMID={tmid:.6f}[/yellow]")
                                self.close_position(contract, pos)
                                
                            # ปิด SHORT ถ้าราคาสูงกว่า BMID
                            elif size < 0 and latest_price > bmid:
                                self.console.print(f"[yellow]ปิด SHORT position: {contract} เนื่องจากราคาล่าสุด={latest_price:.6f} > BMID={bmid:.6f}[/yellow]")
                                self.close_position(contract, pos)
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน positions: {str(e)}[/red]")
            
    def scan_market(self):
        """สแกนตลาดอย่างต่อเนื่องเพื่อหาสัญญาณการเทรด"""
        first_run = True
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                
                # ทำงานทุก 1 ชั่วโมงและในรอบแรก
                if current_time.minute == 0 or first_run:
                    self.console.print(f"[blue]เริ่มสแกนตลาด ณ เวลา {current_time}[/blue]")
                    first_run = False
                    
                    # สแกน positions ที่มีอยู่ก่อน
                    self.scan_positions()
                    
                    # สแกนตลาดเพื่อหาสัญญาณใหม่
                    contracts = self.get_futures_contracts()
                    for contract in contracts:
                        # ดึงข้อมูลแท่งเทียนและคำนวณ Linear Regression Channel
                        df = self.get_candlesticks(contract)
                        if not df.empty:
                            df, slope = self.calculate_linear_regression_channel(contract, df)
                            if not df.empty:
                                # ตรวจสอบสัญญาณและ position ที่มีอยู่
                                signal = self.check_trading_signal(df, slope)
                                existing_pos = self.check_existing_position(contract)
                                
                                # จัดการสัญญาณ BUY
                                if signal == "BUY":
                                    if existing_pos and float(existing_pos['size']) < 0:
                                        # ถ้ามี SHORT position อยู่ ให้ปิดก่อนแล้วเปิด LONG
                                        if self.close_position(contract, existing_pos):
                                            time.sleep(1)  # รอให้ระบบประมวลผลการปิด position
                                            self.create_long_order(contract)
                                    elif not existing_pos:
                                        # ถ้าไม่มี position ให้เปิด LONG
                                        self.create_long_order(contract)
                                        
                                # จัดการสัญญาณ SELL
                                elif signal == "SELL":
                                    if existing_pos and float(existing_pos['size']) > 0:
                                        # ถ้ามี LONG position อยู่ ให้ปิดก่อนแล้วเปิด SHORT
                                        if self.close_position(contract, existing_pos):
                                            time.sleep(1)  # รอให้ระบบประมวลผลการปิด position
                                            self.create_short_order(contract)
                                    elif not existing_pos:
                                        # ถ้าไม่มี position ให้เปิด SHORT
                                        self.create_short_order(contract)
                                        
                    # รอ 30 วินาทีก่อนทำอย่างอื่น
                    time.sleep(30)
                    
                # ทำงานทุก 15 นาทีเพื่อตรวจสอบ positions
                if current_time.minute % 15 == 0:
                    if current_time.minute == 0:
                        first_run = True
                    else:
                        self.scan_positions()
                        time.sleep(60)
                        
                # รอ 10 วินาทีและวนลูปใหม่
                time.sleep(10)
                
            except Exception as e:
                self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}[/red]")
                time.sleep(30)  # รอก่อนลองใหม่ในกรณีที่เกิดข้อผิดพลาด
                


def main():
    """ฟังก์ชันหลักสำหรับเริ่มทำงานของบอท"""
    try:
        bot = GateIOLRCTradeBot()
        bot.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย Linear Regression Channel...[/blue]")
        bot.scan_market()
    except Exception as e:
        Console().print(f"[red]เกิดข้อผิดพลาดร้ายแรง: {str(e)}[/red]")


if __name__ == "__main__":
    main()