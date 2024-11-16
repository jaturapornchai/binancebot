from gate_api import ApiClient, Configuration, SpotApi, Order
from gate_api.exceptions import ApiException, GateApiException
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import random

# ข้อมูลรับรอง API
API_KEY = "c84d3616806f44e5651912c198094a1b"
API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"

class MarketStructureScanner:
    def __init__(self, api_key, api_secret):
        self.config = Configuration(
            key=api_key,
            secret=api_secret,
            host="https://api.gateio.ws/api/v4"
        )
        self.client = ApiClient(self.config)
        self.spot_api = SpotApi(self.client)
        self.zigzag_len = 9
        self.fib_factor = 0.33
        self.min_volume = 100000
        self.signaled_pairs = set()

    def get_account_balance(self, currency):
        """ดึงยอดเงินที่มีอยู่สำหรับสกุลเงินที่กำหนด"""
        try:
            balances = self.spot_api.list_spot_accounts(currency=currency)
            if balances:
                return float(balances[0].available)
            return 0
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงยอดเงินสำหรับ {currency}: {str(e)}", flush=True)
            return 0

    def place_order(self, symbol, side, amount, price=None):
        """ส่งคำสั่งซื้อขาย"""
        try:
            order = Order(
                currency_pair=symbol,
                side=side,
                amount=str(amount),
                price=str(price) if price else None,
                type='market' if not price else 'limit'
            )
            result = self.spot_api.create_order(order)
            
            print(f"\nส่งคำสั่งซื้อขายสำเร็จ:", flush=True)
            print(f"สัญลักษณ์: {symbol}", flush=True)
            print(f"ประเภท: {side.upper()}", flush=True)
            print(f"จำนวน: {amount}", flush=True)
            print(f"ชนิด: {'ตลาด' if not price else 'จำกัด'}", flush=True)
            if price:
                print(f"ราคา: ${price}", flush=True)
            print(f"รหัสคำสั่ง: {result.id}", flush=True)
            
            return result
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการส่งคำสั่ง: {str(e)}", flush=True)
            return None
            
    def get_valid_pairs(self):
        """ดึงคู่เงินที่มีปริมาณเพียงพอ"""
        try:
            pairs = self.spot_api.list_currency_pairs()
            tickers = self.spot_api.list_tickers()
            
            volume_dict = {}
            for ticker in tickers:
                if ticker.currency_pair.endswith('USDT'):
                    volume_usd = float(ticker.quote_volume)
                    volume_dict[ticker.currency_pair] = volume_usd
            
            valid_pairs = []
            for pair in pairs:
                if (pair.id.endswith('USDT') and 
                    not any(char.isdigit() for char in pair.id[:-4]) and
                    pair.id in volume_dict and 
                    volume_dict[pair.id] >= self.min_volume):
                    valid_pairs.append({
                        'symbol': pair.id,
                        'volume': volume_dict[pair.id]
                    })
            
            random.shuffle(valid_pairs)
            return valid_pairs
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงคู่เงินที่ถูกต้อง: {str(e)}", flush=True)
            return []

    def get_ticker_data(self, symbol):
        """ดึงข้อมูลราคา ticker สำหรับสัญลักษณ์ที่กำหนด"""
        try:
            tickers = self.spot_api.list_tickers(currency_pair=symbol)
            if tickers and len(tickers) > 0:
                ticker = tickers[0]
                return {
                    'symbol': symbol,
                    'last': float(ticker.last),
                    'change_percentage': float(ticker.change_percentage),
                    'high_24h': float(ticker.high_24h),
                    'low_24h': float(ticker.low_24h),
                    'volume': float(ticker.quote_volume)
                }
            return None
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงข้อมูล ticker สำหรับ {symbol}: {str(e)}", flush=True)
            return None

    def get_candlesticks(self, symbol, interval='1h', limit=100):
        """ดึงข้อมูลแท่งเทียนสำหรับการวิเคราะห์"""
        try:
            candles = self.spot_api.list_candlesticks(
                currency_pair=symbol,
                interval=interval,
                limit=limit
            )
            
            formatted_candles = []
            for candle in candles:
                formatted_candles.append({
                    'timestamp': float(candle[0]),
                    'volume': float(candle[1]),
                    'close': float(candle[2]),
                    'high': float(candle[3]),
                    'low': float(candle[4]),
                    'open': float(candle[5])
                })
            return formatted_candles
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงข้อมูลแท่งเทียนสำหรับ {symbol}: {str(e)}", flush=True)
            return None

    def analyze_market_structure(self, df):
        """วิเคราะห์โครงสร้างตลาดและหาจุดเปลี่ยน"""
        try:
            df['highest'] = df['high'].rolling(window=self.zigzag_len).max()
            df['lowest'] = df['low'].rolling(window=self.zigzag_len).min()
            
            df['to_up'] = df['high'] >= df['highest'].shift(1)
            df['to_down'] = df['low'] <= df['lowest'].shift(1)
            
            high_points = []
            low_points = []
            current_trend = 1
            
            for i in range(1, len(df)):
                if df.iloc[i]['to_down'] and current_trend == 1:
                    high_points.append({
                        'price': df.iloc[i-1]['high'],
                        'index': i-1
                    })
                    current_trend = -1
                elif df.iloc[i]['to_up'] and current_trend == -1:
                    low_points.append({
                        'price': df.iloc[i-1]['low'],
                        'index': i-1
                    })
                    current_trend = 1
                    
            if len(high_points) >= 2 and len(low_points) >= 2:
                h0, h1 = high_points[-1], high_points[-2]
                l0, l1 = low_points[-1], low_points[-2]
                
                if h0['price'] > h1['price'] and \
                   df.iloc[-1]['high'] > h0['price'] + abs(h0['price'] - l0['price']) * self.fib_factor:
                    return 'bullish', l0['index']
                
                elif l0['price'] < l1['price'] and \
                     df.iloc[-1]['low'] < l0['price'] - abs(h0['price'] - l0['price']) * self.fib_factor:
                    return 'bearish', h0['index']
                    
            return None, None
            
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการวิเคราะห์โครงสร้างตลาด: {str(e)}", flush=True)
            return None, None

    def find_order_blocks(self, df, msb_type, pivot_index):
        """
        ค้นหา order blocks ตามประเภทการแตกของโครงสร้างตลาด
        คืนค่าข้อมูล order block หรือ None ถ้าไม่พบ
        """
        try:
            # ต้องการอย่างน้อย 3 แท่งก่อน pivot สำหรับการวิเคราะห์ order block
            if pivot_index < 3:
                return None
                
            # ดึงข้อมูลช่วงที่เกี่ยวข้องก่อน pivot
            pre_pivot = df.iloc[pivot_index-3:pivot_index]
            
            if msb_type == 'bullish':
                # สำหรับการแตกขาขึ้น ให้หาจุดต่ำสุดในแท่งก่อน pivot
                ob_low = pre_pivot['low'].min()
                # หาจุดสูงสุดในช่วงเดียวกัน
                ob_high = pre_pivot['high'].max()
                
                return {
                    'type': 'Bullish',
                    'high': ob_high,
                    'low': ob_low
                }
                
            else:  # bearish
                # สำหรับการแตกขาลง ให้หาจุดสูงสุดในแท่งก่อน pivot
                ob_high = pre_pivot['high'].max()
                # หาจุดต่ำสุดในช่วงเดียวกัน
                ob_low = pre_pivot['low'].min()
                
                return {
                    'type': 'Bearish',
                    'high': ob_high,
                    'low': ob_low
                }
                
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการค้นหา order blocks: {str(e)}", flush=True)
            return None
            
    def handle_bullish_signal(self, symbol, current_price):
        """จัดการสัญญาณขาขึ้น"""
        try:
            base_currency = symbol.replace('_USDT', '')
            balance = self.get_account_balance(base_currency)
            balance_usd = balance * current_price
            
            print(f"\nตรวจสอบยอดเงิน {base_currency}...", flush=True)
            print(f"ยอดเงินปัจจุบัน: {balance:.8f} {base_currency}", flush=True)
            print(f"มูลค่าเป็น USD: ${balance_usd:.2f}", flush=True)
            
            if balance_usd < 5:
                print(f"ยอดเงินน้อยกว่า $5 ข้ามรอบนี้และรอโอกาสถัดไป", flush=True)
                return  # หยุดและรอรอบต่อไป
            else:
                print(f"ยอดเงินเพียงพอ (${balance_usd:.2f}) ไม่ต้องดำเนินการเพิ่มเติม", flush=True)
                
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการจัดการสัญญาณขาขึ้น: {str(e)}", flush=True)

    def handle_bearish_signal(self, symbol, current_price):
        """จัดการสัญญาณขาลง"""
        try:
            base_currency = symbol.replace('_USDT', '')
            balance = self.get_account_balance(base_currency)
            
            if balance > 0:
                print(f"\nพบ {balance:.8f} {base_currency} เพื่อขาย", flush=True)
                print(f"มูลค่าเป็น USD: ${balance * current_price:.2f}", flush=True)
                
                # ปรับแต่งจำนวนทศนิยมให้ถูกต้องตามเหรียญ
                try:
                    pair_info = self.spot_api.get_currency_pair(symbol)
                    amount_precision = pair_info.amount_precision
                    balance = round(balance, amount_precision)
                    
                    print(f"จำนวนที่ปรับแล้วสำหรับการขาย: {balance} {base_currency}", flush=True)
                except:
                    balance = round(balance, 6)
                
                # ส่งคำสั่งขาย
                order = self.place_order(symbol, 'sell', balance)
                if order:
                    print(f"ส่งคำสั่งขายสำเร็จ", flush=True)
            else:
                print(f"\nไม่พบยอดเงิน {base_currency} เพื่อขาย", flush=True)
                
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการจัดการสัญญาณขาลง: {str(e)}", flush=True)

    def analyze_pair(self, pair_info):
        """วิเคราะห์คู่การซื้อขาย"""
        symbol = pair_info['symbol']
        volume = pair_info['volume']
        
        print(f"กำลังวิเคราะห์ {symbol} (ปริมาณ: ${volume:,.2f})", flush=True)
        
        if symbol in self.signaled_pairs:
            print(f"ข้าม {symbol} - มีสัญญาณแล้ว", flush=True)
            return
            
        try:
            candles = self.get_candlesticks(symbol)
            if not candles:
                return
                
            df = pd.DataFrame(candles)
            
            msb_type, pivot_index = self.analyze_market_structure(df)
            
            if msb_type:
                ob_data = self.find_order_blocks(df, msb_type, pivot_index)
                
                if ob_data:
                    ticker = self.get_ticker_data(symbol)
                    if not ticker:
                        return
                    
                    self.signaled_pairs.add(symbol)
                    current_price = ticker['last']
                    
                    print("\n" + "="*50, flush=True)
                    print(f"พบสัญญาณ MSB ใหม่: {symbol}", flush=True)
                    print(f"เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
                    print("-"*50, flush=True)
                    print(f"ประเภท: {msb_type.upper()} BREAK", flush=True)
                    print(f"ราคาปัจจุบัน: ${current_price:.6f}", flush=True)
                    print(f"การเปลี่ยนแปลงใน 24 ชั่วโมง: {ticker['change_percentage']:.2f}%", flush=True)
                    print(f"ช่วง 24 ชั่วโมง: ${ticker['low_24h']:.6f} - ${ticker['high_24h']:.6f}", flush=True)
                    print(f"ปริมาณ 24 ชั่วโมง: ${ticker['volume']:,.2f}", flush=True)
                    print(f"\nOrder Block ({ob_data['type']}):", flush=True)
                    print(f"สูงสุด: ${ob_data['high']:.6f}", flush=True)
                    print(f"ต่ำสุด: ${ob_data['low']:.6f}", flush=True)
                    
                    # จัดการการซื้อขายตามประเภทสัญญาณ
                    if msb_type == 'bullish':
                        self.handle_bullish_signal(symbol, current_price)
                    else:  # bearish
                        self.handle_bearish_signal(symbol, current_price)
                        
                    print("="*50 + "\n", flush=True)

        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการวิเคราะห์ {symbol}: {str(e)}", flush=True)

    def scan_market(self):
        """ฟังก์ชันหลักในการสแกนตลาด"""
        print("\nเริ่มการสแกน MSB Scanner...", flush=True)
        print(f"ปริมาณขั้นต่ำ 24 ชั่วโมง: ${self.min_volume:,.2f}", flush=True)
        print("กำลังมองหา Market Structure Breaks ในช่วงเวลา 1 ชั่วโมง...", flush=True)
        
        def run_scan():
            try:
                pairs = self.get_valid_pairs()
                print(f"\nกำลังสแกน {len(pairs)} คู่ที่มีปริมาณเพียงพอ...", flush=True)
                
                for pair in pairs:
                    self.analyze_pair(pair)
                    time.sleep(0.2)
                
                print("\nการสแกนเสร็จสิ้น.", flush=True)
                
            except Exception as e:
                print(f"เกิดข้อผิดพลาดในการสแกนตลาด: {str(e)}", flush=True)

        try:
            while True:
                # เริ่มการสแกนครั้งแรกทันที
                current_time = datetime.now()
                print(f"\nเริ่มการสแกนที่ {current_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
                run_scan()
                
                # คำนวณเวลาจนกว่าจะถึงนาทีแรกของชั่วโมงถัดไป
                current_time = datetime.now()
                minutes_to_wait = 60 - current_time.minute
                seconds_to_wait = 60 - current_time.second
                total_seconds = minutes_to_wait * 60 + seconds_to_wait
                
                next_scan_time = (current_time + timedelta(seconds=total_seconds)).strftime('%Y-%m-%d %H:%M:%S')
                print(f"\nการสแกนครั้งถัดไปจะเริ่มที่ {next_scan_time}", flush=True)
                
                # รอพร้อมตัวนับถอยหลัง
                while total_seconds > 0:
                    minutes = total_seconds // 60
                    seconds = total_seconds % 60
                    print(f"เวลาจนกว่าจะถึงการสแกนครั้งถัดไป: {minutes:02d}:{seconds:02d}", end='\r', flush=True)
                    time.sleep(1)
                    total_seconds -= 1

        except KeyboardInterrupt:
            print("\nการสแกนถูกหยุดโดยผู้ใช้.", flush=True)

def main():
    random.seed()
    scanner = MarketStructureScanner(API_KEY, API_SECRET)
    scanner.scan_market()

if __name__ == "__main__":
    main()
