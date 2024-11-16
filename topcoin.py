from gate_api import ApiClient, Configuration, SpotApi, Order
import asyncio
import aiohttp
from datetime import datetime
import time
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List

API_KEY = "c84d3616806f44e5651912c198094a1b"
API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"

@dataclass
class BOSEvent:
    timestamp: float
    price: float
    type: str  # 'bullish' or 'bearish'
    strength: float

class GateioScanner:
    def __init__(self):
        self.base_url = "https://api.gateio.ws/api/v4"
        self.headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        self.config = Configuration(
            key=API_KEY,
            secret=API_SECRET,
            host="https://api.gateio.ws/api/v4"
        )
        self.client = ApiClient(self.config)
        self.spot_api = SpotApi(self.client)

    async def get_spot_pairs(self):
        """ดึงรายชื่อคู่เทรด USDT ที่มี volume 24h > $100,000"""
        async with aiohttp.ClientSession() as session:
            # 1. ดึงรายชื่อคู่เทรดทั้งหมด
            async with session.get(f"{self.base_url}/spot/currency_pairs", headers=self.headers) as response:
                pairs = await response.json()
                # กรองเฉพาะคู่ USDT
                pairs = [pair for pair in pairs if pair['id'].count('_USDT') == 1]

            # 2. ดึงข้อมูล volume จาก tickers
            async with session.get(f"{self.base_url}/spot/tickers", headers=self.headers) as response:
                tickers = await response.json()
                volume_dict = {
                    t['currency_pair']: float(t['quote_volume']) 
                    for t in tickers 
                    if t['currency_pair'].count('_USDT') == 1
                }

            # 3. กรองและเรียงตาม volume
            filtered_pairs = []
            for pair in pairs:
                pair_id = pair['id']
                if pair_id in volume_dict:
                    volume = volume_dict[pair_id]
                    if volume >= 100_000:
                        pair['volume_24h'] = volume
                        filtered_pairs.append(pair)

            filtered_pairs.sort(key=lambda x: x['volume_24h'], reverse=True)

            if filtered_pairs:
                print(f"\nพบ {len(filtered_pairs)} คู่เทรดที่มี volume 24h > $100,000")
                print("Top 5 Volume:")
                for i, pair in enumerate(filtered_pairs[:5], 1):
                    volume_formatted = f"${pair['volume_24h']:,.0f}"
                    print(f"{i}. {pair['id']}: {volume_formatted}")
            else:
                print("\nไม่พบคู่เทรดที่มี volume 24h > $100,000")

            return filtered_pairs

    async def get_klines(self, session, pair, interval='1h', limit=100):
        try:
            params = {'currency_pair': pair, 'interval': interval, 'limit': limit}
            async with session.get(f"{self.base_url}/spot/candlesticks", params=params) as response:
                data = await response.json()
                if isinstance(data, list) and len(data) > 0 and len(data[0]) >= 6:
                    return data
                return None
        except Exception as e:
            print(f"Error getting klines for {pair}: {e}")
            return None

    def safe_float_convert(self, value):
        try:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                clean_value = ''.join(c for c in value if c.isdigit() or c in '.-')
                return float(clean_value) if clean_value else 0.0
            return 0.0
        except:
            return 0.0

    def get_spot_price(self, pair: str) -> float:
        """ดึงราคาล่าสุดของคู่เทรด"""
        try:
            ticker = self.spot_api.list_tickers(currency_pair=pair)
            if ticker and isinstance(ticker, list) and len(ticker) > 0:
                if hasattr(ticker[0], 'last'):  # กรณีเป็น object
                    return float(ticker[0].last)
                elif isinstance(ticker[0], dict):  # กรณีเป็น dict
                    return float(ticker[0]['last'])
            return 0.0
        except Exception as e:
            print(f"Error getting price for {pair}: {e}")
            return 0.0

    def get_account_balance(self, symbol: str) -> float:
        """ดึงข้อมูล balance สำหรับเหรียญที่ต้องการ"""
        try:
            balances = self.spot_api.list_spot_accounts()
            for balance in balances:
                if balance.currency.lower() == symbol.lower():
                    return float(balance.available)  # ส่งคืนเฉพาะจำนวนเหรียญ
            return 0.0
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึง balance: {str(e)}")
            return 0.0

    def place_market_buy(self, pair: str, amount_usdt: float = 20) -> bool:
        """ส่งคำสั่งซื้อแบบ Market"""
        try:
            symbol = pair.split('_')[0]
            
            order = Order(
                currency_pair=pair,
                side='buy',
                amount=str(amount_usdt),
                type='market',
                time_in_force='ioc'
            )
            
            result = self.spot_api.create_order(order)
            print(f"\nส่งคำสั่งซื้อสำเร็จ:")
            print(f"คู่เทรด: {pair}")
            print(f"มูลค่า: ${amount_usdt}")
            print(f"Order ID: {result.id}")
            
            return True

        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการส่งคำสั่งซื้อ: {str(e)}")
            return False

    def place_market_sell(self, pair: str) -> bool:
        """ส่งคำสั่งขายทั้งหมดแบบ Market"""
        try:
            symbol = pair.split('_')[0]
            
            # ตรวจสอบจำนวนเหรียญที่มี
            available_amount = self.get_account_balance(symbol)
            
            if available_amount <= 0:
                print(f"ไม่มีเหรียญ {symbol} ในพอร์ต")
                return False
            
            order = Order(
                currency_pair=pair,
                side='sell',
                amount=str(available_amount),
                type='market',
                time_in_force='ioc'
            )
            
            result = self.spot_api.create_order(order)
            print(f"\nส่งคำสั่งขายสำเร็จ:")
            print(f"คู่เทรด: {pair}")
            print(f"จำนวน: {available_amount} {symbol}")
            print(f"Order ID: {result.id}")
            
            return True

        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการส่งคำสั่งขาย: {str(e)}")
            return False
        
    def check_bos(self, df: pd.DataFrame) -> dict:
        try:
            if len(df) < 20:
                return None

            lookback = 20
            structure_high = df['high'].iloc[-lookback:-1].max()
            structure_low = df['low'].iloc[-lookback:-1].min()
            
            last_candle = df.iloc[-1]
            previous_candle = df.iloc[-2]

            recent_volume = df['volume'].tail(3).mean()
            avg_volume = df['volume'].mean()
            volume_increase = (recent_volume / avg_volume - 1) * 100

            # คำนวณ RSI
            closes = df['close'].values
            deltas = np.diff(closes)
            gain = (deltas >= 0).astype(float) * deltas
            loss = (deltas < 0).astype(float) * abs(deltas)
            avg_gain = np.mean(gain[-14:])
            avg_loss = np.mean(loss[-14:])
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            signal = None
            score = 0
            reasons = []
            bos = None

            # ตรวจสอบ Bullish BOS
            if last_candle['high'] > structure_high:
                bos_strength = (last_candle['high'] - structure_high) / structure_high * 100
                bos = BOSEvent(
                    timestamp=last_candle.name,
                    price=last_candle['high'],
                    type='bullish',
                    strength=bos_strength
                )
                
                # ตรวจสอบเงื่อนไขต่างๆ
                if bos_strength >= 1.0:
                    score += 20
                    reasons.append(f"✅ BOS แรง ({bos_strength:.1f}%)")
                else:
                    reasons.append(f"❌ BOS ไม่แรงพอ ({bos_strength:.1f}%)")

                if volume_increase >= 20:
                    score += 20
                    reasons.append(f"✅ Volume เพิ่มขึ้น {volume_increase:.1f}%")
                else:
                    reasons.append(f"❌ Volume น้อย {volume_increase:.1f}%")

                if 40 <= rsi <= 70:
                    score += 20
                    reasons.append(f"✅ RSI ดี ({rsi:.1f})")
                else:
                    reasons.append(f"❌ RSI ไม่เหมาะสม ({rsi:.1f})")

                current_pullback = (bos.price - last_candle['close']) / bos.price * 100
                if 0 <= current_pullback <= 2:
                    score += 20
                    reasons.append("✅ Pullback เหมาะสม")
                else:
                    reasons.append(f"❌ Pullback มาก ({current_pullback:.1f}%)")

                if last_candle['close'] > last_candle['open']:
                    score += 20
                    reasons.append("✅ แท่งปัจจุบันเป็นบวก")
                else:
                    reasons.append("❌ แท่งปัจจุบันเป็นลบ")

                signal = "BUY 🚀" if score >= 70 else "HOLD 🤔"

            # ตรวจสอบ Bearish BOS
            elif last_candle['low'] < structure_low:
                bos_strength = (structure_low - last_candle['low']) / structure_low * 100
                bos = BOSEvent(
                    timestamp=last_candle.name,
                    price=last_candle['low'],
                    type='bearish',
                    strength=bos_strength
                )

                if bos_strength >= 1.0:
                    score += 20
                    reasons.append(f"✅ BOS แรง ({bos_strength:.1f}%)")
                else:
                    reasons.append(f"❌ BOS ไม่แรงพอ ({bos_strength:.1f}%)")

                if volume_increase >= 20:
                    score += 20
                    reasons.append(f"✅ Volume เพิ่มขึ้น {volume_increase:.1f}%")
                else:
                    reasons.append(f"❌ Volume น้อย {volume_increase:.1f}%)")

                if rsi >= 70:
                    score += 20
                    reasons.append(f"✅ RSI สูง ({rsi:.1f})")
                else:
                    reasons.append(f"❌ RSI ไม่เหมาะสม ({rsi:.1f})")

                current_pullback = (last_candle['close'] - bos.price) / bos.price * 100
                if 0 <= current_pullback <= 2:
                    score += 20
                    reasons.append("✅ Pullback เหมาะสม")
                else:
                    reasons.append(f"❌ Pullback มาก ({current_pullback:.1f}%)")

                if last_candle['close'] < last_candle['open']:
                    score += 20
                    reasons.append("✅ แท่งปัจจุบันเป็นลบ")
                else:
                    reasons.append("❌ แท่งปัจจุบันเป็นบวก")

                signal = "SELL 📉" if score >= 70 else "HOLD 🤔"

            if bos:
                return {
                    'bos': bos,
                    'score': score,
                    'signal': signal,
                    'current_price': last_candle['close'],
                    'volume': recent_volume,
                    'reasons': reasons
                }

            return None

        except Exception as e:
            print(f"Error checking BOS: {e}")
            return None

    async def process_pair(self, session, pair_info):
        try:
            pair = pair_info['id']
            if any(c.isdigit() for c in pair.split('_')[0]):
                return None

            klines = await self.get_klines(session, pair)
            if not klines:
                return None

            df = pd.DataFrame([{
                'timestamp': self.safe_float_convert(k[0]),
                'volume': self.safe_float_convert(k[1]),
                'close': self.safe_float_convert(k[2]),
                'high': self.safe_float_convert(k[3]),
                'low': self.safe_float_convert(k[4]),
                'open': self.safe_float_convert(k[5])
            } for k in klines if len(k) >= 6])

            if df.empty or df.isnull().values.any():
                return None

            df = df.set_index('timestamp').sort_index()
            
            result = self.check_bos(df)
            if result:
                symbol = pair.split('_')[0]
                try:
                    # ดึงยอด balance และราคา
                    usdt_balance = self.get_account_balance('USDT')
                    symbol_balance = self.get_account_balance(symbol)  # จำนวนเหรียญ
                    current_price = self.get_spot_price(pair)  # ราคาปัจจุบัน
                    
                    # แปลงจำนวนเหรียญเป็นมูลค่า USDT
                    symbol_balance_usdt = symbol_balance * current_price

                    if result['signal'] == "BUY 🚀":
                        if symbol_balance_usdt < 5:  # ถ้ามูลค่าน้อยกว่า $5
                            if usdt_balance >= 20:  # มี USDT พอที่จะซื้อ
                                if self.place_market_buy(pair, 20):  # ซื้อ $20
                                    result['auto_trade'] = "ส่งคำสั่งซื้ออัตโนมัติแล้ว ($20)"
                                else:
                                    result['auto_trade'] = "ไม่สามารถส่งคำสั่งซื้อได้"
                            else:
                                result['auto_trade'] = f"มี USDT ไม่พอซื้อ (USDT: ${usdt_balance:.2f})"
                        else:
                            result['auto_trade'] = f"ไม่ซื้อเพิ่ม (มูลค่าในพอร์ต: ${symbol_balance_usdt:.2f})"

                    elif result['signal'] == "SELL 📉":
                        if symbol_balance_usdt > 0:
                            if self.place_market_sell(pair):  # ขายทั้งหมด
                                result['auto_trade'] = f"ส่งคำสั่งขายอัตโนมัติแล้ว (${symbol_balance_usdt:.2f})"
                            else:
                                result['auto_trade'] = "ไม่สามารถส่งคำสั่งขายได้"
                        else:
                            result['auto_trade'] = "ไม่มีเหรียญในพอร์ต"

                except Exception as e:
                    print(f"Error processing {pair}: {str(e)}")
                    result['auto_trade'] = f"เกิดข้อผิดพลาด: {str(e)}"

                return {'pair': pair, **result}

        except Exception as e:
            print(f"Error processing {pair}: {e}")
            return None

    async def scan_market(self):
        pairs = await self.get_spot_pairs()
        print(f"\nพบ {len(pairs)} คู่เทรด")
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = [self.process_pair(session, pair) for pair in pairs]
            results = await asyncio.gather(*tasks)
            
            signals = [r for r in results if r is not None]
            signals.sort(key=lambda x: x['score'], reverse=True)
            return signals

