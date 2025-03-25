import os, time, re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console

class GateIOLinearRegressionTrader:
    def __init__(self):
        load_dotenv() # โหลดไฟล์ .env
        self.api_key, self.secret_key = os.getenv('GATEIO_API_KEY'), os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client, self.futures_api = ApiClient(config), FuturesApi(ApiClient(config))
        self.leverage, self.order_amount = 10, 20 # ตั้งค่าเริ่มต้น leverage และจำนวนเงินต่อออเดอร์
        self.lookback_period, self.devlen = 100, 2.0 # ตั้งค่าช่วงเวลาย้อนหลังและขนาดความเบี่ยงเบน
        self.console = Console() # สร้าง console สำหรับแสดงผล

    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ"""
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = []
        pattern = re.compile(r'^\D+_USDT$')
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                json_data = contract.to_dict()
                if float(json_data['volume_24h']) * float(json_data['last']) > 100000:
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
        if len(df) < self.lookback_period + 5: return {}
        recent_data = df['close'].iloc[-self.lookback_period:].values
        x = np.arange(self.lookback_period)
        slope, intercept = np.polyfit(x, recent_data, 1)
        line = intercept + slope * x
        middle = line[-1]
        deviations = recent_data - line
        dev = np.sqrt(np.mean(deviations**2))
        top, bottom = middle + dev * self.devlen, middle - dev * self.devlen
        topmiddle, middlebottom = (top + middle) / 2, (middle + bottom) / 2
        latest_price = recent_data[-1]
        
        # ปรับขนาด channel เมื่อมีค่าไม่สมเหตุสมผล
        if (top - latest_price) / latest_price > 1.0 or (latest_price - bottom) / latest_price > 1.0:
            self.console.print(f"[yellow]⚠️ ปรับขนาด channel เนื่องจากค่าเดิมไม่สมเหตุสมผล[/yellow]")
            reasonable_dev = latest_price * 0.05
            top, bottom = middle + reasonable_dev * self.devlen, middle - reasonable_dev * self.devlen
            topmiddle, middlebottom = (top + middle) / 2, (middle + bottom) / 2
        
        # ปรับค่า BOTTOM เมื่อเป็นค่าลบ
        if bottom < 0 and latest_price > 0:
            bottom = latest_price * 0.8
            middlebottom = (middle + bottom) / 2
            self.console.print(f"[yellow]⚠️ ปรับค่า BOTTOM เนื่องจากเป็นค่าลบ[/yellow]")
        
        prev_data = df['close'].iloc[-self.lookback_period-1:-1].values if len(df) > self.lookback_period + 1 else []
        prev_slope = np.polyfit(x, prev_data, 1)[0] if len(prev_data) == self.lookback_period else 0.0
        
        return {
            'MIDDLE': middle, 'TOP': top, 'BOTTOM': bottom,
            'TOPMIDDLE': topmiddle, 'MIDDLEBOTTOM': middlebottom,
            'slope': slope, 'slope_prev': prev_slope, 'dev': dev
        }

    def is_green_candle(self, candle) -> bool: return candle['close'] > candle['open']
    def is_red_candle(self, candle) -> bool: return candle['close'] < candle['open']

    def is_touching_top(self, candle, top_value) -> bool:
        tolerance = top_value * 0.001
        return abs(candle['high'] - top_value) < tolerance

    def is_touching_bottom(self, candle, bottom_value) -> bool:
        tolerance = bottom_value * 0.001
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
        if not lrc_data or len(df) < 1: return None  # ต้องมีอย่างน้อย 1 แท่งเทียน
        
        top_value, bottom_value = lrc_data['TOP'], lrc_data['BOTTOM']
        # ใช้แท่งเทียนล่าสุด
        candle = df.iloc[-1].to_dict()
        latest_price = self.get_latest_price(contract)
        if latest_price is None: return None
        
        is_green = self.is_green_candle(candle)
        is_red = self.is_red_candle(candle)
        touches_bottom = self.is_touching_bottom(candle, bottom_value)
        touches_top = self.is_touching_top(candle, top_value)
        
        self.console.print(f"[blue]   การตรวจสอบสัญญาณ: ราคาล่าสุด={latest_price:.6f}[/blue]")
        self.console.print(f"[blue]   BOTTOM={lrc_data['BOTTOM']:.6f}, MIDDLEBOTTOM={lrc_data['MIDDLEBOTTOM']:.6f}, MIDDLE={lrc_data['MIDDLE']:.6f}, TOPMIDDLE={lrc_data['TOPMIDDLE']:.6f}, TOP={top_value:.6f}[/blue]")
        self.console.print(f"[blue]   แท่งเทียน: {is_green and 'สีเขียว' or is_red and 'สีแดง' or 'Doji'}, ทับ TOP={touches_top}, ทับ BOTTOM={touches_bottom}[/blue]")
        
        # เงื่อนไขใหม่: BUY = CANDLE สีเขียว ทับเส้น BOTTOM พอดี และราคาสูงสุดของ CANDLE สูงกว่า BOTTOM
        if is_green and touches_bottom and candle['high'] > bottom_value:
            self.console.print(f"[green]สัญญาณ BUY: แท่งเทียนสีเขียว ทับเส้น BOTTOM ({bottom_value:.6f}) และราคาสูงสุดของแท่ง ({candle['high']:.6f}) สูงกว่า BOTTOM[/green]")
            return "BUY"
        
        # เงื่อนไขใหม่: SELL = CANDLE สีแดง ทับเส้น TOP พอดี และราคาต่ำสุดของ CANDLE ต่ำกว่า TOP
        if is_red and touches_top and candle['low'] < top_value:
            self.console.print(f"[red]สัญญาณ SELL: แท่งเทียนสีแดง ทับเส้น TOP ({top_value:.6f}) และราคาต่ำสุดของแท่ง ({candle['low']:.6f}) ต่ำกว่า TOP[/red]")
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
            
            direction = abs(size) if size < 0 else -size
            self.futures_api.create_futures_order(
                'usdt',
                {
                    'contract': contract,
                    'size': direction,
                    'price': 0,
                    'tif': 'ioc',
                    'reduce_only': True
                }
            )
            position_type = "LONG" if size > 0 else "SHORT"
            self.console.print(f"[yellow]ปิด position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถปิด position สำหรับ {contract}: {str(e)}[/red]")
            return False

    def create_order(self, contract: str, is_long: bool) -> Dict:
        """เปิด position LONG หรือ SHORT"""
        try:
            if not self.set_leverage(contract): return None
            
            price = self.get_latest_price(contract)
            if not price: return None
            
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            
            order = self.futures_api.create_futures_order(
                'usdt',
                {
                    'contract': contract,
                    'size': size if is_long else -size,
                    'price': 0,
                    'tif': 'ioc',
                    'reduce_only': False
                }
            )
            position_type = "LONG" if is_long else "SHORT"
            self.console.print(f"[{'green' if is_long else 'red'}]เปิด position {position_type}: {contract} ขนาด={size}[/{'green' if is_long else 'red'}]")
            return order
        except Exception as e:
            position_type = "LONG" if is_long else "SHORT"
            self.console.print(f"[red]ไม่สามารถเปิด {position_type} สำหรับ {contract}: {str(e)}[/red]")
            return None

    def scan_positions(self):
        """สแกน positions ที่เปิดอยู่และตรวจสอบเงื่อนไขการปิด position ตามเงื่อนไขใหม่"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            
            positions_checked, positions_closed = 0, 0
            
            for pos in positions:
                contract, size = pos['contract'], float(pos['size'])
                position_type = "LONG 📈" if size > 0 else "SHORT 📉" if size < 0 else "NONE"
                entry_price = float(pos['entry_price'])
                
                self.console.print(f"[cyan]▶ ตรวจสอบ: {contract} ({position_type}) - ราคาเข้า: {entry_price:.6f} - ขนาด: {abs(size)}[/cyan]")
                
                df = self.get_candlesticks(contract)
                
                if not df.empty and len(df) >= 1:  # ต้องมีอย่างน้อย 1 แท่งเทียน
                    lrc_data = self.calculate_linear_regression_channel(df)
                    
                    if lrc_data:
                        latest_price = self.get_latest_price(contract)
                        
                        if latest_price:
                            topmiddle, middlebottom = lrc_data['TOPMIDDLE'], lrc_data['MIDDLEBOTTOM']
                            top, bottom = lrc_data['TOP'], lrc_data['BOTTOM']
                            slope_direction = "ขาขึ้น 📈" if lrc_data['slope'] > 0 else "ขาลง 📉" if lrc_data['slope'] < 0 else "แนวราบ ➡️"
                            
                            self.console.print(f"[magenta]   Linear Regression Channel:[/magenta]")
                            self.console.print(f"[magenta]   TOP={top:.6f}, TOPMIDDLE={topmiddle:.6f}, MIDDLE={lrc_data['MIDDLE']:.6f}, MIDDLEBOTTOM={middlebottom:.6f}, BOTTOM={bottom:.6f}[/magenta]")
                            self.console.print(f"[magenta]   Slope={lrc_data['slope']:.6f} ({slope_direction}) - ราคาล่าสุด={latest_price:.6f}[/magenta]")
                            
                            # ใช้แท่งเทียนล่าสุด
                            latest_candle = df.iloc[-1].to_dict()
                            candle_type = "สีเขียว 🟩" if latest_candle['close'] > latest_candle['open'] else "สีแดง 🟥" if latest_candle['close'] < latest_candle['open'] else "Doji ⬛"
                            self.console.print(f"[magenta]   แท่งเทียนล่าสุด: {candle_type} - Open: {latest_candle['open']:.6f}, Close: {latest_candle['close']:.6f}, High: {latest_candle['high']:.6f}, Low: {latest_candle['low']:.6f}[/magenta]")
                            
                            pnl_percentage = ((latest_price - entry_price) / entry_price) * 100 if size > 0 else ((entry_price - latest_price) / entry_price) * 100
                            pnl_color = "green" if pnl_percentage > 0 else "red"
                            self.console.print(f"[{pnl_color}]   P&L: {pnl_percentage:.2f}%[/{pnl_color}]")
                            
                            close_position_reason = None
                            
                            # เงื่อนไขใหม่: ปิด LONG ถ้าราคาต่ำสุดของ CANDLE สูงกว่า MIDDLEBOTTOM หรือราคาสูงสุดของ CANDLE ต่ำกว่า BOTTOM
                            if size > 0:  # LONG position
                                if latest_candle['low'] > middlebottom:
                                    close_position_reason = f"ราคาต่ำสุดของแท่งเทียน ({latest_candle['low']:.6f}) สูงกว่าเส้น MIDDLEBOTTOM ({middlebottom:.6f})"
                                elif latest_candle['high'] < bottom:
                                    close_position_reason = f"ราคาสูงสุดของแท่งเทียน ({latest_candle['high']:.6f}) ต่ำกว่าเส้น BOTTOM ({bottom:.6f})"
                            
                            # เงื่อนไขใหม่: ปิด SHORT ถ้าราคาสูงสุดของ CANDLE ต่ำกว่า TOPMIDDLE หรือราคาต่ำสุดของ CANDLE สูงกว่า TOP
                            elif size < 0:  # SHORT position
                                if latest_candle['high'] < topmiddle:
                                    close_position_reason = f"ราคาสูงสุดของแท่งเทียน ({latest_candle['high']:.6f}) ต่ำกว่าเส้น TOPMIDDLE ({topmiddle:.6f})"
                                elif latest_candle['low'] > top:
                                    close_position_reason = f"ราคาต่ำสุดของแท่งเทียน ({latest_candle['low']:.6f}) สูงกว่าเส้น TOP ({top:.6f})"
                            
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
            
            self.console.print(f"[blue]===== สรุปการสแกน positions =====[/blue]")
            self.console.print(f"[blue]ตรวจสอบ: {positions_checked}/{len(positions)} positions[/blue]")
            self.console.print(f"[blue]ปิด: {positions_closed} positions[/blue]")
            
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน positions: {str(e)}[/red]")

    def scan_market(self):
        """สแกนตลาดเพื่อหาสัญญาณการเทรดและจัดการ positions"""
        first_run = True
        stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
        
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                
                if current_time.minute % 15 == 0 or first_run:
                    self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    first_run = False
                    
                    scan_stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
                    
                    self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                    self.scan_positions()
                    
                    self.console.print(f"[blue]📊 ตรวจหาสัญญาณเทรดใหม่[/blue]")
                    contracts = self.get_futures_contracts()
                    
                    for i, contract in enumerate(contracts, 1):
                        self.console.print(f"[cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract}[/cyan]")
                        df = self.get_candlesticks(contract)
                        
                        if not df.empty and len(df) >= 1:  # ต้องมีอย่างน้อย 1 แท่งเทียน
                            lrc_data = self.calculate_linear_regression_channel(df)
                            
                            if lrc_data:
                                slope_direction = "ขาขึ้น 📈" if lrc_data['slope'] > 0 else "ขาลง 📉" if lrc_data['slope'] < 0 else "แนวราบ ➡️"
                                latest_price = self.get_latest_price(contract)
                                
                                self.console.print(f"[magenta]   Linear Regression Channel:[/magenta]")
                                self.console.print(f"[magenta]   TOP={lrc_data['TOP']:.6f}, TOPMIDDLE={lrc_data['TOPMIDDLE']:.6f}, MIDDLE={lrc_data['MIDDLE']:.6f}, MIDDLEBOTTOM={lrc_data['MIDDLEBOTTOM']:.6f}, BOTTOM={lrc_data['BOTTOM']:.6f}[/magenta]")
                                self.console.print(f"[magenta]   Slope={lrc_data['slope']:.6f} ({slope_direction}), ราคาล่าสุด={latest_price:.6f}[/magenta]")
                                
                                # ใช้แท่งเทียนล่าสุด
                                latest_candle = df.iloc[-1].to_dict()
                                candle_type = "สีเขียว 🟩" if latest_candle['close'] > latest_candle['open'] else "สีแดง 🟥" if latest_candle['close'] < latest_candle['open'] else "Doji ⬛"
                                self.console.print(f"[magenta]   แท่งเทียนล่าสุด: {candle_type} - High: {latest_candle['high']:.6f}, Low: {latest_candle['low']:.6f}[/magenta]")
                                
                                signal = self.check_trading_signal(df, lrc_data, contract)
                                
                                if signal == "BUY":
                                    scan_stats['buy_signals'] += 1
                                    existing_pos = self.check_existing_position(contract)
                                    if existing_pos and float(existing_pos['size']) < 0:
                                        self.console.print(f"[yellow]🔄 มี SHORT position อยู่ ต้องปิดก่อนเปิด LONG[/yellow]")
                                        if self.close_position(contract, existing_pos):
                                            scan_stats['positions_closed'] += 1
                                            if self.create_order(contract, True):
                                                scan_stats['long_opened'] += 1
                                    elif not existing_pos:
                                        self.console.print(f"[yellow]🆕 ไม่มี position อยู่ เปิด LONG ได้เลย[/yellow]")
                                        if self.create_order(contract, True):
                                            scan_stats['long_opened'] += 1
                                    else:
                                        self.console.print(f"[yellow]⏩ มี LONG position อยู่แล้ว ไม่ต้องทำอะไร[/yellow]")
                                elif signal == "SELL":
                                    scan_stats['sell_signals'] += 1
                                    existing_pos = self.check_existing_position(contract)
                                    if existing_pos and float(existing_pos['size']) > 0:
                                        self.console.print(f"[yellow]🔄 มี LONG position อยู่ ต้องปิดก่อนเปิด SHORT[/yellow]")
                                        if self.close_position(contract, existing_pos):
                                            scan_stats['positions_closed'] += 1
                                            if self.create_order(contract, False):
                                                scan_stats['short_opened'] += 1
                                    elif not existing_pos:
                                        self.console.print(f"[yellow]🆕 ไม่มี position อยู่ เปิด SHORT ได้เลย[/yellow]")
                                        if self.create_order(contract, False):
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
                    
                    for key in stats: stats[key] += scan_stats[key]
                    
                    self.console.print(f"[blue]===== สรุปการสแกนรอบนี้ =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกน: {scan_stats['contracts_scanned']}/{len(contracts)}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ BUY: {scan_stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SELL: {scan_stats['sell_signals']}[/red]")
                    self.console.print(f"[green]📈 เปิด LONG: {scan_stats['long_opened']}[/green]")
                    self.console.print(f"[red]📉 เปิด SHORT: {scan_stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position: {scan_stats['positions_closed']}[/yellow]")
                    
                    self.console.print(f"[blue]===== สถิติรวมทั้งหมด =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกนทั้งหมด: {stats['contracts_scanned']}[/blue]")
                    self.console.print(f"[green]📈 สัญญาณ BUY ทั้งหมด: {stats['buy_signals']}[/green]")
                    self.console.print(f"[red]📉 สัญญาณ SELL ทั้งหมด: {stats['sell_signals']}[/red]")
                    self.console.print(f"[green]📈 เปิด LONG ทั้งหมด: {stats['long_opened']}[/green]")
                    self.console.print(f"[red]📉 เปิด SHORT ทั้งหมด: {stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position ทั้งหมด: {stats['positions_closed']}[/yellow]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    
                    time.sleep(30)
                
                time.sleep(10)
            except Exception as e:
                self.console.print(f"[red]❌ เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}[/red]")
                time.sleep(60)

def main():
    trader = GateIOLinearRegressionTrader()
    trader.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย Linear Regression Channel...[/blue]")
    trader.scan_market()

if __name__ == "__main__":
    main()