import requests
import pandas as pd
import time
import hmac
import hashlib
import json
from datetime import datetime
from gate_api import ApiClient, Configuration, Order, SpotApi
from gate_api.exceptions import ApiException, GateApiException

# API Credentials
API_KEY = "c84d3616806f44e5651912c198094a1b"
API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"

class GateioTrader:
    def __init__(self):
        self.base_url = "https://api.gateio.ws/api/v4"
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        self.request_count = 0
        self.last_request_time = time.time()
        self.rate_limit = 300  # requests per minute
        
        # Initialize gate-api client
        config = Configuration(key=API_KEY, secret=API_SECRET)
        client = ApiClient(config)
        self.spot_api = SpotApi(client)
        
    def _rate_limit_check(self):
        """Implement rate limiting"""
        current_time = time.time()
        time_passed = current_time - self.last_request_time
        
        if time_passed < 60:  # Within a minute window
            if self.request_count >= self.rate_limit:
                sleep_time = 60 - time_passed
                print(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
                self.request_count = 0
                self.last_request_time = time.time()
        else:
            self.request_count = 0
            self.last_request_time = current_time
            
        self.request_count += 1

    def place_spot_order(self, symbol, amount_usdt=10):
        """Place a spot market buy order using gate-api"""
        try:
            # Get current price
            tickers = self.spot_api.list_tickers(currency_pair=symbol)
            if not tickers or not tickers[0].last:
                print(f"Could not get price for {symbol}")
                return False
            
            current_price = float(tickers[0].last)
            quantity = amount_usdt / current_price
            
            # Create market buy order
            order = Order(
                currency_pair=symbol,
                side='buy',
                amount=str(round(quantity, 8)),
                type='market',
                time_in_force='ioc'  # Immediate or Cancel for market orders
            )
            
            # Place order
            result = self.spot_api.create_order(order)
            
            print(f"\n✅ Market Buy Order Placed for {symbol}")
            print(f"Order ID: {result.id}")
            print(f"Status: {result.status}")
            print(f"Amount: {quantity:.8f} {symbol.split('_')[0]}")
            print(f"Total: {amount_usdt} USDT")
            return True
            
        except GateApiException as ex:
            print(f"\n❌ Gate.io API Error for {symbol}:")
            print(f"Label: {ex.label}")
            print(f"Message: {ex.message}")
            return False
        except ApiException as e:
            print(f"\n❌ API Error for {symbol}: {str(e)}")
            return False
        except Exception as e:
            print(f"\n❌ Error placing order for {symbol}: {str(e)}")
            return False

    def get_candlesticks(self, symbol, interval='1h', limit=144):
        """Get candlestick data for a trading pair"""
        endpoint = f"{self.base_url}/spot/candlesticks"
        params = {
            'currency_pair': symbol,
            'interval': interval,
            'limit': limit
        }
        response = requests.get(endpoint, headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json()
        return None

    def scan_and_trade(self):
        """Scan for volume spikes and place orders"""
        print(f"\n🔍 Starting scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        pairs_with_signal = 0
        
        try:
            print("\nScanning Gate.io USDT pairs for volume spikes...")
            
            # Get all trading pairs
            endpoint = f"{self.base_url}/spot/currency_pairs"
            response = requests.get(endpoint, headers=self.headers)
            if response.status_code != 200:
                print("Failed to fetch trading pairs")
                return
                
            pairs = response.json()
            usdt_pairs = [
                pair for pair in pairs 
                if pair['id'].endswith('_USDT') and 
                not any(c.isdigit() for c in pair['id'].split('_')[0][0])
            ]
            print(f"\nFound {len(usdt_pairs)} valid USDT pairs")
            
            for idx, pair in enumerate(usdt_pairs, 1):
                symbol = pair['id']
                print(f"\rProcessing {idx}/{len(usdt_pairs)}: {symbol}", end='', flush=True)
                
                try:
                    candles = self.get_candlesticks(symbol)
                    if not candles:
                        continue
                    
                    df = pd.DataFrame(candles, columns=[
                        'timestamp', 'volume', 'close', 'high', 
                        'low', 'open', 'amount', 'count'
                    ])
                    
                    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
                    df = df.dropna(subset=['volume'])
                    
                    if len(df) < 144:
                        continue
                    
                    ma_144 = df['volume'].rolling(window=144).mean()
                    current_volume = float(df['volume'].iloc[-1])
                    avg_volume = float(ma_144.iloc[-1])
                    
                    if pd.isna(avg_volume) or avg_volume == 0:
                        continue
                    
                    volume_increase = ((current_volume - avg_volume) / avg_volume) * 100
                    
                    if volume_increase > 1000:  # Volume must increase by 1000%
                        df['close'] = pd.to_numeric(df['close'], errors='coerce')
                        df['open'] = pd.to_numeric(df['open'], errors='coerce')
                        
                        try:
                            price_change = ((float(df['close'].iloc[-1]) - float(df['open'].iloc[-1])) / 
                                          float(df['open'].iloc[-1])) * 100
                        except (ValueError, ZeroDivisionError):
                            price_change = 0
                        
                        volume_24h = float(df['volume'].tail(24).sum())
                        
                        if current_volume > avg_volume and volume_24h > 0:
                            pairs_with_signal += 1
                            
                            print(f"\n\n🚨 Volume Spike Found: {symbol}")
                            print(f"💹 Volume Increase: {volume_increase:.2f}%")
                            print(f"📈 Price Change: {price_change:.2f}%")
                            print(f"💰 Price: {float(df['close'].iloc[-1]):.8f} USDT")
                            print(f"📊 Volume (Current/24h/144MA): {current_volume:.2f} / {volume_24h:.2f} / {avg_volume:.2f}")
                            
                            self.place_spot_order(symbol, amount_usdt=10)
                            print("-" * 80)
                
                except Exception as e:
                    continue
                
                time.sleep(0.1)
            
            print(f"\n\n✨ Scan completed. Found {pairs_with_signal} pairs with signals.")
            
        except Exception as e:
            print(f"\nAn error occurred during scan: {str(e)}")

def main():
    print("🤖 Gate.io Volume Scanner Bot Starting...")
    trader = GateioTrader()
    
    # Run first scan
    trader.scan_and_trade()
    
    print("\n⏰ Waiting for the first minute of next hour...")
    
    while True:
        if datetime.now().minute == 0:
            trader.scan_and_trade()
            time.sleep(55)
        time.sleep(1)

if __name__ == "__main__":
    main()