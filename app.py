import os, time, re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console

class GateIOLinearRegressionTrader:
    def __init__(self):
        load_dotenv()
        # โหลด API key จาก environment variables
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env")
        
        # ตั้งค่า API client
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        
        # ตั้งค่าพารามิเตอร์การเทรด
        self.leverage = 5
        self.order_amount = 20  # จำนวนเงิน USD ต่อการเปิดออเดอร์
        self.lookback_period = 100  # จำนวนแท่งเทียนที่ใช้คำนวณ Linear Regression Channel
        self.devlen = 2.0  # ค่าความเบี่ยงเบน (deviation) สำหรับขอบบนและล่าง
        
        # สร้าง console สำหรับแสดงผล
        self.console = Console()

    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ"""
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = []
        pattern = re.compile(r'^\D+_USDT$')
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                 # ตรวจสอบสภาพคล่อง (Volume 24h > $500,000)
                json_data = contract.to_dict()
                if float(json_data['volume_24h']) * float(json_data['last']) > 500000:
                    valid_contracts.append(contract.contract)
        self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา[/blue]")
        return valid_contracts

    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนจาก API"""
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
        if not candles: return pd.DataFrame()
        
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')

    def calculate_linear_regression_channel(self, df: pd.DataFrame) -> dict:
        """คำนวณ Linear Regression Channel พร้อมเส้น TOPMIDDLE และ MIDDLEBOTTOM"""
        if len(df) < self.lookback_period + 5: return {}  # ต้องมีข้อมูลมากกว่าที่ต้องการใช้
        
        # ดึงข้อมูลล่าสุดตามจำนวน lookback_period
        recent_data = df['close'].iloc[-self.lookback_period:].values
        
        # ใช้ numpy สำหรับการคำนวณ linear regression
        x = np.arange(self.lookback_period)
        slope, intercept = np.polyfit(x, recent_data, 1)
        
        # คำนวณค่า linear regression line และค่าต่างๆ
        line = intercept + slope * x
        middle = line[-1]
        deviations = recent_data - line
        dev = np.sqrt(np.mean(deviations**2))
        top = middle + dev * self.devlen
        bottom = middle - dev * self.devlen
        
        # เพิ่มเส้น TOPMIDDLE และ MIDDLEBOTTOM
        topmiddle = (top + middle) / 2
        middlebottom = (middle + bottom) / 2
        
        # ตรวจสอบความสมเหตุสมผลของค่า
        latest_price = recent_data[-1]
        
        # ป้องกันค่า channel ที่ไม่สมเหตุสมผล
        if (top - latest_price) / latest_price > 1.0 or (latest_price - bottom) / latest_price > 1.0:
            self.console.print(f"[yellow]⚠️ ปรับขนาด channel เนื่องจากค่าเดิมไม่สมเหตุสมผล[/yellow]")
            reasonable_dev = latest_price * 0.05  # ใช้ค่า 5% ของราคาปัจจุบัน
            top = middle + reasonable_dev * self.devlen
            bottom = middle - reasonable_dev * self.devlen
            # คำนวณ TOPMIDDLE และ MIDDLEBOTTOM ใหม่
            topmiddle = (top + middle) / 2
            middlebottom = (middle + bottom) / 2
        
        # ตรวจสอบค่าลบ
        if bottom < 0 and latest_price > 0:
            bottom = latest_price * 0.8  # กำหนดค่าต่ำสุดเป็น 80% ของราคาปัจจุบัน
            middlebottom = (middle + bottom) / 2  # อัพเดต MIDDLEBOTTOM
            self.console.print(f"[yellow]⚠️ ปรับค่า BOTTOM เนื่องจากเป็นค่าลบ[/yellow]")
        
        # คำนวณ slope ก่อนหน้า
        prev_data = df['close'].iloc[-self.lookback_period-1:-1].values if len(df) > self.lookback_period + 1 else []
        prev_slope = np.polyfit(x, prev_data, 1)[0] if len(prev_data) == self.lookback_period else 0.0
        
        return {
            'MIDDLE': middle, 
            'TOP': top, 
            'BOTTOM': bottom, 
            'TOPMIDDLE': topmiddle, 
            'MIDDLEBOTTOM': middlebottom,
            'slope': slope, 
            'slope_prev': prev_slope, 
            'dev': dev
        }

    def is_green_candle(self, candle) -> bool:
        """ตรวจสอบว่าแท่งเทียนเป็นสีเขียวหรือไม่ (close > open)"""
        return candle['close'] > candle['open']

    def is_red_candle(self, candle) -> bool:
        """ตรวจสอบว่าแท่งเทียนเป็นสีแดงหรือไม่ (close < open)"""
        return candle['close'] < candle['open']

    def is_touching_top(self, candle, top_value) -> bool:
        """ตรวจสอบว่าแท่งเทียนทับเส้น TOP หรือไม่"""
        tolerance = top_value * 0.001  # ยอมรับความคลาดเคลื่อน 0.1%
        return abs(candle['high'] - top_value) < tolerance

    def is_touching_bottom(self, candle, bottom_value) -> bool:
        """ตรวจสอบว่าแท่งเทียนทับเส้น BOTTOM หรือไม่"""
        tolerance = bottom_value * 0.001  # ยอมรับความคลาดเคลื่อน 0.1%
        return abs(candle['low'] - bottom_value) < tolerance

    def get_latest_price(self, contract: str) -> float:
        """ดึงราคาล่าสุดของสัญญา"""
        ticker = self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract == contract:
                return float(t.last)
        self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
        return None

    def check_trading_signal(self, df: pd.DataFrame, lrc_data: dict, contract: str = None) -> str:
        """ตรวจสอบสัญญาณการเทรดตามเงื่อนไขที่กำหนดใหม่"""
        if not lrc_data or len(df) < 1: return None
        
        top_value = lrc_data['TOP']
        bottom_value = lrc_data['BOTTOM']
        
        # ดึงข้อมูลแท่งเทียนล่าสุด
        latest_candle = df.iloc[-1]
        
        # ดึงราคาล่าสุด
        latest_price = self.get_latest_price(contract)
        if latest_price is None: return None
        
        # ตรวจสอบเงื่อนไขแท่งเทียน
        is_green = self.is_green_candle(latest_candle)
        is_red = self.is_red_candle(latest_candle)
        touches_top = self.is_touching_top(latest_candle, top_value)
        touches_bottom = self.is_touching_bottom(latest_candle, bottom_value)
        
        # แสดงผลข้อมูลเพื่อวิเคราะห์
        topmiddle = lrc_data['TOPMIDDLE']
        middlebottom = lrc_data['MIDDLEBOTTOM']
        middle = lrc_data['MIDDLE']
        self.console.print(f"[blue]   การตรวจสอบสัญญาณ: ราคาล่าสุด={latest_price:.6f}[/blue]")
        self.console.print(f"[blue]   BOTTOM={bottom_value:.6f}, MIDDLEBOTTOM={middlebottom:.6f}, MIDDLE={middle:.6f}, TOPMIDDLE={topmiddle:.6f}, TOP={top_value:.6f}[/blue]")
        self.console.print(f"[blue]   แท่งเทียน: {is_green and 'สีเขียว' or is_red and 'สีแดง' or 'Doji'}, ทับ TOP={touches_top}, ทับ BOTTOM={touches_bottom}[/blue]")
        
        # เงื่อนไขใหม่: BUY=CANDLE เป็นสีเขียว ทับเส้น TOP พอดี และราคาล่าสุดอยู่เหนือเส้น TOP
        if is_green and touches_top and latest_price > top_value:
            self.console.print(f"[green]สัญญาณ BUY: แท่งเทียนสีเขียว ทับเส้น TOP ({top_value:.6f}) และราคาล่าสุด ({latest_price:.6f}) อยู่เหนือเส้น TOP[/green]")
            return "BUY"
        
        # เงื่อนไขใหม่: SELL=CANDLE เป็นสีแดง ทับเส้น BOTTOM พอดี และราคาล่าสุดอยู่ใต้เส้น BOTTOM
        if is_red and touches_bottom and latest_price < bottom_value:
            self.console.print(f"[red]สัญญาณ SELL: แท่งเทียนสีแดง ทับเส้น BOTTOM ({bottom_value:.6f}) และราคาล่าสุด ({latest_price:.6f}) อยู่ใต้เส้น BOTTOM[/red]")
            return "SELL"
        
        return None

    def check_existing_position(self, contract: str) -> Dict:
        """ตรวจสอบว่ามี position ที่เปิดอยู่หรือไม่"""
        positions = self.futures_api.list_positions(settle='usdt', holding=True)
        for p in positions:
            if p.contract == contract:
                position_info = p.to_dict()
                size = float(position_info['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                self.console.print(f"[yellow]พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                return position_info
        return None

    def set_leverage(self, contract: str) -> bool:
        """ตั้งค่า leverage สำหรับการเทรด"""
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            self.console.print(f"[yellow]ตั้งค่า leverage {self.leverage}x สำหรับ {contract}[/yellow]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถตั้งค่า leverage สำหรับ {contract}: {str(e)}[/red]")
            return False

    def close_position(self, contract: str, position: Dict) -> bool:
        """ปิด position ที่มีอยู่"""
        try:
            size = float(position['size'])
            if size == 0: return False
            
            # ใช้ค่าตรงข้ามกับ size ปัจจุบันเพื่อปิด position
            direction = abs(size) if size < 0 else -size
            self.futures_api.create_futures_order(
                'usdt',
                {
                    'contract': contract,
                    'size': direction,
                    'price': 0,  # market order
                    'tif': 'ioc',  # immediate-or-cancel
                    'reduce_only': True  # เพื่อปิด position เท่านั้น
                }
            )
            position_type = "LONG" if size > 0 else "SHORT"
            self.console.print(f"[yellow]ปิด position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถปิด position สำหรับ {contract}: {str(e)}[/red]")
            return False

    def create_long_order(self, contract: str) -> Dict:
        """เปิด position LONG"""
        try:
            if not self.set_leverage(contract): return None
            
            price = self.get_latest_price(contract)
            if not price: return None
            
            # ดึงข้อมูลสัญญาเพื่อคำนวณขนาด position
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            
            # คำนวณขนาด position
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            
            # สร้างคำสั่งซื้อ
            order = self.futures_api.create_futures_order(
                'usdt',
                {
                    'contract': contract,
                    'size': size,
                    'price': 0,  # market order
                    'tif': 'ioc',  # immediate-or-cancel
                    'reduce_only': False  # เพื่อเปิด position ใหม่
                }
            )
            self.console.print(f"[green]เปิด position LONG: {contract} ขนาด={size}[/green]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด LONG สำหรับ {contract}: {str(e)}[/red]")
            return None

    def create_short_order(self, contract: str) -> Dict:
        """เปิด position SHORT"""
        try:
            if not self.set_leverage(contract): return None
            
            price = self.get_latest_price(contract)
            if not price: return None
            
            # ดึงข้อมูลสัญญาเพื่อคำนวณขนาด position
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            
            # คำนวณขนาด position
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            
            # สร้างคำสั่งขาย
            order = self.futures_api.create_futures_order(
                'usdt',
                {
                    'contract': contract,
                    'size': -size,  # ค่าลบเพื่อ short
                    'price': 0,  # market order
                    'tif': 'ioc',  # immediate-or-cancel
                    'reduce_only': False  # เพื่อเปิด position ใหม่
                }
            )
            self.console.print(f"[red]เปิด position SHORT: {contract} ขนาด={size}[/red]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด SHORT สำหรับ {contract}: {str(e)}[/red]")
            return None

    def scan_positions(self):
        """สแกน positions ที่เปิดอยู่และตรวจสอบเงื่อนไขการปิด position ตามเงื่อนไขใหม่"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            
            positions_checked = 0
            positions_closed = 0
            
            for pos in positions:
                contract = pos['contract']
                size = float(pos['size'])
                position_type = "LONG 📈" if size > 0 else "SHORT 📉" if size < 0 else "NONE"
                entry_price = float(pos['entry_price'])
                
                self.console.print(f"[cyan]▶ ตรวจสอบ: {contract} ({position_type}) - ราคาเข้า: {entry_price:.6f} - ขนาด: {abs(size)}[/cyan]")
                
                df = self.get_candlesticks(contract)
                
                if not df.empty:
                    lrc_data = self.calculate_linear_regression_channel(df)
                    
                    if lrc_data:
                        latest_price = self.get_latest_price(contract)
                        
                        if latest_price:
                            top = lrc_data['TOP']
                            bottom = lrc_data['BOTTOM']
                            middle = lrc_data['MIDDLE']
                            topmiddle = lrc_data['TOPMIDDLE']
                            middlebottom = lrc_data['MIDDLEBOTTOM']
                            slope = lrc_data['slope']
                            
                            # แสดงข้อมูล Linear Regression Channel
                            slope_direction = "ขาขึ้น 📈" if slope > 0 else "ขาลง 📉" if slope < 0 else "แนวราบ ➡️"
                            
                            self.console.print(f"[magenta]   Linear Regression Channel:[/magenta]")
                            self.console.print(f"[magenta]   TOP={top:.6f}, TOPMIDDLE={topmiddle:.6f}, MIDDLE={middle:.6f}, MIDDLEBOTTOM={middlebottom:.6f}, BOTTOM={bottom:.6f}[/magenta]")
                            self.console.print(f"[magenta]   Slope={slope:.6f} ({slope_direction}) - ราคาล่าสุด={latest_price:.6f}[/magenta]")
                            
                            # แสดงข้อมูลแท่งเทียนล่าสุด
                            latest_candle = df.iloc[-1]
                            candle_type = "สีเขียว 🟩" if latest_candle['close'] > latest_candle['open'] else "สีแดง 🟥" if latest_candle['close'] < latest_candle['open'] else "Doji ⬛"
                            self.console.print(f"[magenta]   แท่งเทียนล่าสุด: {candle_type} - Open: {latest_candle['open']:.6f}, Close: {latest_candle['close']:.6f}[/magenta]")
                            
                            # คำนวณกำไร/ขาดทุนเป็น %
                            if size > 0:  # LONG
                                pnl_percentage = ((latest_price - entry_price) / entry_price) * 100
                            else:  # SHORT
                                pnl_percentage = ((entry_price - latest_price) / entry_price) * 100
                            pnl_color = "green" if pnl_percentage > 0 else "red"
                            self.console.print(f"[{pnl_color}]   P&L: {pnl_percentage:.2f}%[/{pnl_color}]")
                            
                            # ตรวจสอบสัญญาณการเทรด
                            signal = self.check_trading_signal(df, lrc_data, contract)
                            
                            # ตรวจสอบเงื่อนไขการปิด position ตามที่กำหนดใหม่
                            close_position_reason = None
                            
                            # เงื่อนไขใหม่:
                            # ปิด long position ถ้า position เดิมที่เปิดอยู่เป็น long และราคาล่าสุดต่ำกว่าเส้น TOPMIDDLE
                            # ปิด short position ถ้า position เดิมที่เปิดอยู่เป็น short และ ราคาล่าสุด สูงกว่าเส้น MIDDLEBOTTOM
                            if size > 0:  # LONG position
                                if latest_price < topmiddle:
                                    close_position_reason = f"ราคาล่าสุด ({latest_price:.6f}) ต่ำกว่าเส้น TOPMIDDLE ({topmiddle:.6f})"
                            elif size < 0:  # SHORT position
                                if latest_price > middlebottom:
                                    close_position_reason = f"ราคาล่าสุด ({latest_price:.6f}) สูงกว่าเส้น MIDDLEBOTTOM ({middlebottom:.6f})"
                            
                            if close_position_reason:
                                position_label = "LONG" if size > 0 else "SHORT"
                                self.console.print(f"[yellow]🔔 ปิด {position_label} position: {contract} เนื่องจาก {close_position_reason}[/yellow]")
                                if self.close_position(contract, pos):
                                    positions_closed += 1
                                    self.console.print(f"[green]✅ ปิด {position_label} position สำเร็จ: {contract} - P&L: {pnl_percentage:.2f}%[/green]")
                            else:
                                self.console.print(f"[blue]   ยังไม่ต้องปิด position (ไม่เข้าเงื่อนไข)[/blue]")
                            
                            positions_checked += 1
                        else:
                            self.console.print(f"[red]❌ ไม่สามารถดึงราคาล่าสุดของ {contract} ได้[/red]")
                    else:
                        self.console.print(f"[red]❌ ไม่สามารถคำนวณ Linear Regression Channel สำหรับ {contract} ได้[/red]")
                else:
                    self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
            
            # แสดงผลสรุป
            self.console.print(f"[blue]===== สรุปการสแกน positions =====[/blue]")
            self.console.print(f"[blue]ตรวจสอบ: {positions_checked}/{len(positions)} positions[/blue]")
            self.console.print(f"[blue]ปิด: {positions_closed} positions[/blue]")
            
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน positions: {str(e)}[/red]")

    def scan_market(self):
        """สแกนตลาดเพื่อหาสัญญาณการเทรดและจัดการ positions"""
        first_run = True
        
        # ตัวแปรเก็บสถิติรวม
        stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0,
                'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
        
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                
                # ทำงานทุกต้นชั่วโมงและนาทีที่ 15, 30, 45 หรือเมื่อเริ่มต้นโปรแกรม
                if current_time.minute % 15 == 0 or first_run:
                    self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    first_run = False
                    
                    # ตัวแปรเก็บสถิติการสแกนรอบนี้
                    scan_stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0,
                               'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
                    
                    # สแกน positions ที่มีอยู่
                    self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                    self.scan_positions()
                    
                    # ดึงรายชื่อสัญญา futures ที่มีสภาพคล่อง
                    self.console.print(f"[blue]📊 ตรวจหาสัญญาณเทรดใหม่[/blue]")
                    contracts = self.get_futures_contracts()
                    
                    # ตรวจสอบแต่ละสัญญา
                    for i, contract in enumerate(contracts, 1):
                        self.console.print(f"[cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract}[/cyan]")
                        df = self.get_candlesticks(contract)
                        
                        if not df.empty:
                            lrc_data = self.calculate_linear_regression_channel(df)
                            
                            if lrc_data:
                                # แสดงข้อมูล Linear Regression Channel
                                top = lrc_data['TOP']
                                bottom = lrc_data['BOTTOM']
                                middle = lrc_data['MIDDLE']
                                topmiddle = lrc_data['TOPMIDDLE']
                                middlebottom = lrc_data['MIDDLEBOTTOM']
                                slope = lrc_data['slope']
                                
                                slope_direction = "ขาขึ้น 📈" if slope > 0 else "ขาลง 📉" if slope < 0 else "แนวราบ ➡️"
                                latest_price = self.get_latest_price(contract)
                                
                                self.console.print(f"[magenta]   Linear Regression Channel:[/magenta]")
                                self.console.print(f"[magenta]   TOP={top:.6f}, TOPMIDDLE={topmiddle:.6f}, MIDDLE={middle:.6f}, MIDDLEBOTTOM={middlebottom:.6f}, BOTTOM={bottom:.6f}[/magenta]")
                                self.console.print(f"[magenta]   Slope={slope:.6f} ({slope_direction}), ราคาล่าสุด={latest_price:.6f}[/magenta]")
                                
                                # ตรวจสอบสัญญาณการเทรด
                                signal = self.check_trading_signal(df, lrc_data, contract)
                                
                                # จัดการการเทรดตามสัญญาณที่ได้รับ
                                if signal == "BUY":
                                    scan_stats['buy_signals'] += 1
                                    existing_pos = self.check_existing_position(contract)
                                    if existing_pos and float(existing_pos['size']) < 0:
                                        # มี short position อยู่ ให้ปิดก่อนแล้วเปิด long
                                        self.console.print(f"[yellow]🔄 มี SHORT position อยู่ ต้องปิดก่อนเปิด LONG[/yellow]")
                                        if self.close_position(contract, existing_pos):
                                            scan_stats['positions_closed'] += 1
                                            if self.create_long_order(contract):
                                                scan_stats['long_opened'] += 1
                                    elif not existing_pos:
                                        # ไม่มี position ให้เปิด long ได้เลย
                                        self.console.print(f"[yellow]🆕 ไม่มี position อยู่ เปิด LONG ได้เลย[/yellow]")
                                        if self.create_long_order(contract):
                                            scan_stats['long_opened'] += 1
                                    else:
                                        self.console.print(f"[yellow]⏩ มี LONG position อยู่แล้ว ไม่ต้องทำอะไร[/yellow]")
                                elif signal == "SELL":
                                    scan_stats['sell_signals'] += 1
                                    existing_pos = self.check_existing_position(contract)
                                    if existing_pos and float(existing_pos['size']) > 0:
                                        # มี long position อยู่ ให้ปิดก่อนแล้วเปิด short
                                        self.console.print(f"[yellow]🔄 มี LONG position อยู่ ต้องปิดก่อนเปิด SHORT[/yellow]")
                                        if self.close_position(contract, existing_pos):
                                            scan_stats['positions_closed'] += 1
                                            if self.create_short_order(contract):
                                                scan_stats['short_opened'] += 1
                                    elif not existing_pos:
                                        # ไม่มี position ให้เปิด short ได้เลย
                                        self.console.print(f"[yellow]🆕 ไม่มี position อยู่ เปิด SHORT ได้เลย[/yellow]")
                                        if self.create_short_order(contract):
                                            scan_stats['short_opened'] += 1
                                    else:
                                        self.console.print(f"[yellow]⏩ มี SHORT position อยู่แล้ว ไม่ต้องทำอะไร[/yellow]")
                                else:
                                    self.console.print(f"[blue]   ไม่พบสัญญาณเทรด[/blue]")
                                
                                scan_stats['contracts_scanned'] += 1
                            else:
                                self.console.print(f"[red]❌ ไม่สามารถคำนวณ Linear Regression Channel สำหรับ {contract} ได้[/red]")
                        else:
                            self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                    
                    # อัพเดตสถิติรวม
                    for key in stats:
                        stats[key] += scan_stats[key]
                    
                    # แสดงผลสรุปการสแกนรอบนี้
                    self.console.print(f"[blue]===== สรุปการสแกนรอบนี้ =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกน: {scan_stats['contracts_scanned']}/{len(contracts)}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ BUY: {scan_stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SELL: {scan_stats['sell_signals']}[/red]")
                    self.console.print(f"[green]📈 เปิด LONG: {scan_stats['long_opened']}[/green]")
                    self.console.print(f"[red]📉 เปิด SHORT: {scan_stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position: {scan_stats['positions_closed']}[/yellow]")
                    
                    # แสดงผลสถิติรวม
                    self.console.print(f"[blue]===== สถิติรวมทั้งหมด =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกนทั้งหมด: {stats['contracts_scanned']}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ BUY ทั้งหมด: {stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SELL ทั้งหมด: {stats['sell_signals']}[/red]")
                    self.console.print(f"[green]📈 เปิด LONG ทั้งหมด: {stats['long_opened']}[/green]")
                    self.console.print(f"[red]📉 เปิด SHORT ทั้งหมด: {stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position ทั้งหมด: {stats['positions_closed']}[/yellow]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    
                    time.sleep(30)  # รอ 30 วินาทีหลังจากสแกนเสร็จ
                
                time.sleep(10)  # รอ 10 วินาทีก่อนตรวจสอบเวลาอีกครั้ง
            except Exception as e:
                self.console.print(f"[red]❌ เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}[/red]")
                time.sleep(60)  # รอ 1 นาทีก่อนลองใหม่

def main():
    trader = GateIOLinearRegressionTrader()
    trader.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย Linear Regression Channel...[/blue]")
    trader.scan_market()

if __name__ == "__main__":
    main()