def format_number(num):
    if num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.2f}K"
    return f"{num:.2f}"

async def main():
    while True:
        try:
            scanner = GateioScanner()
            print("\n=== สแกนหา Break of Structure ===")
            
            start_time = time.time()
            signals = await scanner.scan_market()
            scan_time = time.time() - start_time
            
            if signals:
                print(f"\nพบ {len(signals)} สัญญาณ (เวลาที่ใช้: {scan_time:.1f} วินาที)")
                print("\n{:<4} {:<12} {:<8} {:<8} {:<15} {:<10}".format(
                    "No.", "เหรียญ", "Signal", "Score", "ราคา", "Volume"
                ))
                print("-" * 70)
                
                for i, s in enumerate(signals, 1):
                    print("{:<4} {:<12} {:<8} {:<8} {:<15} {:<10}".format(
                        f"{i}.", s['pair'],
                        s['signal'],
                        f"{s['score']}%",
                        f"{s['current_price']:.8f}",
                        format_number(s['volume'])
                    ))
                    print("\nเหตุผล:")
                    for reason in s['reasons']:
                        print(f"  {reason}")
                    
                    if 'auto_trade' in s:
                        print(f"\nการเทรดอัตโนมัติ: {s['auto_trade']}")
                    print()
            else:
                print("\nไม่พบสัญญาณ BOS")
                
            print("\nรอ 5 นาที...")
            await asyncio.sleep(60 * 5)
            
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())        