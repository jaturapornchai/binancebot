import os, time, re
from typing import List, Dict, Tuple
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console

class GateIORSIDivergenceTrader:
    def __init__(self):
        load_dotenv()
        self.api_key, self.secret_key = os.getenv('GATEIO_API_KEY'), os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env")
        
        # ตั้งค่า API client
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        
        # ตั้งค่าพารามิเตอร์การเทรด
        self.leverage = 10
        self.order_amount = 20  # จำนวนเงิน USD ต่อการเปิดออเดอร์
        self.rsi_period = 14  # ช่วงเวลาสำหรับคำนวณ RSI
        self.swing_lookback = 14  # จำนวนแท่งเทียนที่ใช้มองหา swing high/low
        
        # สร้าง console สำหรับแสดงผล
        self.console = Console()

    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ"""
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = []
        pattern = re.compile(r'^\D+_USDT$')
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                # ตรวจสอบสภาพคล่อง (Volume 24h > $100,000)
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

    def calculate_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """คำนวณ Relative Strength Index (RSI)"""
        if len(df) < self.rsi_period + 5: return df
        
        # คำนวณการเปลี่ยนแปลงของราคา
        df['price_change'] = df['close'].diff()
        
        # แยกการเปลี่ยนแปลงเป็นบวกและลบ
        df['gain'] = np.where(df['price_change'] > 0, df['price_change'], 0)
        df['loss'] = np.where(df['price_change'] < 0, -df['price_change'], 0)
        
        # คำนวณค่าเฉลี่ยของ gain และ loss
        df['avg_gain'] = df['gain'].rolling(window=self.rsi_period).mean()
        df['avg_loss'] = df['loss'].rolling(window=self.rsi_period).mean()
        
        # คำนวณ RS และ RSI
        df['rs'] = df['avg_gain'] / df['avg_loss']
        df['rsi'] = 100 - (100 / (1 + df['rs']))
        
        return df

    def find_swings(self, df: pd.DataFrame) -> Tuple[List[int], List[int]]:
        """หา swing high และ swing low ในข้อมูล"""
        if len(df) < self.swing_lookback + 5: return [], []
        
        swing_highs = []
        swing_lows = []
        
        for i in range(self.swing_lookback, len(df) - self.swing_lookback):
            # Swing High: จุดสูงสุดที่มีแท่งเทียนต่ำกว่าทั้ง 2 ข้าง
            if all(df['high'].iloc[i] > df['high'].iloc[i-j] for j in range(1, self.swing_lookback//2+1)) and \
               all(df['high'].iloc[i] > df['high'].iloc[i+j] for j in range(1, self.swing_lookback//2+1)):
                swing_highs.append(i)
                
            # Swing Low: จุดต่ำสุดที่มีแท่งเทียนสูงกว่าทั้ง 2 ข้าง
            if all(df['low'].iloc[i] < df['low'].iloc[i-j] for j in range(1, self.swing_lookback//2+1)) and \
               all(df['low'].iloc[i] < df['low'].iloc[i+j] for j in range(1, self.swing_lookback//2+1)):
                swing_lows.append(i)
                
        return swing_highs, swing_lows

    def check_divergence(self, df: pd.DataFrame) -> Dict:
        """ตรวจหา RSI Divergence ทั้ง Bullish และ Bearish"""
        if 'rsi' not in df.columns or len(df) < 50: return {}
        
        # หา swing high และ swing low
        swing_highs, swing_lows = self.find_swings(df)
        
        # กำหนดจำนวนแท่งเทียนล่าสุดที่จะตรวจสอบ
        recent_bars = 50  
        last_bars = min(len(df), recent_bars)
        
        # ตรวจหา Bearish Divergence (ราคาทำจุดสูงขึ้น แต่ RSI ทำจุดต่ำลง)
        bearish_divergence = False
        # กรองเฉพาะ swing highs ที่อยู่ในช่วง recent_bars
        recent_swing_highs = [i for i in swing_highs if i >= len(df) - last_bars]
        
        if len(recent_swing_highs) >= 2:
            # เรียงลำดับจากใหม่ไปเก่า
            recent_swing_highs = sorted(recent_swing_highs, reverse=True)
            latest_high, prev_high = recent_swing_highs[0], recent_swing_highs[1]
            
            # ตรวจสอบว่าราคาทำจุดสูงขึ้น แต่ RSI ทำจุดต่ำลง
            if df['high'].iloc[latest_high] > df['high'].iloc[prev_high] and \
               df['rsi'].iloc[latest_high] < df['rsi'].iloc[prev_high]:
                bearish_divergence = True
        
        # ตรวจหา Bullish Divergence (ราคาทำจุดต่ำลง แต่ RSI ทำจุดสูงขึ้น)
        bullish_divergence = False
        # กรองเฉพาะ swing lows ที่อยู่ในช่วง recent_bars
        recent_swing_lows = [i for i in swing_lows if i >= len(df) - last_bars]
        
        if len(recent_swing_lows) >= 2:
            # เรียงลำดับจากใหม่ไปเก่า
            recent_swing_lows = sorted(recent_swing_lows, reverse=True)
            latest_low, prev_low = recent_swing_lows[0], recent_swing_lows[1]
            
            # ตรวจสอบว่าราคาทำจุดต่ำลง แต่ RSI ทำจุดสูงขึ้น
            if df['low'].iloc[latest_low] < df['low'].iloc[prev_low] and \
               df['rsi'].iloc[latest_low] > df['rsi'].iloc[prev_low]:
                bullish_divergence = True
        
        # คำนวณ HIGHPRICE และ LOWPRICE
        relevant_data = df.iloc[-self.rsi_period-1:-1]  # ไม่รวมแท่งปัจจุบัน
        highprice = relevant_data['high'].max()
        lowprice = relevant_data['low'].min()
        
        return {
            'bullish_divergence': bullish_divergence,
            'bearish_divergence': bearish_divergence,
            'highprice': highprice,
            'lowprice': lowprice
        }

    def get_latest_price(self, contract: str) -> float:
        """ดึงราคาล่าสุดของสัญญา"""
        ticker = self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract == contract:
                return float(t.last)
        self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
        return None

    def check_trading_signal(self, df: pd.DataFrame, divergence_data: dict, contract: str = None) -> str:
        """ตรวจสอบสัญญาณการเทรดตามเงื่อนไข RSI Divergence"""
        if not divergence_data or len(df) < 1: return None
        
        # ดึงราคาล่าสุด
        latest_price = self.get_latest_price(contract)
        if latest_price is None: return None
        
        highprice = divergence_data.get('highprice')
        lowprice = divergence_data.get('lowprice')
        bullish_divergence = divergence_data.get('bullish_divergence')
        bearish_divergence = divergence_data.get('bearish_divergence')
        
        # แสดงข้อมูลเพื่อวิเคราะห์
        last_rsi = df['rsi'].iloc[-1] if 'rsi' in df.columns else None
        rsi_display = f"{last_rsi:.2f}" if last_rsi is not None else "N/A"
        self.console.print(f"[blue]   การตรวจสอบสัญญาณ: ราคาล่าสุด={latest_price:.6f}, RSI={rsi_display}[/blue]")
        self.console.print(f"[blue]   HIGHPRICE={highprice:.6f}, LOWPRICE={lowprice:.6f}[/blue]")
        self.console.print(f"[blue]   Bullish Divergence={bullish_divergence}, Bearish Divergence={bearish_divergence}[/blue]")
        
        # เงื่อนไขเทรด: BUY=เมื่อเกิดสัญญาณ RSI Bullish Divergence
        if bullish_divergence:
            self.console.print(f"[green]สัญญาณ BUY: พบ RSI Bullish Divergence[/green]")
            return "SELL" # "BUY"
        
        # เงื่อนไขเทรด: SELL=เมื่อเกิดสัญญาณ RSI Bearish Divergence
        if bearish_divergence:
            self.console.print(f"[red]สัญญาณ SELL: พบ RSI Bearish Divergence[/red]")
            return "BUY" #"SELL"
        
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
        """สแกน positions ที่เปิดอยู่และตรวจสอบเงื่อนไขการปิด position"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            
            positions_checked, positions_closed = 0, 0
            
            for pos in positions:
                contract = pos['contract']
                size = float(pos['size'])
                position_type = "LONG 📈" if size > 0 else "SHORT 📉" if size < 0 else "NONE"
                entry_price = float(pos['entry_price'])
                
                self.console.print(f"[cyan]▶ ตรวจสอบ: {contract} ({position_type}) - ราคาเข้า: {entry_price:.6f} - ขนาด: {abs(size)}[/cyan]")
                
                df = self.get_candlesticks(contract)
                
                if not df.empty:
                    df = self.calculate_rsi(df)
                    divergence_data = self.check_divergence(df)
                    
                    if divergence_data:
                        latest_price = self.get_latest_price(contract)
                        
                        if latest_price:
                            highprice = divergence_data['highprice']
                            lowprice = divergence_data['lowprice']
                            
                            # แสดงข้อมูล RSI ล่าสุด
                            last_rsi = df['rsi'].iloc[-1] if 'rsi' in df.columns else None
                            rsi_display = f"{last_rsi:.2f}" if last_rsi is not None else "N/A"
                            self.console.print(f"[magenta]   ข้อมูล RSI:[/magenta]")
                            self.console.print(f"[magenta]   RSI ล่าสุด={rsi_display} - HIGHPRICE={highprice:.6f}, LOWPRICE={lowprice:.6f}[/magenta]")
                            
                            # คำนวณกำไร/ขาดทุนเป็น %
                            pnl_percentage = ((latest_price - entry_price) / entry_price) * 100 if size > 0 else ((entry_price - latest_price) / entry_price) * 100
                            pnl_color = "green" if pnl_percentage > 0 else "red"
                            self.console.print(f"[{pnl_color}]   P&L: {pnl_percentage:.2f}%[/{pnl_color}]")
                            
                            # ตรวจสอบเงื่อนไขการปิด position ตามที่กำหนดใหม่
                            close_position_reason = None
                            
                            # ปิด long position ถ้าราคาล่าสุดอยู่ต่ำกว่า LOWPRICE
                            if size > 0 and latest_price < lowprice:
                                close_position_reason = f"ราคาล่าสุด ({latest_price:.6f}) ต่ำกว่า LOWPRICE ({lowprice:.6f})"
                            # ปิด short position ถ้าราคาล่าสุดอยู่สูงกว่า HIGHPRICE
                            elif size < 0 and latest_price > highprice:
                                close_position_reason = f"ราคาล่าสุด ({latest_price:.6f}) สูงกว่า HIGHPRICE ({highprice:.6f})"
                            
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
                        self.console.print(f"[red]❌ ไม่สามารถตรวจสอบ Divergence สำหรับ {contract} ได้[/red]")
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
        stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
        
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                
                # ทำงานทุกต้นชั่วโมงและนาทีที่ 15, 30, 45 หรือเมื่อเริ่มต้นโปรแกรม
                if current_time.minute % 15 == 0 or first_run:
                    self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    first_run = False
                    
                    # ตัวแปรเก็บสถิติการสแกนรอบนี้
                    scan_stats = {'contracts_scanned': 0, 'buy_signals': 0, 'sell_signals': 0, 'long_opened': 0, 'short_opened': 0, 'positions_closed': 0}
                    
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
                            # คำนวณ RSI และตรวจสอบ Divergence
                            df = self.calculate_rsi(df)
                            divergence_data = self.check_divergence(df)
                            
                            if divergence_data:
                                # แสดงข้อมูล RSI ล่าสุด
                                last_rsi = df['rsi'].iloc[-1] if 'rsi' in df.columns else None
                                highprice = divergence_data['highprice']
                                lowprice = divergence_data['lowprice']
                                latest_price = self.get_latest_price(contract)
                                
                                rsi_display = f"{last_rsi:.2f}" if last_rsi is not None else "N/A"
                                self.console.print(f"[magenta]   ข้อมูล RSI:[/magenta]")
                                self.console.print(f"[magenta]   RSI ล่าสุด={rsi_display} - HIGHPRICE={highprice:.6f}, LOWPRICE={lowprice:.6f}[/magenta]")
                                
                                # ตรวจสอบสัญญาณการเทรด
                                signal = self.check_trading_signal(df, divergence_data, contract)
                                
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
                                self.console.print(f"[red]❌ ไม่สามารถตรวจสอบ Divergence สำหรับ {contract} ได้[/red]")
                        else:
                            self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                    
                    # อัพเดตสถิติรวม
                    for key in stats: stats[key] += scan_stats[key]
                    
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
    trader = GateIORSIDivergenceTrader()
    trader.console.print("[blue]เริ่มต้นระบบเทรดอัตโนมัติด้วย RSI Divergence...[/blue]")
    trader.scan_market()

if __name__ == "__main__":
    main()