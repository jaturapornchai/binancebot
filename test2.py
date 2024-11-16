from gate_api import ApiClient, Configuration, SpotApi
from gate_api.exceptions import ApiException, GateApiException
import pandas as pd
import numpy as np
import time
from datetime import datetime
import logging

# API Credentials
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
        self.min_volume = 100000  # Minimum 24h volume in USD
        self.signaled_pairs = set()  # Keep track of pairs that have already signaled
        
    def get_valid_pairs(self):
        """Get valid pairs with sufficient volume"""
        try:
            pairs = self.spot_api.list_currency_pairs()
            tickers = self.spot_api.list_tickers()
            
            # Create dictionary of 24h volumes
            volume_dict = {}
            for ticker in tickers:
                if ticker.currency_pair.endswith('USDT'):
                    volume_usd = float(ticker.quote_volume)  # Already in USDT
                    volume_dict[ticker.currency_pair] = volume_usd
            
            valid_pairs = []
            for pair in pairs:
                # Check if pair ends with USDT, has no numbers, and meets volume requirement
                if (pair.id.endswith('USDT') and 
                    not any(char.isdigit() for char in pair.id[:-4]) and
                    pair.id in volume_dict and 
                    volume_dict[pair.id] >= self.min_volume):
                    valid_pairs.append({
                        'symbol': pair.id,
                        'volume': volume_dict[pair.id]
                    })
            
            # Sort by volume
            valid_pairs.sort(key=lambda x: x['volume'], reverse=True)
            return valid_pairs
            
        except Exception as e:
            print(f"Error getting valid pairs: {str(e)}")
            return []

    def get_ticker_data(self, symbol):
        """Get current ticker data for a symbol"""
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
            print(f"Error getting ticker data for {symbol}: {str(e)}")
            return None

    def get_candlesticks(self, symbol, interval='1h', limit=100):
        """Get candlestick data for analysis"""
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
            print(f"Error getting candlesticks for {symbol}: {str(e)}")
            return None

    def analyze_market_structure(self, df):
        """Analyze market structure and find breaks"""
        try:
            df['highest'] = df['high'].rolling(window=self.zigzag_len).max()
            df['lowest'] = df['low'].rolling(window=self.zigzag_len).min()
            
            # Identify swing points
            df['to_up'] = df['high'] >= df['highest'].shift(1)
            df['to_down'] = df['low'] <= df['lowest'].shift(1)
            
            # Store high and low points
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
                    
            # Check for market structure break
            if len(high_points) >= 2 and len(low_points) >= 2:
                h0, h1 = high_points[-1], high_points[-2]
                l0, l1 = low_points[-1], low_points[-2]
                
                # Check bullish break
                if h0['price'] > h1['price'] and \
                   df.iloc[-1]['high'] > h0['price'] + abs(h0['price'] - l0['price']) * self.fib_factor:
                    return 'bullish', l0['index']
                
                # Check bearish break
                elif l0['price'] < l1['price'] and \
                     df.iloc[-1]['low'] < l0['price'] - abs(h0['price'] - l0['price']) * self.fib_factor:
                    return 'bearish', h0['index']
                    
            return None, None
            
        except Exception as e:
            print(f"Error in market structure analysis: {str(e)}")
            return None, None

    def find_order_blocks(self, df, msb_type, pivot_index):
        """Find order blocks after MSB"""
        try:
            if msb_type == 'bullish':
                # Look for red candle (bearish) for bullish OB
                for i in range(pivot_index, len(df)):
                    if df.iloc[i]['open'] > df.iloc[i]['close']:
                        return {
                            'type': 'BU-OB',
                            'high': df.iloc[i]['high'],
                            'low': df.iloc[i]['low']
                        }
            else:
                # Look for green candle (bullish) for bearish OB
                for i in range(pivot_index, len(df)):
                    if df.iloc[i]['open'] < df.iloc[i]['close']:
                        return {
                            'type': 'BE-OB',
                            'high': df.iloc[i]['high'],
                            'low': df.iloc[i]['low']
                        }
            return None
        except Exception as e:
            print(f"Error finding order blocks: {str(e)}")
            return None

    def analyze_pair(self, pair_info):
        """Analyze a single trading pair"""
        symbol = pair_info['symbol']
        
        # Skip if we've already seen this pair
        if symbol in self.signaled_pairs:
            return
            
        try:
            # Get candlestick data
            candles = self.get_candlesticks(symbol)
            if not candles:
                return
                
            # Convert to DataFrame
            df = pd.DataFrame(candles)
            
            # Find market structure break
            msb_type, pivot_index = self.analyze_market_structure(df)
            
            if msb_type:
                # Get order blocks
                ob_data = self.find_order_blocks(df, msb_type, pivot_index)
                
                if ob_data:
                    # Get current price data
                    ticker = self.get_ticker_data(symbol)
                    if not ticker:
                        return
                    
                    # Add to signaled pairs
                    self.signaled_pairs.add(symbol)
                    
                    # Print signal information
                    print("\n" + "="*50)
                    print(f"NEW MSB SIGNAL: {symbol}")
                    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print("-"*50)
                    print(f"Type: {msb_type.upper()} BREAK")
                    print(f"Current Price: ${ticker['last']:.6f}")
                    print(f"24h Change: {ticker['change_percentage']:.2f}%")
                    print(f"24h Range: ${ticker['low_24h']:.6f} - ${ticker['high_24h']:.6f}")
                    print(f"24h Volume: ${ticker['volume']:,.2f}")
                    print(f"\nOrder Block ({ob_data['type']}):")
                    print(f"High: ${ob_data['high']:.6f}")
                    print(f"Low: ${ob_data['low']:.6f}")
                    print("="*50 + "\n")

        except Exception as e:
            print(f"Error analyzing {symbol}: {str(e)}")

    def scan_market(self):
        """Main scanning function"""
        print("\nStarting MSB Scanner...")
        print(f"Minimum 24h Volume: ${self.min_volume:,.2f}")
        print("Looking for Market Structure Breaks in 1H timeframe...")
        
        while True:
            try:
                pairs = self.get_valid_pairs()
                print(f"\nScanning {len(pairs)} pairs with sufficient volume...")
                
                for pair in pairs:
                    self.analyze_pair(pair)
                    time.sleep(0.2)  # Rate limiting
                
                print("\nScan complete. Waiting for next scan...")
                time.sleep(60)  # Wait 1 minute before next scan
                
            except KeyboardInterrupt:
                print("\nScanning stopped by user.")
                break
            except Exception as e:
                print(f"Error in market scan: {str(e)}")
                time.sleep(60)  # Wait before retry

def main():
    scanner = MarketStructureScanner(API_KEY, API_SECRET)
    scanner.scan_market()

if __name__ == "__main__":
    main()