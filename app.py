import os, time, re
from typing import List, Dict
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
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client, self.futures_api = ApiClient(config), FuturesApi(ApiClient(config))
        self.leverage, self.order_amount, self.rsi_period = 10, 20, 14  # ตั้งค่าพารามิเตอร์การเทรด
        self.lookback_period, self.console = 100, Console()  # จำนวนแท่งเทียนที่ใช้วิเคราะห์และ console แสดงผล

    def calculate_rsi(self, df: pd.DataFrame) -> pd.Series:
        """คำนวณ Relative Strength Index (RSI)"""
        delta = df['close'].diff()
        gain, loss = delta.where(delta > 0, 0), -delta.where(delta < 0, 0)
        avg_gain, avg_loss = gain.rolling(window=self.rsi_period).mean(), loss.rolling(window=self.rsi_period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def find_swing_high_low(self, df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
        """หาจุด Swing High และ Swing Low"""
        df = df.copy()
        df['swing_high'], df['swing_low'] = False, False
        for i in range(window, len(df) - window):
            if all(df['high'].iloc[i] > df['high'].iloc[i-window:i]) and all(df['high'].iloc[i] > df['high'].iloc[i+1:i+window+1]):
                df.loc[df.index[i], 'swing_high'] = True
            if all(df['low'].iloc[i] < df['low'].iloc[i-window:i]) and all(df['low'].iloc[i] < df['low'].iloc[i+1:i+window+1]):
                df.loc[df.index[i], 'swing_low'] = True
        return df

    def check_rsi_divergence(self, df: pd.DataFrame) -> dict:
        """ตรวจหา RSI Divergence ทั้ง Bullish และ Bearish"""
        if len(df) < self.lookback_period: return {}
        result = {'bullish_divergence': False, 'bearish_divergence': False}
        
        # คำนวณ RSI และหา swing points
        df = df.copy(); df['rsi'] = self.calculate_rsi(df); df = self.find_swing_high_low(df)
        recent_df = df.iloc[-30:].copy()  # ใช้ 30 แท่งล่าสุดเพื่อหา divergence
        
        # หา swing high/low ล่าสุด 2 จุด
        swing_highs = recent_df[recent_df['swing_high']].iloc[-2:] if len(recent_df[recent_df['swing_high']]) >= 2 else None
        swing_lows = recent_df[recent_df['swing_low']].iloc[-2:] if len(recent_df[recent_df['swing_low']]) >= 2 else None
        
        # ตรวจหา Bearish Divergence (ราคาสูงขึ้น แต่ RSI ลดลง)
        if swing_highs is not None and len(swing_highs) == 2:
            price_higher, rsi_lower = swing_highs.iloc[1]['high'] > swing_highs.iloc[0]['high'], swing_highs.iloc[1]['rsi'] < swing_highs.iloc[0]['rsi']
            if price_higher and rsi_lower:
                result['bearish_divergence'] = True
                self.console.print(f"[red]🔍 พบ Bearish Divergence! ราคา: {swing_highs.iloc[0]['high']:.6f} -> {swing_highs.iloc[1]['high']:.6f}, RSI: {swing_highs.iloc[0]['rsi']:.2f} -> {swing_highs.iloc[1]['rsi']:.2f}[/red]")
        
        # ตรวจหา Bullish Divergence (ราคาต่ำลง แต่ RSI สูงขึ้น)
        if swing_lows is not None and len(swing_lows) == 2:
            price_lower, rsi_higher = swing_lows.iloc[1]['low'] < swing_lows.iloc[0]['low'], swing_lows.iloc[1]['rsi'] > swing_lows.iloc[0]['rsi']
            if price_lower and rsi_higher:
                result['bullish_divergence'] = True
                self.console.print(f"[green]🔍 พบ Bullish Divergence! ราคา: {swing_lows.iloc[0]['low']:.6f} -> {swing_lows.iloc[1]['low']:.6f}, RSI: {swing_lows.iloc[0]['rsi']:.2f} -> {swing_lows.iloc[1]['rsi']:.2f}[/green]")
        
        # คำนวณ HIGHPRICE และ LOWPRICE
        if len(df) >= (self.rsi_period + 2):
            high_prices, low_prices = df['high'].iloc[-(self.rsi_period+2):-2], df['low'].iloc[-(self.rsi_period+2):-2]
            result['HIGHPRICE'], result['LOWPRICE'] = high_prices.max(), low_prices.min()
            self.console.print(f"[blue]📊 HIGHPRICE={result['HIGHPRICE']:.6f}, LOWPRICE={result['LOWPRICE']:.6f}[/blue]")
        
        # แสดงค่า RSI ล่าสุด
        if len(df) > 0 and not np.isnan(df['rsi'].iloc[-1]):
            result['current_rsi'] = df['rsi'].iloc[-1]
            self.console.print(f"[blue]📊 RSI ล่าสุด = {result['current_rsi']:.2f}[/blue]")
        
        return result

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

    def get_latest_price(self, contract: str) -> float:
        """ดึงราคาล่าสุดของสัญญา"""
        ticker = self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract == contract:
                return float(t.last)
        self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
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
            direction = abs(size) if size < 0 else -size  # ใช้ค่าตรงข้ามกับ size ปัจจุบันเพื่อปิด position
            self.futures_api.create_futures_order('usdt', {
                'contract': contract, 'size': direction, 'price': 0,  # market order
                'tif': 'ioc', 'reduce_only': True  # immediate-or-cancel, เพื่อปิด position เท่านั้น
            })
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
            
            # คำนวณขนาด position และสร้างคำสั่งซื้อ
            usd_value, size = self.order_amount * self.leverage, max(min_size, round(self.order_amount * self.leverage / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract, 'size': size, 'price': 0,  # market order
                'tif': 'ioc', 'reduce_only': False  # immediate-or-cancel, เพื่อเปิด position ใหม่
            })
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
            
            # คำนวณขนาด position และสร้างคำสั่งขาย
            usd_value, size = self.order_amount * self.leverage, max(min_size, round(self.order_amount * self.leverage / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract, 'size': -size, 'price': 0,  # ค่าลบเพื่อ short, market order
                'tif': 'ioc', 'reduce_only': False  # immediate-or-cancel, เพื่อเปิด position ใหม่
            })
            self.console.print(f"[red]เปิด position SHORT: {contract} ขนาด={size}[/red]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด SHORT สำหรับ {contract}: {str(e)}[/red]")
            return None

    def check_trading_signal(self, df: pd.DataFrame, divergence_data: dict, contract: str = None) -> str:
        """ตรวจสอบสัญญาณการเทรดตามเงื่อนไขที่กำหนดใหม่"""
        if not divergence_data or len(df) < 1: return None
        
        # ตรวจสอบสัญญาณ Bullish/Bearish Divergence
        if divergence_data.get('bullish_divergence', False):
            self.console.print(f"[green]สัญญาณ BUY: พบ Bullish Divergence[/green]")
            return "BUY"
        if divergence_data.get('bearish_divergence', False):
            self.console.print(f"[red]สัญญาณ SELL: พบ Bearish Divergence[/red]")
            return "SELL"
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
                if not df.empty:
                    # ตรวจสอบ RSI Divergence
                    divergence_data = self.check_rsi_divergence(df)
                    if divergence_data:
                        latest_price = self.get_latest_price(contract)
                        if latest_price:
                            # คำนวณกำไร/ขาดทุนเป็น %
                            pnl_percentage = ((latest_price - entry_price) / entry_price) * 100 if size > 0 else ((entry_price - latest_price) / entry_price) * 100
                            pnl_color = "green" if pnl_percentage > 0 else "red"
                            self.console.print(f"[{pnl_color}]   P&L: {pnl_percentage:.2f}%[/{pnl_color}]")
                            
                            # ตรวจสอบเงื่อนไขการปิด position ตามที่กำหนดใหม่
                            close_position_reason = None
                            if len(df) >= 2:
                                prev_candle = df.iloc[-2]
                                # ปิด long position ถ้าราคาต่ำสุดของแท่งก่อนหน้า อยู่ต่ำกว่า LOWPRICE
                                if size > 0 and 'LOWPRICE' in divergence_data and prev_candle['low'] < divergence_data['LOWPRICE']:
                                    close_position_reason = f"ราคาต่ำสุดของแท่งก่อนหน้า ({prev_candle['low']:.6f}) ต่ำกว่า LOWPRICE ({divergence_data['LOWPRICE']:.6f})"
                                # ปิด short position ถ้าราคาสูงสุดของแท่งก่อนหน้า อยู่สูงกว่า HIGHPRICE
                                elif size < 0 and 'HIGHPRICE' in divergence_data and prev_candle['high'] > divergence_data['HIGHPRICE']:
                                    close_position_reason = f"ราคาสูงสุดของแท่งก่อนหน้า ({prev_candle['high']:.6f}) สูงกว่า HIGHPRICE ({divergence_data['HIGHPRICE']:.6f})"
                            
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
                        self.console.print(f"[red]❌ ไม่สามารถตรวจหา RSI Divergence สำหรับ {contract} ได้[/red]")
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
                    
                    # สแกน positions ที่มีอยู่และตรวจหาสัญญาณเทรดใหม่
                    self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                    self.scan_positions()
                    self.console.print(f"[blue]📊 ตรวจหาสัญญาณเทรดใหม่[/blue]")
                    contracts = self.get_futures_contracts()
                    
                    # ตรวจสอบแต่ละสัญญา
                    for i, contract in enumerate(contracts, 1):
                        self.console.print(f"[cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract}[/cyan]")
                        df = self.get_candlesticks(contract)
                        
                        if not df.empty:
                            # ตรวจสอบ RSI Divergence
                            divergence_data = self.check_rsi_divergence(df)
                            if divergence_data:
                                # แสดงค่า RSI ล่าสุด
                                if 'current_rsi' in divergence_data:
                                    rsi_value = divergence_data['current_rsi']
                                    rsi_color = "green" if rsi_value > 50 else "red"
                                    self.console.print(f"[{rsi_color}]   RSI ล่าสุด: {rsi_value:.2f}[/{rsi_color}]")
                                
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
                                self.console.print(f"[red]❌ ไม่สามารถตรวจหา RSI Divergence สำหรับ {contract} ได้[/red]")
                        else:
                            self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                    
                    # อัพเดตสถิติรวมและแสดงผลสรุป
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