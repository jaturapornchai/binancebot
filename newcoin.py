from gate_api import ApiClient, Configuration, SpotApi, Order
import requests
import time
from datetime import datetime

API_KEY = "c84d3616806f44e5651912c198094a1b"
API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"

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

    def get_spot_pairs(self):
        """ดึงข้อมูลคู่เทรดทั้งหมด"""
        endpoint = f"{self.base_url}/spot/currency_pairs"
        response = requests.get(endpoint, headers=self.headers).json()
        pairs = []
        for pair_info in response:
            # ตรวจสอบให้แน่ใจว่าไม่มี '_USDT_USDT'
            if pair_info['id'].count('_USDT') == 1:
                pairs.append(pair_info)
        return pairs

    def get_ticker(self, pair):
        """ดึงข้อมูลราคาและวอลุ่ม"""
        endpoint = f"{self.base_url}/spot/tickers"
        response = requests.get(endpoint, params={'currency_pair': pair}, headers=self.headers).json()
        return response[0] if response else None

    def get_first_trade_time(self, pair):
        """ดึงเวลาการเทรดแรกสุด"""
        try:
            endpoint = f"{self.base_url}/spot/trades"
            params = {
                'currency_pair': pair,
                'limit': 1,
                'last_id': 0  # ดึงเทรดแรกสุด
            }
            response = requests.get(endpoint, params=params, headers=self.headers).json()
            if response:
                return datetime.fromtimestamp(float(response[0]['create_time']))
            return None
        except:
            return None

    def get_account_balance(self, symbol):
        """ดึงข้อมูล balance สำหรับเหรียญที่ต้องการ"""
        try:
            # ดึงข้อมูล balance ของเหรียญจากพอร์ต
            balances = self.spot_api.list_spot_accounts()
            for balance in balances:
                if balance.currency.lower() == symbol.lower():
                    # ดึงราคาล่าสุดของเหรียญเป็น USDT
                    ticker = self.get_ticker(symbol + '_USDT')
                    if ticker:
                        price = float(ticker['last'])
                        return float(balance.available) * price
            return 0.0
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึง balance: {str(e)}")
            return 0.0

    def place_buy_order(self, symbol):
        try:
            # ตรวจสอบมูลค่าเหรียญใน port
            current_value = self.get_account_balance(symbol)
            if current_value >= 5:
                print(f"ไม่ทำการซื้อ {symbol} เนื่องจากมูลค่าใน port มากกว่า $5")
                return None
            
            # สั่งซื้อเหรียญเพิ่ม โดยสร้าง currency_pair ที่ถูกต้อง
            order = Order(
                currency_pair=f"{symbol}_USDT",
                side='buy',
                amount='20',
                type='market',
                time_in_force='ioc'
            )
            result = self.spot_api.create_order(order)
            
            print(f"\nส่งคำสั่งซื้อสำเร็จ:", flush=True)
            print(f"สัญลักษณ์: {symbol}", flush=True)
            print(f"มูลค่าประมาณ: $20", flush=True)
            print(f"รหัสคำสั่ง: {result.id}", flush=True)
            
            return result

        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการส่งคำสั่งซื้อ: {str(e)}", flush=True)
            return None

    def scan_new_coins(self):
        """สแกนหาเหรียญใหม่"""
        print("\nกำลังสแกนหาเหรียญที่เพิ่งเข้าตลาด...")
        new_coins = []
        pairs = self.get_spot_pairs()
        now = datetime.now()
        
        print(f"\nพบ {len(pairs)} คู่เทรดทั้งหมด")
        print("กำลังตรวจสอบแต่ละคู่...")
        
        for i, pair_info in enumerate(pairs, 1):
            try:
                pair = pair_info['id']
                if not pair.endswith('_USDT'):
                    continue
                    
                symbol = pair.split('_')[0]
                if any(c.isdigit() for c in symbol):
                    continue
                
                print(f"\rความคืบหน้า: {i}/{len(pairs)} ({i/len(pairs)*100:.1f}%) | ตรวจสอบ: {pair}", end='')
                
                # ดูเวลาเทรดแรกสุด
                first_trade = self.get_first_trade_time(pair)
                if not first_trade:
                    continue
                    
                # เช็คว่าเป็นเหรียญใหม่ใน 24 ชั่วโมง
                hours_listed = (now - first_trade).total_seconds() / 3600
                if hours_listed <= 24:
                    # ดึงข้อมูลเพิ่มเติม
                    ticker = self.get_ticker(pair)
                    if not ticker:
                        continue
                        
                    coin_info = {
                        'pair': pair,
                        'hours_listed': hours_listed,
                        'listed_time': first_trade,
                        'volume': float(ticker['quote_volume']),
                        'last_price': float(ticker['last']),
                        'high_24h': float(ticker['high_24h']),
                        'low_24h': float(ticker['low_24h']),
                        'change_24h': float(ticker['change_percentage'])
                    }
                    new_coins.append(coin_info)
                    print(f"\n🆕 พบเหรียญใหม่: {pair} (เข้าตลาดมา {hours_listed:.1f} ชั่วโมง)")
                    self.place_buy_order(symbol)
                
                time.sleep(0.1)
                
            except Exception as e:
                continue
                
        print("\n\nการสแกนเสร็จสิ้น")
        return new_coins

def format_number(num):
    """จัดรูปแบบตัวเลข"""
    if num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.2f}K"
    return f"{num:.2f}"

def format_thai_time(dt):
    """แปลงเวลาเป็นรูปแบบไทย"""
    thai_months = {
        1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.", 
        5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
        9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."
    }
    
    return f"{dt.day} {thai_months[dt.month]} {dt.year+543} {dt.strftime('%H:%M:%S')}"

def scan():
    try:
        scanner = GateioScanner()
        print("\n=== สแกนหาเหรียญที่เพิ่งเข้าตลาดใน 24 ชั่วโมง ===")
        
        coins = scanner.scan_new_coins()
        
        if coins:
            # เรียงตามเวลาที่เข้าตลาด (ใหม่สุดขึ้นก่อน)
            coins.sort(key=lambda x: x['hours_listed'])
            
            print(f"\nพบ {len(coins)} เหรียญใหม่:")
            for i, coin in enumerate(coins, 1):
                print(f"\n{i}. {coin['pair']}")
                print(f"   เข้าตลาดเมื่อ: {format_thai_time(coin['listed_time'])} ({coin['hours_listed']:.1f} ชม.)")
                print(f"   ราคาล่าสุด: {coin['last_price']:.8f}")
                print(f"   วอลุ่ม: {format_number(coin['volume'])} USDT")
                print(f"   เปลี่ยนแปลง: {coin['change_24h']:.2f}%")
                print(f"   สูงสุด-ต่ำสุด: {coin['high_24h']:.8f} - {coin['low_24h']:.8f}")
        else:
            print("\nไม่พบเหรียญใหม่ในช่วง 24 ชั่วโมงที่ผ่านมา")

    except Exception as e:
        print(f"\nเกิดข้อผิดพลาด: {str(e)}")

def main():
    scan()        
    while True:
        if datetime.now().minute == 1:
            scan()        
        time.sleep(10)

if __name__ == "__main__":
    main()
