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
        self.api_key, self.secret_key = os.getenv('GATEIO_API_KEY'), os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client, self.futures_api = ApiClient(config), FuturesApi(ApiClient(config))
        self.leverage, self.order_amount = 10, 50
        self.lookback_period, self.devlen = 100, 2.0
        self.console = Console()

    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องเพียงพอ"""
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = [c.contract for c in ticket if re.match(r'^\D+_USDT$', c.contract) and c.contract not in ['USDC_USDT', 'DOGS_USDT'] and float(c.volume_24h) * float(c.last) > 100000]
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
        """คำนวณ Linear Regression Channel พร้อมเส้น TOP MIDDLE และ BOTTOM"""
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
        
        # ปรับขนาด channel หากมีค่าผิดปกติ
        if (top - latest_price) / latest_price > 1.0 or (latest_price - bottom) / latest_price > 1.0:
            self.console.print(f"[yellow]⚠️ ปรับขนาด channel เนื่องจากค่าเดิมไม่สมเหตุสมผล[/yellow]")
            reasonable_dev = latest_price * 0.05
            top, bottom = middle + reasonable_dev * self.devlen, middle - reasonable_dev * self.devlen
            topmiddle, middlebottom = (top + middle) / 2, (middle + bottom) / 2
        
        # ปรับค่า BOTTOM หากเป็นค่าลบ
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

    def is_touching(self, candle, value, is_top=True) -> bool:
        """ตรวจสอบว่าแท่งเทียนทับเส้นหรือไม่"""
        tolerance = value * 0.001  # ค่าความคลาดเคลื่อนที่ยอมรับได้
        high_or_low = candle['high'] if is_top else candle['low']
        return abs(high_or_low - value) < tolerance

    def get_latest_price(self, contract: str) -> float:
        """ดึงราคาล่าสุดของสัญญา"""
        for t in self.futures_api.list_futures_tickers(settle='usdt'):
            if t.contract == contract: return float(t.last)
        self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
        return None

    def check_trading_signal(self, df: pd.DataFrame, lrc_data: dict, contract: str = None) -> str:
        """ตรวจสอบสัญญาณการเทรดตามเงื่อนไข"""
        if not lrc_data or len(df) < 1: return None
        
        latest_candle = df.iloc[-1]
        latest_price = self.get_latest_price(contract)
        if latest_price is None: return None
        
        # เงื่อนไข: CANDLE เป็นสีแดง (ทับเส้น TOP หรือ BOTTOM) และ LRC เป็นขาลง
        is_red = latest_candle['close'] < latest_candle['open']
        touches_top = self.is_touching(latest_candle, lrc_data['TOP'], is_top=True)
        touches_bottom = self.is_touching(latest_candle, lrc_data['BOTTOM'], is_top=False)
        is_downtrend = lrc_data['slope'] < 0
        
        self.console.print(f"[blue]   ตรวจสอบสัญญาณ: ราคาล่าสุด={latest_price:.6f}[/blue]")
        self.console.print(f"[blue]   เงื่อนไข: แท่งเทียนสีแดง={is_red}, ทับ TOP={touches_top}, ทับ BOTTOM={touches_bottom}, ขาลง={is_downtrend}[/blue]")
        
        if is_red and (touches_top or touches_bottom) and is_downtrend:
            touch_point = "TOP" if touches_top else "BOTTOM"
            self.console.print(f"[red]🔴 สัญญาณ SELL: แท่งเทียนสีแดง, ทับเส้น {touch_point}, LRC ขาลง (slope={lrc_data['slope']:.6f})[/red]")
            return "SELL"
        
        return None

    def check_existing_position(self, contract: str) -> Dict:
        """ตรวจสอบว่ามี position ที่เปิดอยู่หรือไม่"""
        for p in self.futures_api.list_positions(settle='usdt', holding=True):
            if p.contract == contract:
                pos_info = p.to_dict()
                size = float(pos_info['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                self.console.print(f"[yellow]พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                return pos_info
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
            self.futures_api.create_futures_order('usdt', {
                'contract': contract, 'size': direction, 'price': 0,
                'tif': 'ioc', 'reduce_only': True
            })
            self.console.print(f"[green]✅ ปิด position {'LONG' if size > 0 else 'SHORT'} สำหรับ {contract}: ขนาด={abs(size)}[/green]")
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
            
            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract, 'size': size if is_long else -size,
                'price': 0, 'tif': 'ioc', 'reduce_only': False
            })
            
            position_type = "LONG" if is_long else "SHORT"
            self.console.print(f"[{'green' if is_long else 'red'}]✅ เปิด position {position_type}: {contract} ขนาด={size}[/{'green' if is_long else 'red'}]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด {'LONG' if is_long else 'SHORT'} สำหรับ {contract}: {str(e)}[/red]")
            return None

    def scan_positions(self):
        """สแกน positions ที่เปิดอยู่เพื่อทำการปิดตามเงื่อนไข"""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            self.console.print(f"[blue]===== สแกน {len(positions)} positions ที่เปิดอยู่ =====[/blue]")
            
            positions_checked, positions_closed = 0, 0
            
            for pos in positions:
                contract, size = pos['contract'], float(pos['size'])
                position_type = "LONG 📈" if size > 0 else "SHORT 📉" if size < 0 else "NONE"
                entry_price = float(pos['entry_price'])
                
                self.console.print(f"[cyan]▶ ตรวจสอบ: {contract} ({position_type}) - ราคาเข้า: {entry_price:.6f} - ขนาด: {abs(size)}[/cyan]")
                
                latest_price = self.get_latest_price(contract)
                if not latest_price:
                    self.console.print(f"[red]❌ ไม่สามารถดึงราคาล่าสุดของ {contract} ได้[/red]")
                    continue
                
                # คำนวณ P&L เป็นเปอร์เซ็นต์
                pnl_percentage = ((latest_price - entry_price) / entry_price) * 100 if size > 0 else ((entry_price - latest_price) / entry_price) * 100
                self.console.print(f"[{'green' if pnl_percentage > 0 else 'red'}]   P&L: {pnl_percentage:.2f}%[/{'green' if pnl_percentage > 0 else 'red'}]")
                
                # ปิด SHORT position ตามเงื่อนไข (กำไรมากกว่า 1.5% หรือขาดทุนมากกว่า 1.25%)
                close_position_reason = None
                if size < 0:  # เฉพาะ SHORT position
                    if (pnl_percentage > 0 and pnl_percentage > 1.5) or (pnl_percentage < 0 and abs(pnl_percentage) > 1.25):
                        close_position_reason = f"{'กำไร' if pnl_percentage > 0 else 'ขาดทุน'} {abs(pnl_percentage):.2f}% > {'1.5' if pnl_percentage > 0 else '1.25'}%"
                
                if close_position_reason:
                    self.console.print(f"[yellow]🔔 ปิด SHORT position: {contract} เนื่องจาก {close_position_reason}[/yellow]")
                    if self.close_position(contract, pos):
                        positions_closed += 1
                else:
                    self.console.print(f"[blue]   ยังไม่เข้าเงื่อนไขการปิด position[/blue]")
                
                positions_checked += 1
            
            self.console.print(f"[blue]สรุป: ตรวจสอบ {positions_checked}/{len(positions)}, ปิด {positions_closed} positions[/blue]")
            return positions_closed
            
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการสแกน positions: {str(e)}[/red]")
            return 0

    def scan_market(self):
        """สแกนตลาดเพื่อหาสัญญาณการเทรดและจัดการ positions"""
        first_run = True
        stats = {'contracts_scanned': 0, 'sell_signals': 0, 'short_opened': 0, 'positions_closed': 0}
        
        while True:
            try:
                current_time = pd.Timestamp.now(tz='Asia/Bangkok')
                
                if current_time.minute % 15 == 0 or first_run:
                    self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    first_run = False
                    
                    scan_stats = {'contracts_scanned': 0, 'sell_signals': 0, 'short_opened': 0, 'positions_closed': 0}
                    
                    # ตรวจสอบ Positions ที่มีอยู่
                    self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                    scan_stats['positions_closed'] = self.scan_positions()
                    
                    # ตรวจหาสัญญาณเทรดใหม่
                    self.console.print(f"[blue]📊 ตรวจหาสัญญาณเทรดใหม่[/blue]")
                    contracts = self.get_futures_contracts()
                    
                    for i, contract in enumerate(contracts, 1):
                        self.console.print(f"[cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract}[/cyan]")
                        df = self.get_candlesticks(contract)
                        
                        if df.empty:
                            self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                            continue
                            
                        lrc_data = self.calculate_linear_regression_channel(df)
                        if not lrc_data:
                            self.console.print(f"[red]❌ ไม่สามารถคำนวณ Linear Regression Channel สำหรับ {contract} ได้[/red]")
                            continue
                        
                        latest_price = self.get_latest_price(contract)
                        slope_direction = "ขาขึ้น 📈" if lrc_data['slope'] > 0 else "ขาลง 📉" if lrc_data['slope'] < 0 else "แนวราบ ➡️"
                        
                        self.console.print(f"[magenta]   Linear Regression Channel:[/magenta]")
                        self.console.print(f"[magenta]   TOP={lrc_data['TOP']:.6f}, MIDDLE={lrc_data['MIDDLE']:.6f}, BOTTOM={lrc_data['BOTTOM']:.6f}[/magenta]")
                        self.console.print(f"[magenta]   Slope={lrc_data['slope']:.6f} ({slope_direction}), ราคาล่าสุด={latest_price:.6f}[/magenta]")
                        
                        # แสดงข้อมูลแท่งเทียนล่าสุด
                        latest_candle = df.iloc[-1]
                        candle_type = "สีเขียว 🟩" if latest_candle['close'] > latest_candle['open'] else "สีแดง 🟥" if latest_candle['close'] < latest_candle['open'] else "Doji ⬛"
                        self.console.print(f"[magenta]   แท่งเทียนล่าสุด: {candle_type} - O: {latest_candle['open']:.6f}, H: {latest_candle['high']:.6f}, L: {latest_candle['low']:.6f}, C: {latest_candle['close']:.6f}[/magenta]")
                        
                        signal = self.check_trading_signal(df, lrc_data, contract)
                        
                        if signal == "SELL":
                            scan_stats['sell_signals'] += 1
                            
                            # เปิด SHORT ใหม่ตามเงื่อนไข
                            existing_position = self.check_existing_position(contract)
                            if not existing_position:
                                self.console.print(f"[yellow]🆕 เปิด SHORT position ตามสัญญาณ SELL[/yellow]")
                                if self.create_order(contract, False):  # false คือ SHORT
                                    scan_stats['short_opened'] += 1
                            else:
                                self.console.print(f"[yellow]⚠️ มี position อยู่แล้ว ไม่สามารถเปิด SHORT ได้[/yellow]")
                        else:
                            self.console.print(f"[blue]   ไม่พบสัญญาณเทรด[/blue]")
                        
                        scan_stats['contracts_scanned'] += 1
                    
                    # อัปเดตสถิติรวม
                    for key in stats: stats[key] += scan_stats[key]
                    
                    # แสดงสรุปการสแกน
                    self.console.print(f"[blue]===== สรุปการสแกนรอบนี้ =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกน: {scan_stats['contracts_scanned']}/{len(contracts)}[/blue]")
                    self.console.print(f"[red]📉 สัญญาณ SELL: {scan_stats['sell_signals']}[/red]")
                    self.console.print(f"[red]📉 เปิด SHORT: {scan_stats['short_opened']}[/red]")
                    self.console.print(f"[yellow]🔄 ปิด Position: {scan_stats['positions_closed']}[/yellow]")
                    
                    # แสดงสถิติรวมทั้งหมด
                    self.console.print(f"[blue]===== สถิติรวมทั้งหมด =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกนทั้งหมด: {stats['contracts_scanned']}[/blue]")
                    self.console.print(f"[red]📉 สัญญาณ SELL ทั้งหมด: {stats['sell_signals']}[/red]")
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