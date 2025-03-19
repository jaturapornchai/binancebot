import os
import time
import re
from typing import List, Dict, Tuple
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console


class GateIODBOTradeBot:
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
        self.console = Console()  # สำหรับแสดงผลในคอนโซล
        
        # พารามิเตอร์สำหรับ Double break out Caco Maia
        self.media_rapida = 8  # Fast average
        self.media_lenta = 20  # Slow average
        self.trix_length = 7  # TRIX length
        self.trix_ma = 4  # TRIX Average
        self.stoch_length = 14  # Stochastic Length
        self.stoch_k = 3  # Stochastic %K
        self.stoch_d = 3  # Stochastic %D
        self.lookback_period = 14  # จำนวนแท่งเทียนย้อนหลังสำหรับการตรวจสอบการปิด position
        
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
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """คำนวณตัวชี้วัดสำหรับ Double break out Caco Maia"""
        if len(df) < max(self.media_lenta, self.stoch_length, self.trix_length + self.trix_ma) + 10:
            return pd.DataFrame()
            
        # คำนวณค่าเฉลี่ยเคลื่อนที่
        df['sma_fast'] = df['close'].rolling(window=self.media_rapida).mean()
        df['sma_slow'] = df['close'].rolling(window=self.media_lenta).mean()
        
        # คำนวณ TRIX
        # ฟังก์ชันสำหรับคำนวณ EMA ซ้อน 3 ชั้น
        def tema(series, length):
            ema1 = series.ewm(span=length, adjust=False).mean()
            ema2 = ema1.ewm(span=length, adjust=False).mean()
            ema3 = ema2.ewm(span=length, adjust=False).mean()
            return ema3
        
        tema_values = tema(df['close'], self.trix_length)
        # คำนวณ TRIX = ((ค่าปัจจุบัน - ค่าก่อนหน้า) / ค่าก่อนหน้า) * 10000
        df['trix'] = ((tema_values - tema_values.shift(1)) / tema_values.shift(1)) * 10000
        df['trix_signal'] = df['trix'].ewm(span=self.trix_ma, adjust=False).mean()
        
        # คำนวณ Stochastic
        df['stoch_lowest'] = df['low'].rolling(window=self.stoch_length).min()
        df['stoch_highest'] = df['high'].rolling(window=self.stoch_length).max()
        df['stoch_raw'] = 100 * ((df['close'] - df['stoch_lowest']) / (df['stoch_highest'] - df['stoch_lowest']))
        df['stoch'] = df['stoch_raw'].rolling(window=self.stoch_d).mean()
        df['stoch_k'] = df['stoch'].rolling(window=self.stoch_k).mean()
        
        # คำนวณค่าต่ำสุดและสูงสุดย้อนหลัง 14 time frame สำหรับการปิด position
        df['lowest_14'] = df['low'].rolling(window=self.lookback_period).min()
        df['highest_14'] = df['high'].rolling(window=self.lookback_period).max()
        
        return df.dropna()
    
    def trix_comprado(self, df: pd.DataFrame, index: int) -> bool:
        """ตรวจสอบเงื่อนไข TRIX เป็นบวก"""
        return df['trix'].iloc[index] > df['trix_signal'].iloc[index]
    
    def stock_comprado(self, df: pd.DataFrame, index: int) -> bool:
        """ตรวจสอบเงื่อนไข Stochastic เป็นบวก"""
        return df['stoch'].iloc[index] > df['stoch_k'].iloc[index]
    
    def rompeu(self, df: pd.DataFrame, index: int) -> bool:
        """ตรวจสอบเงื่อนไขสัญญาณซื้อ (Break up)"""
        candle = df.iloc[index]
        # รูปแบบแท่งเทียนทะลุขึ้น
        breakup_pattern = (
            candle['close'] > candle['open'] and
            candle['open'] <= candle['sma_fast'] and
            candle['close'] > candle['sma_fast'] and
            candle['low'] < candle['sma_slow'] and
            candle['close'] > candle['sma_slow']
        )
        # ตัวกรองเป็นบวก
        filters_ok = self.trix_comprado(df, index) and self.stock_comprado(df, index)
        
        return breakup_pattern and filters_ok
    
    def perdeu(self, df: pd.DataFrame, index: int) -> bool:
        """ตรวจสอบเงื่อนไขสัญญาณขาย (Break down)"""
        candle = df.iloc[index]
        # รูปแบบแท่งเทียนทะลุลง
        breakdown_pattern = (
            candle['close'] < candle['open'] and
            candle['open'] >= candle['sma_fast'] and
            candle['close'] < candle['sma_fast'] and
            candle['high'] > candle['sma_slow'] and
            candle['close'] < candle['sma_slow']
        )
        # ตัวกรองเป็นลบ
        filters_ok = not self.trix_comprado(df, index) and not self.stock_comprado(df, index)
        
        return breakdown_pattern and filters_ok
    
    def check_trading_signal(self, df: pd.DataFrame) -> str:
        """ตรวจสอบสัญญาณการเทรด"""
        if len(df) < 2:
            return None
            
        # ใช้ข้อมูลล่าสุด
        last_index = len(df) - 1
        
        # ตรวจสอบเงื่อนไขสัญญาณซื้อ
        if self.rompeu(df, last_index):
            self.console.print(f"[green]สัญญาณ BUY: Double breakout Caco Maia - Break up![/green]")
            return "BUY"
            
        # ตรวจสอบเงื่อนไขสัญญาณขาย
        elif self.perdeu(df, last_index):
            self.console.print(f"[red]สัญญาณ SELL: Double breakout Caco Maia - Break down![/red]")
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
                
                # ดึงข้อมูลแท่งเทียนและคำนวณตัวชี้วัด
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df = self.calculate_indicators(df)
                    if not df.empty:
                        latest_price = self.get_latest_price(contract)
                        if latest_price:
                            latest_data = df.iloc[-1]
                            size = float(pos['size'])
                            
                            # ปิด LONG ถ้าราคาล่าสุดต่ำกว่าราคาต่ำสุดย้อนหลัง 14 time frame
                            if size > 0 and latest_price < latest_data['lowest_14']:
                                self.console.print(f"[yellow]ปิด LONG position: {contract} เนื่องจากราคาล่าสุด={latest_price:.6f} < ราคาต่ำสุดย้อนหลัง 14 แท่ง={latest_data['lowest_14']:.6f}[/yellow]")
                                self.close_position(contract, pos)
                                
                            # ปิด SHORT ถ้าราคาล่าสุดสูงกว่าราคาสูงสุดย้อนหลัง 14 time frame
                            elif size < 0 and latest_price > latest_data['highest_14']:
                                self.console.print(f"[yellow]ปิด SHORT position: {contract} เนื่องจากราคาล่าสุด={latest_price:.6f} > ราคาสูงสุดย้อนหลัง 14 แท่ง={latest_data['highest_14']:.6f}[/yellow]")
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
                        # ดึงข้อมูลแท่งเทียนและคำนวณตัวชี้วัด
                        df = self.get_candlesticks(contract)
                        if not df.empty:
                            df = self.calculate_indicators(df)
                            if not df.empty:
                                # ตรวจสอบสัญญาณและ position ที่มีอยู่
                                signal = self.check_trading_signal(df)
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
        bot = GateIODBOTradeBot()
        bot.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย Double break out Caco Maia...[/blue]")
        bot.scan_market()
    except Exception as e:
        Console().print(f"[red]เกิดข้อผิดพลาดร้ายแรง: {str(e)}[/red]")


if __name__ == "__main__":
    main()