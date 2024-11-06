import time
import pandas as pd
import numpy as np
from datetime import datetime
from gate_api import ApiClient, Configuration, SpotApi
from gate_api.exceptions import ApiException, GateApiException

class GateioTradingBot:
    def __init__(self, api_key, api_secret):
        self.config = Configuration(
            key=api_key,
            secret=api_secret,
            host="https://api.gateio.ws/api/v4"
        )
        self.client = ApiClient(self.config)
        self.spot_api = SpotApi(self.client)
        self.check_interval = 3600  # 1 hour in seconds
        self.buy_amount = 20  # Amount in USDT to buy
        self.min_volume = 10000  # Minimum 24h volume in USDT

    def get_candlesticks(self, symbol, interval='1h', limit=2):
        """ดึงข้อมูล candlestick"""
        try:
            candles = self.spot_api.list_candlesticks(
                currency_pair=symbol,
                interval=interval,
                limit=limit
            )
            if candles and len(candles) >= 2 and all(len(c) >= 6 for c in candles):
                return candles
            return None
        except:
            return None

    def get_account_balance(self, currency):
        """ดึงข้อมูลยอดคงเหลือในบัญชี"""
        try:
            balances = self.spot_api.list_spot_accounts()
            for balance in balances:
                if balance.currency.upper() == currency.upper():
                    return float(balance.available)
            return 0
        except Exception as e:
            print(f"Error getting balance: {e}")
            return 0

    def place_market_buy(self, symbol, amount_usdt):
        """ส่งคำสั่งซื้อแบบ market order"""
        try:
            # คำนวณจำนวนเหรียญจากราคาตลาดล่าสุด
            ticker = self.spot_api.list_tickers(currency_pair=symbol)[0]
            price = float(ticker.last)
            amount = amount_usdt / price

            # สร้าง order object ตามรูปแบบที่ถูกต้อง
            from gate_api import Order
            order = Order(
                currency_pair=symbol,
                side='buy',
                amount=str(amount),
                price=str(price * 1.05),  # ตั้งราคาสูงกว่าตลาด 5% เพื่อให้เป็น taker แน่นอน
                time_in_force='ioc',  # Immediate or Cancel
            )
            
            result = self.spot_api.create_order(order)
            print(f"ซื้อสำเร็จ: {symbol} จำนวน ${amount_usdt} USDT")
            return True
        except Exception as e:
            print(f"Error placing order: {e}")
            return False

    def analyze_momentum(self, candles):
        """วิเคราะห์โมเมนตัมของราคา"""
        if not candles or len(candles) < 2:
            return None

        try:
            current = candles[0]
            previous = candles[1]
            
            current_close = float(current[2])
            current_open = float(current[5])
            previous_close = float(previous[2])
            current_volume = float(current[1])
            previous_volume = float(previous[1])

            if current_close <= 0 or previous_close <= 0 or previous_volume <= 0:
                return None
            
            price_change = ((current_close - previous_close) / previous_close) * 100
            volume_change = ((current_volume - previous_volume) / previous_volume) * 100
            
            # เพิ่มเงื่อนไขการขึ้นแรง
            strong_momentum = False
            if current_close > previous_close:
                if volume_change > 50 and price_change > 2:
                    price_action = "🚀 เริ่มขึ้นแรง"
                    strong_momentum = True
                elif volume_change > 20:
                    price_action = "📈 เริ่มขึ้น"
                else:
                    price_action = "↗️ ขึ้นปกติ"
            else:
                return None

            return {
                'price_action': price_action,
                'volume_change': volume_change,
                'price_change_1h': price_change,
                'strong_momentum': strong_momentum
            }
            
        except:
            return None

    def scan_opportunities(self):
        """สแกนหาโอกาสในการเทรด"""
        try:
            print(f"\n=== เริ่มสแกนตลาด - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
            
            # ดึงข้อมูลทั้งหมดจาก API
            tickers = self.spot_api.list_tickers()
            
            valid_tickers = []
            for t in tickers:
                try:
                    if t.currency_pair.endswith('_USDT'):
                        data = {
                            'currency_pair': t.currency_pair,
                            'last': float(t.last),
                            'quote_volume': float(t.quote_volume)
                        }
                        if all(v > 0 for v in [data['last'], data['quote_volume']]):
                            valid_tickers.append(data)
                except:
                    continue
            
            # วิเคราะห์แต่ละคู่เทรด
            for ticker in valid_tickers:
                symbol = ticker['currency_pair']
                volume = ticker['quote_volume']
                
                # ตรวจสอบวอลลุ่มขั้นต่ำ
                if volume < self.min_volume:
                    continue
                
                # วิเคราะห์โมเมนตัม
                candles = self.get_candlesticks(symbol)
                analysis = self.analyze_momentum(candles)
                
                if analysis and analysis.get('strong_momentum'):
                    coin = symbol.replace('_USDT', '')
                    current_balance = self.get_account_balance(coin)
                    current_value = current_balance * float(ticker['last'])
                    
                    print(f"\nพบโอกาสเทรด: {symbol}")
                    print(f"ราคาปัจจุบัน: ${ticker['last']}")
                    print(f"การเปลี่ยนแปลงราคา 1H: {analysis['price_change_1h']:.2f}%")
                    print(f"การเปลี่ยนแปลงวอลลุ่ม: {analysis['volume_change']:.2f}%")
                    print(f"มูลค่าในพอร์ต: ${current_value:.2f}")
                    
                    # ตรวจสอบเงื่อนไขการซื้อ
                    if current_value < 5:
                        print(f"เริ่มซื้อ {symbol}...")
                        self.place_market_buy(symbol, self.buy_amount)
                    else:
                        print(f"มีในพอร์ตเพียงพอแล้ว (${current_value:.2f})")

        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการสแกน: {e}")

    def run(self):
        """เริ่มการทำงานของบอท"""
        print("\nเริ่มต้นการทำงานของบอท...")
        print(f"ตรวจสอบตลาดทุก {self.check_interval // 3600} ชั่วโมง")
        print(f"จำนวนเงินที่ซื้อต่อครั้ง: ${self.buy_amount} USDT")
        print(f"วอลลุ่มขั้นต่ำ: ${self.min_volume:,} USDT")
        
        try:
            while True:
                self.scan_opportunities()
                print(f"\nรอถึงรอบถัดไปในอีก {self.check_interval // 3600} ชั่วโมง...")
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\nหยุดการทำงานของบอท...")

def main():
    # API Credentials
    API_KEY = "c84d3616806f44e5651912c198094a1b"
    API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"
    
    bot = GateioTradingBot(API_KEY, API_SECRET)
    bot.run()

if __name__ == "__main__":
    main()