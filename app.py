import os, time, re, json
from typing import List, Dict, Tuple, Optional, Union
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from rich.console import Console
from datetime import datetime
class OptimizedShortTrader:
    def __init__(self):
        load_dotenv()
        self.api_key, self.secret_key = os.getenv('GATEIO_API_KEY'), os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key: raise ValueError("API keys ไม่พบในไฟล์ .env")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client, self.futures_api = ApiClient(config), FuturesApi(ApiClient(config))
        self.leverage, self.order_amount = 10, 50
        self.lookback_period, self.devlen = 100, 2.0
        self.console = Console()
        self.profit_threshold, self.loss_threshold = 1.5, 1.25
        self.max_positions, self.max_correlation = 5, 0.7
        self.market_config = {
            'min_volume_usd': 100000,
            'blacklist': ['USDC_USDT', 'DOGS_USDT'],
            'rsi_period': 14,
            'rsi_overbought': 70,
            'stochastic_period': 14,
            'stochastic_overbought': 80,
        }
        self.trade_history = {}
    def get_futures_contracts(self) -> List[str]:
        """ดึงรายชื่อสัญญา futures ที่มีสภาพคล่องและเรียงตามปริมาณและความผันผวน"""
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        contracts_data = [{
            'contract': c.contract,
            'volume_usd': float(c.volume_24h) * float(c.last),
            'volatility': (float(c.high_24h) - float(c.low_24h)) / float(c.last) * 100
        } for c in ticket if re.match(r'^\D+_USDT$', c.contract) 
          and c.contract not in self.market_config['blacklist']
          and float(c.volume_24h) * float(c.last) > self.market_config['min_volume_usd']]
        sorted_contracts = sorted(contracts_data, 
            key=lambda x: (x['volume_usd'] * 0.7) + (x['volatility'] * x['volume_usd'] * 0.3), 
            reverse=True)
        valid_contracts = [c['contract'] for c in sorted_contracts]
        self.console.print(f"[blue]พบสัญญาที่มีสภาพคล่องจำนวน {len(valid_contracts)} สัญญา (เรียงตามปริมาณและความผันผวน)[/blue]")
        return valid_contracts
    def get_candlesticks(self, contract: str, interval: str = '5m', limit: int = 500) -> pd.DataFrame:
        """ดึงข้อมูลแท่งเทียนจาก API และแปลงเป็น DataFrame"""
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval=interval, limit=limit)
        if not candles: return pd.DataFrame()
        df = pd.DataFrame([{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 
                          'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')
    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """คำนวณตัวชี้วัดทางเทคนิคทั้งหมดสำหรับการวิเคราะห์"""
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
        if (top - latest_price) / latest_price > 1.0 or (latest_price - bottom) / latest_price > 1.0:
            reasonable_dev = latest_price * 0.05
            top, bottom = middle + reasonable_dev * self.devlen, middle - reasonable_dev * self.devlen
            topmiddle, middlebottom = (top + middle) / 2, (middle + bottom) / 2
        if bottom < 0 and latest_price > 0:
            bottom = latest_price * 0.8
            middlebottom = (middle + bottom) / 2
        delta = df['close'].diff().dropna()
        gain, loss = delta.copy(), delta.copy()
        gain[gain < 0], loss[loss > 0] = 0, 0
        avg_gain = gain.rolling(window=self.market_config['rsi_period']).mean().abs()
        avg_loss = loss.rolling(window=self.market_config['rsi_period']).mean().abs()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=14).mean().iloc[-1]
        sma = df['close'].rolling(window=20).mean().iloc[-1]
        std = df['close'].rolling(window=20).std().iloc[-1]
        upper_band, lower_band = sma + (std * 2), sma - (std * 2)
        bb_width = (upper_band - lower_band) / sma
        short_trend = 1 if df['close'].iloc[-3:].mean() > df['close'].iloc[-6:-3].mean() else -1
        volume_trend = df['volume'].iloc[-5:].mean() / df['volume'].iloc[-20:-5].mean() if len(df) >= 20 else 1
        volume_price_trend = 1 if (df['close'].diff().iloc[-1] > 0 and df['volume'].iloc[-1] > df['volume'].iloc[-2]) or \
                            (df['close'].diff().iloc[-1] < 0 and df['volume'].iloc[-1] < df['volume'].iloc[-2]) else -1
        low_min = df['low'].rolling(window=14).min()
        high_max = df['high'].rolling(window=14).max()
        k = 100 * ((df['close'] - low_min) / (high_max - low_min))
        d = k.rolling(window=3).mean()
        return {
            'MIDDLE': middle, 'TOP': top, 'BOTTOM': bottom, 'TOPMIDDLE': topmiddle, 'MIDDLEBOTTOM': middlebottom,
            'slope': slope, 'dev': dev, 'rsi': rsi.iloc[-1], 'atr': atr,
            'volume': {'recent': df['volume'].iloc[-20:].mean(), 'trend': volume_trend},
            'momentum': df['close'].iloc[-1] / df['close'].iloc[-10] - 1 if len(df) >= 10 else 0,
            'bb': {'width': bb_width, 'upper': upper_band, 'lower': lower_band, 'sma': sma},
            'short_trend': short_trend, 'volume_price_trend': volume_price_trend,
            'stochastic': {'k': k.iloc[-1], 'd': d.iloc[-1]}
        }
    def is_touching(self, candle, value, is_top=True) -> bool:
        """ตรวจสอบว่าแท่งเทียนทับเส้นหรือไม่"""
        tolerance = value * 0.001
        return abs((candle['high'] if is_top else candle['low']) - value) < tolerance
    def get_latest_price(self, contract: str) -> Optional[float]:
        """ดึงราคาล่าสุดของสัญญา"""
        for t in self.futures_api.list_futures_tickers(settle='usdt'):
            if t.contract == contract: return float(t.last)
        self.console.print(f"[red]ไม่พบราคาสำหรับ {contract}[/red]")
        return None
    def calculate_position_score(self, indicators: Dict, df: pd.DataFrame, contract: str) -> Tuple[float, Dict]:
        """คำนวณคะแนนสำหรับการเปิด SHORT position ตามตัวชี้วัดต่างๆ"""
        if not indicators or len(df) < 3: return 0, {}
        latest_candle = df.iloc[-1]
        latest_price = self.get_latest_price(contract)
        if latest_price is None: return 0, {}
        score, reasons = 0, {}
        is_red = latest_candle['close'] < latest_candle['open']
        touches_top = self.is_touching(latest_candle, indicators['TOP'], is_top=True)
        touches_bottom = self.is_touching(latest_candle, indicators['BOTTOM'], is_top=False)
        is_downtrend = indicators['slope'] < 0
        if is_red and is_downtrend and (touches_top or touches_bottom):
            score += 30  # คะแนนพื้นฐาน
            touch_point = "TOP" if touches_top else "BOTTOM"
            reasons["basic"] = f"แท่งเทียนสีแดง + ทับเส้น {touch_point} + LRC ขาลง (slope={indicators['slope']:.6f})"
            score += 10 if touches_top else 5
            reasons[f"{touch_point.lower()}_touch"] = f"ทับเส้น {touch_point} ที่ {indicators['TOP' if touches_top else 'BOTTOM']:.6f}"
            if indicators['rsi'] > self.market_config['rsi_overbought']:
                score += 15
                reasons["rsi"] = f"RSI สูงเกินไป ({indicators['rsi']:.2f} > {self.market_config['rsi_overbought']})"
            elif indicators['rsi'] > 60:
                score += 5
                reasons["rsi"] = f"RSI ค่อนข้างสูง ({indicators['rsi']:.2f})"
            if latest_candle['volume'] > df['volume'].iloc[-2] * 1.2:
                score += 10
                reasons["volume"] = f"ปริมาณการซื้อขายเพิ่มขึ้น {(latest_candle['volume']/df['volume'].iloc[-2]-1)*100:.2f}%"
            near_resistance = any(df['high'].iloc[-i] > latest_price * 0.995 and df['high'].iloc[-i] < latest_price * 1.005 
                             for i in range(2, min(20, len(df))))
            if near_resistance:
                score += 10
                reasons["resistance"] = "ราคาอยู่ใกล้แนวต้านสำคัญ"
            if indicators['stochastic']['k'] > self.market_config['stochastic_overbought'] and \
               indicators['stochastic']['d'] > self.market_config['stochastic_overbought']:
                score += 10
                reasons["stochastic"] = f"Stochastic K/D สูงเกินไป (K={indicators['stochastic']['k']:.2f}, D={indicators['stochastic']['d']:.2f})"
            if latest_price > indicators['bb']['upper']:
                score += 10
                reasons["bollinger"] = f"ราคาสูงกว่า Upper Bollinger Band ({latest_price:.6f} > {indicators['bb']['upper']:.6f})"
            if indicators['short_trend'] < 0:
                score += 10
                reasons["short_trend"] = "แนวโน้มระยะสั้นเป็นขาลง"
            if indicators['volume_price_trend'] < 0:
                score += 5
                reasons["volume_price"] = "ความสัมพันธ์ระหว่างปริมาณและราคาไม่สอดคล้องกัน (bearish)"
            if len(df) > 3 and df['high'].iloc[-2] > indicators['TOP'] * 0.999 and df['close'].iloc[-2] < df['open'].iloc[-2]:
                score += 15
                reasons["top_rejection"] = "ราคาเพิ่งตีกลับจาก TOP ในแท่งก่อนหน้า"
        return score, reasons
    def get_market_trend(self) -> Dict:
        """วิเคราะห์แนวโน้มตลาดโดยรวมจาก Bitcoin"""
        btc_df = self.get_candlesticks("BTC_USDT", interval='1h', limit=24)
        if btc_df.empty: return {'trend': 'unknown', 'strength': 0}
        ema4 = btc_df['close'].ewm(span=4).mean().iloc[-1]
        ema8 = btc_df['close'].ewm(span=8).mean().iloc[-1]
        ema12 = btc_df['close'].ewm(span=12).mean().iloc[-1]
        ema24 = btc_df['close'].ewm(span=24).mean().iloc[-1]
        trend_score = sum([
            -1 if ema4 < ema8 else 1 if ema4 > ema8 else 0,
            -1 if ema8 < ema12 else 1 if ema8 > ema12 else 0,
            -1 if ema12 < ema24 else 1 if ema12 > ema24 else 0
        ])
        trend = 'bearish' if trend_score <= -2 else 'bullish' if trend_score >= 2 else 'sideways'
        strength = abs(trend_score) / 3
        return {'trend': trend, 'strength': strength}
    def check_position_correlation(self, new_contract: str) -> float:
        """ตรวจสอบสหสัมพันธ์ระหว่างสัญญาใหม่กับสัญญาที่มีอยู่แล้ว"""
        current_positions = self.get_current_positions()
        if not current_positions: return 0.0
        contracts = [pos['contract'] for pos in current_positions]
        if new_contract in contracts: return 1.0
        max_correlation = 0.0
        for contract in contracts:
            new_df = self.get_candlesticks(new_contract, interval='1h', limit=24)
            existing_df = self.get_candlesticks(contract, interval='1h', limit=24)
            if not new_df.empty and not existing_df.empty and len(new_df) == len(existing_df):
                correlation = new_df['close'].corr(existing_df['close'])
                max_correlation = max(max_correlation, abs(correlation))
        return max_correlation
    def get_current_positions(self) -> List[Dict]:
        """ดึงข้อมูล positions ที่เปิดอยู่ทั้งหมด"""
        try:
            return [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
        except Exception as e:
            self.console.print(f"[red]เกิดข้อผิดพลาดในการดึงข้อมูล positions: {str(e)}[/red]")
            return []
    def check_existing_position(self, contract: str) -> Optional[Dict]:
        """ตรวจสอบว่ามี position ที่เปิดอยู่หรือไม่"""
        for p in self.get_current_positions():
            if p['contract'] == contract:
                size = float(p['size'])
                position_type = "LONG" if size > 0 else "SHORT" if size < 0 else "NONE"
                self.console.print(f"[yellow]พบ position {position_type} สำหรับ {contract}: ขนาด={abs(size)}[/yellow]")
                return p
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
            entry_price = float(position['entry_price'])
            exit_price = self.get_latest_price(contract)
            pnl_percentage = ((entry_price - exit_price) / entry_price) * 100 if size < 0 else ((exit_price - entry_price) / entry_price) * 100
            if contract not in self.trade_history: self.trade_history[contract] = []
            self.trade_history[contract].append({
                'action': 'close', 'position_type': 'LONG' if size > 0 else 'SHORT',
                'size': abs(size), 'entry_price': entry_price, 'exit_price': exit_price,
                'pnl_percentage': pnl_percentage,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            self.console.print(f"[green]✅ ปิด position {'LONG' if size > 0 else 'SHORT'} สำหรับ {contract}: ขนาด={abs(size)}, P&L={pnl_percentage:.2f}%[/green]")
            return True
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถปิด position สำหรับ {contract}: {str(e)}[/red]")
            return False
    def create_order(self, contract: str, is_long: bool, score: float, reasons: Dict) -> Optional[Dict]:
        """เปิด position LONG หรือ SHORT ตามคะแนนที่ได้"""
        try:
            current_positions = self.get_current_positions()
            if len(current_positions) >= self.max_positions:
                self.console.print(f"[yellow]⚠️ ไม่สามารถเปิด position ใหม่ได้: เกินจำนวนสูงสุด ({self.max_positions} positions)[/yellow]")
                return None
            correlation = self.check_position_correlation(contract)
            if correlation > self.max_correlation:
                self.console.print(f"[yellow]⚠️ ไม่สามารถเปิด position ใหม่ได้: สหสัมพันธ์กับ positions ที่มีอยู่สูงเกินไป ({correlation:.2f} > {self.max_correlation})[/yellow]")
                return None
            if not self.set_leverage(contract): return None
            price = self.get_latest_price(contract)
            if not price: return None
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            position_size_factor = min(1.0, score / 100)
            usd_value = self.order_amount * self.leverage * position_size_factor
            size = max(min_size, round(usd_value / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract, 'size': size if is_long else -size,
                'price': 0, 'tif': 'ioc', 'reduce_only': False
            })
            if contract not in self.trade_history: self.trade_history[contract] = []
            self.trade_history[contract].append({
                'action': 'open', 'position_type': 'LONG' if is_long else 'SHORT',
                'size': size, 'price': price, 'score': score, 'reasons': reasons,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            position_type = "LONG" if is_long else "SHORT"
            self.console.print(f"[{'green' if is_long else 'red'}]✅ เปิด position {position_type}: {contract} ขนาด={size}, คะแนน={score:.2f}[/{'green' if is_long else 'red'}]")
            return order
        except Exception as e:
            self.console.print(f"[red]ไม่สามารถเปิด {'LONG' if is_long else 'SHORT'} สำหรับ {contract}: {str(e)}[/red]")
            return None
    def scan_positions(self) -> int:
        """สแกน positions ที่เปิดอยู่เพื่อทำการปิดตามเงื่อนไข"""
        try:
            positions = self.get_current_positions()
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
                pnl_percentage = ((latest_price - entry_price) / entry_price) * 100 if size > 0 else ((entry_price - latest_price) / entry_price) * 100
                self.console.print(f"[{'green' if pnl_percentage > 0 else 'red'}]   P&L: {pnl_percentage:.2f}%[/{'green' if pnl_percentage > 0 else 'red'}]")
                close_position_reason = None
                if size < 0:  # เฉพาะ SHORT position
                    if (pnl_percentage > 0 and pnl_percentage > self.profit_threshold) or \
                       (pnl_percentage < 0 and abs(pnl_percentage) > self.loss_threshold):
                        close_position_reason = f"{'กำไร' if pnl_percentage > 0 else 'ขาดทุน'} {abs(pnl_percentage):.2f}% > {self.profit_threshold if pnl_percentage > 0 else self.loss_threshold}%"
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
    def analyze_trading_stats(self) -> Dict:
        """วิเคราะห์ประสิทธิภาพและสถิติการเทรด"""
        stats = {'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0, 'total_profit': 0.0, 'total_loss': 0.0, 'win_rate': 0.0}
        close_trades = []
        for contract in self.trade_history:
            for trade in self.trade_history[contract]:
                if trade['action'] == 'close':
                    close_trades.append(trade)
                    stats['total_trades'] += 1
                    if trade['pnl_percentage'] > 0:
                        stats['winning_trades'] += 1
                        stats['total_profit'] += trade['pnl_percentage']
                    else:
                        stats['losing_trades'] += 1
                        stats['total_loss'] += abs(trade['pnl_percentage'])
        if stats['total_trades'] > 0:
            stats['win_rate'] = stats['winning_trades'] / stats['total_trades'] * 100
            stats['avg_profit'] = stats['total_profit'] / stats['winning_trades'] if stats['winning_trades'] > 0 else 0
            stats['avg_loss'] = stats['total_loss'] / stats['losing_trades'] if stats['losing_trades'] > 0 else 0
            stats['profit_factor'] = stats['total_profit'] / stats['total_loss'] if stats['total_loss'] > 0 else float('inf')
        return stats
    def scan_market(self):
        """สแกนตลาดเพื่อหาสัญญาณการเทรดและจัดการ positions"""
        first_run = True
        stats = {'contracts_scanned': 0, 'signals': 0, 'short_opened': 0, 'positions_closed': 0}
        while True:
            try:
                current_time = pd.Timestamp.now()
                if current_time.minute % 5 == 0 or first_run:
                    self.console.print(f"[blue]🔍 เริ่มสแกนตลาด ณ เวลา {current_time.strftime('%Y-%m-%d %H:%M:%S')}[/blue]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    first_run = False
                    scan_stats = {'contracts_scanned': 0, 'signals': 0, 'short_opened': 0, 'positions_closed': 0}
                    # ตรวจสอบแนวโน้มตลาดโดยรวม
                    market_trend = self.get_market_trend()
                    market_ok_for_short = market_trend['trend'] in ['bearish', 'sideways']
                    self.console.print(f"[{'red' if market_trend['trend'] == 'bearish' else 'yellow' if market_trend['trend'] == 'sideways' else 'green'}]🌐 แนวโน้มตลาดโดยรวม: {market_trend['trend']} (ความแรง: {market_trend['strength']:.2f})[/{'red' if market_trend['trend'] == 'bearish' else 'yellow' if market_trend['trend'] == 'sideways' else 'green'}]")
                    # ตรวจสอบ Positions ที่มีอยู่
                    self.console.print(f"[blue]📊 ตรวจสอบ Positions ที่มีอยู่[/blue]")
                    scan_stats['positions_closed'] = self.scan_positions()
                    # ตรวจหาสัญญาณเทรดใหม่
                    self.console.print(f"[blue]📊 ตรวจหาสัญญาณเทรดใหม่{' (ข้ามเนื่องจากตลาดขาขึ้น)' if not market_ok_for_short else ''}[/blue]")
                    if market_ok_for_short:  # เฉพาะเมื่อตลาดเป็นขาลงหรือทรงตัว
                        contracts = self.get_futures_contracts()
                        for i, contract in enumerate(contracts, 1):
                            self.console.print(f"[cyan]▶ สแกนสัญญา ({i}/{len(contracts)}): {contract}[/cyan]")
                            df = self.get_candlesticks(contract)
                            if df.empty:
                                self.console.print(f"[red]❌ ไม่สามารถดึงข้อมูลแท่งเทียนของ {contract} ได้[/red]")
                                continue
                            indicators = self.calculate_indicators(df)
                            if not indicators:
                                self.console.print(f"[red]❌ ไม่สามารถคำนวณตัวชี้วัดสำหรับ {contract} ได้[/red]")
                                continue
                            latest_price = self.get_latest_price(contract)
                            slope_direction = "ขาขึ้น 📈" if indicators['slope'] > 0 else "ขาลง 📉" if indicators['slope'] < 0 else "แนวราบ ➡️"
                            self.console.print(f"[magenta]   Linear Regression Channel: TOP={indicators['TOP']:.6f}, MIDDLE={indicators['MIDDLE']:.6f}, BOTTOM={indicators['BOTTOM']:.6f}[/magenta]")
                            self.console.print(f"[magenta]   Slope={indicators['slope']:.6f} ({slope_direction}), RSI={indicators['rsi']:.2f}, ราคาล่าสุด={latest_price:.6f}[/magenta]")
                            # คำนวณคะแนนการเปิด position
                            score, reasons = self.calculate_position_score(indicators, df, contract)
                            if score > 0:
                                scan_stats['signals'] += 1
                                self.console.print(f"[yellow]🔔 พบสัญญาณเทรด (คะแนน={score:.2f}/100) สำหรับ {contract}[/yellow]")
                                for reason, detail in reasons.items():
                                    self.console.print(f"[yellow]   - {detail}[/yellow]")
                                # ตรวจสอบว่ามี position เดิมหรือไม่
                                existing_position = self.check_existing_position(contract)
                                if not existing_position and score >= 50:  # คะแนนต้องมากกว่า 50 จึงจะเปิด position
                                    self.console.print(f"[yellow]🆕 เปิด SHORT position ตามสัญญาณที่พบ (คะแนน={score:.2f}/100)[/yellow]")
                                    if self.create_order(contract, False, score, reasons):  # false คือ SHORT
                                        scan_stats['short_opened'] += 1
                                else:
                                    if existing_position:
                                        self.console.print(f"[yellow]⚠️ มี position อยู่แล้ว ไม่สามารถเปิด SHORT ใหม่ได้[/yellow]")
                                    elif score < 50:
                                        self.console.print(f"[yellow]⚠️ คะแนนไม่ถึงเกณฑ์ ({score:.2f} < 50) ไม่เปิด SHORT[/yellow]")
                            else:
                                self.console.print(f"[blue]   ไม่พบสัญญาณเทรด[/blue]")
                            scan_stats['contracts_scanned'] += 1
                    # อัปเดตสถิติรวม
                    for key in stats: stats[key] += scan_stats[key]
                    # แสดงสรุปการสแกน
                    self.console.print(f"[blue]===== สรุปการสแกนรอบนี้ =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกน: {scan_stats['contracts_scanned']}[/blue]")
                    self.console.print(f"[yellow]🔔 สัญญาณที่พบ: {scan_stats['signals']}[/yellow]")
                    self.console.print(f"[red]📉 เปิด SHORT: {scan_stats['short_opened']}[/red]")
                    self.console.print(f"[green]🔄 ปิด Position: {scan_stats['positions_closed']}[/green]")
                    # แสดงสถิติรวมทั้งหมด
                    self.console.print(f"[blue]===== สถิติรวมทั้งหมด =====[/blue]")
                    self.console.print(f"[blue]📊 สัญญาที่สแกนทั้งหมด: {stats['contracts_scanned']}[/blue]")
                    self.console.print(f"[yellow]🔔 สัญญาณที่พบทั้งหมด: {stats['signals']}[/yellow]")
                    self.console.print(f"[red]📉 เปิด SHORT ทั้งหมด: {stats['short_opened']}[/red]")
                    self.console.print(f"[green]🔄 ปิด Position ทั้งหมด: {stats['positions_closed']}[/green]")
                    # แสดงสถิติการเทรด
                    trading_stats = self.analyze_trading_stats()
                    if trading_stats['total_trades'] > 0:
                        self.console.print(f"[blue]===== สถิติการเทรด =====[/blue]")
                        self.console.print(f"[blue]🔢 จำนวนเทรดทั้งหมด: {trading_stats['total_trades']}[/blue]")
                        self.console.print(f"[green]✅ เทรดที่กำไร: {trading_stats['winning_trades']} ({trading_stats['win_rate']:.2f}%)[/green]")
                        self.console.print(f"[red]❌ เทรดที่ขาดทุน: {trading_stats['losing_trades']}[/red]")
                        self.console.print(f"[green]💰 กำไรเฉลี่ยต่อเทรด: {trading_stats['avg_profit']:.2f}%[/green]")
                        self.console.print(f"[red]💸 ขาดทุนเฉลี่ยต่อเทรด: {trading_stats['avg_loss']:.2f}%[/red]")
                        self.console.print(f"[{'green' if trading_stats['profit_factor'] > 1 else 'red'}]📊 Profit Factor: {trading_stats['profit_factor']:.2f}[/{'green' if trading_stats['profit_factor'] > 1 else 'red'}]")
                    self.console.print(f"[blue]===========================================[/blue]")
                    time.sleep(30)
                time.sleep(10)
            except Exception as e:
                self.console.print(f"[red]❌ เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}[/red]")
                time.sleep(60)
def main():
    trader = OptimizedShortTrader()
    trader.console.print("[blue]เริ่มต้นระบบเทรด SHORT อัตโนมัติที่ปรับปรุงแล้ว...[/blue]")
    trader.scan_market()
if __name__ == "__main__":
    main()