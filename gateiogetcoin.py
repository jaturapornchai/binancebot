import requests
import pandas as pd
from datetime import datetime
import time
import re

class GateioVolumeScanner:
    def __init__(self):
        self.base_url = "https://api.gateio.ws/api/v4"
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    def is_valid_coin(self, symbol):
        """
        Check if coin name is valid:
        - No numbers in the name
        - Doesn't start with S_ or L_
        """
        base_coin = symbol.split('_')[0]
        
        # Check for numbers
        if any(char.isdigit() for char in base_coin):
            return False
            
        # Check for S_ or L_ prefix
        if base_coin.startswith('S_') or base_coin.startswith('L_'):
            return False
            
        return True

    def get_candlesticks(self, symbol, interval='1h', limit=24):
        """Get candlestick data for a trading pair"""
        endpoint = f"{self.base_url}/spot/candlesticks"
        params = {
            'currency_pair': symbol,
            'interval': interval,
            'limit': limit
        }
        try:
            response = requests.get(endpoint, headers=self.headers, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching candlesticks for {symbol}: {str(e)}")
        return None

    def scan_high_volume_pairs(self):
        """Scan for pairs with high buy volume in last 24 timeframes"""
        print(f"\n🔍 Starting volume scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        high_volume_pairs = []

        try:
            # Get all trading pairs
            endpoint = f"{self.base_url}/spot/currency_pairs"
            response = requests.get(endpoint, headers=self.headers)
            if response.status_code != 200:
                print("Failed to fetch trading pairs")
                return []

            pairs = response.json()
            valid_pairs = [p for p in pairs if p['id'].endswith('_USDT') and self.is_valid_coin(p['id'])]
            total_pairs = len(valid_pairs)

            print(f"\nFound {total_pairs} valid USDT pairs (excluding numbered coins and S_/L_ prefixes)")
            print("Starting volume analysis...")

            processed = 0
            for pair in valid_pairs:
                symbol = pair['id']
                processed += 1
                print(f"\rProcessing {processed}/{total_pairs}: {symbol}", end='', flush=True)

                candles = self.get_candlesticks(symbol)
                if not candles:
                    continue

                try:
                    df = pd.DataFrame(candles, columns=[
                        'timestamp', 'volume', 'close', 'high',
                        'low', 'open', 'amount', 'count'
                    ])

                    # Convert amount (buy volume) to numeric and calculate total
                    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
                    df['close'] = pd.to_numeric(df['close'], errors='coerce')

                    # Calculate total buy volume in USDT
                    total_buy_volume_usdt = (df['amount'] * df['close']).sum()

                    if total_buy_volume_usdt > 10000:  # More than $10,000 in buy volume
                        pair_info = {
                            'symbol': symbol,
                            'buy_volume_usdt': total_buy_volume_usdt
                        }
                        high_volume_pairs.append(pair_info)
                        print(f"\n📈 High volume pair found: {symbol} - ${total_buy_volume_usdt:,.2f}")

                except Exception as e:
                    print(f"\nError processing {symbol}: {str(e)}")
                    continue

                time.sleep(0.1)  # Rate limiting

            # Sort pairs by volume
            high_volume_pairs.sort(key=lambda x: x['buy_volume_usdt'], reverse=True)

            # Save to file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'high_volume_pairs_{timestamp}.txt'

            with open(filename, 'w') as f:
                f.write(f"High Volume Pairs (>{10000:,} USDT in 24h) - Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("Excluding coins with numbers and S_/L_ prefixes\n")
                f.write("-" * 80 + "\n\n")
                
                for pair in high_volume_pairs:
                    f.write(f"{pair['symbol']}: ${pair['buy_volume_usdt']:,.2f}\n")

            print(f"\n\n✅ Scan completed. Found {len(high_volume_pairs)} pairs with high volume.")
            print(f"📝 Results saved to {filename}")

            return high_volume_pairs

        except Exception as e:
            print(f"\nAn error occurred during scan: {str(e)}")
            return []

def main():
    print("🔍 Gate.io Volume Scanner Starting...")
    scanner = GateioVolumeScanner()
    scanner.scan_high_volume_pairs()

if __name__ == "__main__":
    main()