import math
import matplotlib.pyplot as plt
import sys
from scipy import stats
import ccxt
import os
import random
import time
import pandas as pd
import numpy as np
import requests
from binance.client import Client
from datetime import datetime, timedelta
import io
from sklearn.linear_model import LinearRegression
from typing import List
import talib

# ดึงค่า API key และ secret จาก environment variables
#api_key = os.getenv('BINANCE_API_KEY')
#api_secret = os.getenv('BINANCE_SECRET_KEY')
#line_token = os.getenv('LINE_NOTIFY_TOKEN')

api_key="wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN"
api_secret="8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU"

api_key_for_withdraw="Ujet1FjuMIwxxyPzArJUu3NDZYXsaqWEj6riAJVintMMtgOQFqfxkDYwLeieyPNb"
api_secret_withdraw="QitSQ5S5WE6qoSecFnFjBzrIBJEivJJPS8NHBhbFgGt0dE6KJrZMEJL5cSGegJhq"

line_token="aMFv92TD5VFEXQ3fU9gN1sAaWWrkyVoo6VlJe95hvE7"
line_token_group="u63d6tjQyeDimyWKB8p2a4uecdtZ7DkKuhTSFNfJoGO"
line_all_message = ""

# สร้างอินสแตนซ์ของ Binance Futures
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
})

client = Client(api_key, api_secret)
trade_time_frame = '15m'
tread_time_frame_stop_loss = '15m'
limit_time_frame_for_stop_loss = 28
future_leverage = 15
temp_folder = 'temp'
line_all_message = ""
ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']

# ตรวจสอบว่า API key, secret และ line_token ไม่เป็น None
if not api_key or not api_secret or not line_token:
    raise ValueError("API key, secret หรือ LINE token ไม่ถูกต้อง")














import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
import matplotlib
matplotlib.use('Agg')  # Use Agg backend to avoid tkinter issues
import matplotlib.pyplot as plt
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException

@dataclass
class Pattern:
    title: str
    description: str

def analyze_swing_highs_lows_patterns(symbol, timeframes=['1h', '4h'], days_back=60, length=21, recent_hours=44):
    # Initialize Binance client
    client = Client()

    # Validate and convert timeframe
    valid_timeframes = {'1m': Client.KLINE_INTERVAL_1MINUTE,
                        '3m': Client.KLINE_INTERVAL_3MINUTE,
                        '5m': Client.KLINE_INTERVAL_5MINUTE,
                        '15m': Client.KLINE_INTERVAL_15MINUTE,
                        '30m': Client.KLINE_INTERVAL_30MINUTE,
                        '1h': Client.KLINE_INTERVAL_1HOUR,
                        '2h': Client.KLINE_INTERVAL_2HOUR,
                        '4h': Client.KLINE_INTERVAL_4HOUR,
                        '6h': Client.KLINE_INTERVAL_6HOUR,
                        '8h': Client.KLINE_INTERVAL_8HOUR,
                        '12h': Client.KLINE_INTERVAL_12HOUR,
                        '1d': Client.KLINE_INTERVAL_1DAY,
                        '3d': Client.KLINE_INTERVAL_3DAY,
                        '1w': Client.KLINE_INTERVAL_1WEEK,
                        '1M': Client.KLINE_INTERVAL_1MONTH}
    
    results = {}
    overall_signal = "NORMAL"
    
    # Create a figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(20, 20))
    
    for i, timeframe in enumerate(timeframes):
        if timeframe not in valid_timeframes:
            raise ValueError(f"Invalid timeframe. Choose from {', '.join(valid_timeframes.keys())}")
        
        binance_timeframe = valid_timeframes[timeframe]

        # Calculate start date and end date
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        trading_signal = "NORMAL"

        try:
            # Download data from Binance
            klines = client.get_historical_klines(symbol, binance_timeframe, start_date.strftime("%d %b %Y %H:%M:%S"), end_date.strftime("%d %b %Y %H:%M:%S"))
            
            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df = df.astype(float)

            # Check if data is empty
            if df.empty:
                raise ValueError(f"No data available for {symbol} from {start_date} to {end_date} with {timeframe} interval.")

            # Prepare data
            df['o'] = df['open']
            df['h'] = df['high']
            df['l'] = df['low']
            df['c'] = df['close']
            df['d'] = abs(df['c'] - df['o'])

            # Pivot high and low
            df['ph'] = df['high'].rolling(window=2*length+1, center=True).max()
            df['pl'] = df['low'].rolling(window=2*length+1, center=True).min()

            # Pattern definitions
            patterns = {
                'Hammer': Pattern('Hammer', "Short body with a long lower wick, found at the bottom of a downward trend."),
                'Shooting Star': Pattern('Shooting Star', "Small lower body with a long upper wick, forms in an uptrend."),
            }

            # Pattern conditions
            df['Hammer'] = (df['pl'] == df['low']) & (np.minimum(df['o'], df['c']) - df['low'] > df['d']) & (df['high'] - np.maximum(df['c'], df['o']) < df['d'])
            df['Shooting Star'] = (df['ph'] == df['high']) & (df['high'] - np.maximum(df['open'], df['close']) > df['d']) & (np.minimum(df['close'], df['open']) - df['low'] < df['d'])

            # Identify swing highs and lows
            df['Swing High'] = (df['ph'] == df['high']) & (df['ph'].shift(1) != df['high'].shift(1))
            df['Swing Low'] = (df['pl'] == df['low']) & (df['pl'].shift(1) != df['low'].shift(1))

            # Check for Hammer or Shooting Star in the last 14 hours
            recent_cutoff = end_date - timedelta(hours=recent_hours)
            recent_data = df.loc[recent_cutoff:]
            hammer_found = recent_data['Hammer'].any()
            shooting_star_found = recent_data['Shooting Star'].any()

            # Determine trading signal
            if hammer_found:
                trading_signal = "LONG"
            elif shooting_star_found:
                trading_signal = "SHORT"
            else:
                trading_signal = "NORMAL"
        
            # Update overall signal if a non-NORMAL signal is found
            if trading_signal != "NORMAL":
                overall_signal = trading_signal

            # Plot on the appropriate subplot
            ax = ax1 if i == 0 else ax2
            
            ax.plot(df.index, df['close'], label='Close Price')
            
            # Plot swing highs and lows
            ax.scatter(df.index[df['Swing High']], df['high'][df['Swing High']], color='red', label='Swing High', marker='^')
            ax.scatter(df.index[df['Swing Low']], df['low'][df['Swing Low']], color='green', label='Swing Low', marker='v')

            # Annotate patterns
            for pattern_name in patterns.keys():
                pattern_indices = df.index[df[pattern_name]]
                for idx in pattern_indices:
                    ax.annotate(pattern_name, (idx, df.loc[idx, 'close']), 
                                xytext=(0, 10), textcoords='offset points', ha='center', va='bottom',
                                bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.5),
                                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))

            ax.set_title(f'Swing Highs/Lows & Candle Patterns for {symbol} ({timeframe} Timeframe)\nTrading Signal: {trading_signal}')
            ax.set_xlabel('Date')
            ax.set_ylabel('Price')
            ax.legend()
            ax.grid(True)
            ax.tick_params(axis='x', rotation=45)

            results[timeframe] = {
                'trading_signal': trading_signal,
            }

        except BinanceAPIException as e:
            print(f"Error fetching data from Binance for {timeframe}: {e}")
            results[timeframe] = None
        except Exception as e:
            print(f"An unexpected error occurred for {timeframe}: {e}")
            results[timeframe] = None

    if overall_signal != "NORMAL":
        # Create 'temp' folder if it doesn't exist
        if not os.path.exists('temp'):
            os.makedirs('temp')

        plt.tight_layout()
        # Save the chart
        chart_filename = f'temp/{symbol}_{"-".join(timeframes)}_{start_date.date()}_{end_date.date()}.png'
        plt.savefig(chart_filename)
        plt.close()  # Close the plot to free up memory

        results['chart_filename'] = chart_filename
    else:
        plt.close()  # Close the plot without saving if no signal

    return results
















def fetch_future_symbols():
    def get_futures_symbols() -> List[str]:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url)
        data = response.json()
        return [symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING']

    def get_latest_prices(symbols: List[str]) -> dict:
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        response = requests.get(url)
        data = response.json()
        return {item['symbol']: float(item['price']) for item in data if item['symbol'] in symbols}

    def get_24h_volume(symbols: List[str]) -> dict:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        response = requests.get(url)
        data = response.json()
        return {item['symbol']: float(item['volume']) for item in data if item['symbol'] in symbols}

    symbols = get_futures_symbols()
    prices = get_latest_prices(symbols)
    volumes = get_24h_volume(symbols)

    filtered_symbols = []
    for symbol in symbols:
        if symbol in prices and symbol in volumes:
            volume_usdt = prices[symbol] * volumes[symbol]
            if volume_usdt > 100000000:
                filtered_symbols.append(symbol)

    random.shuffle(filtered_symbols)
    # ลบที่ไม่ได้ต่อท้ายด้วย USDT
    filtered_symbols = [x for x in filtered_symbols if x.endswith('USDT')]
    # ลบที่มีตัวเลขนำหน้า 
    filtered_symbols = [x for x in filtered_symbols if not x[0].isdigit()]

    return filtered_symbols






# start
# ลบ file ใน sub folder temp ทิ้ง
for filename in os.listdir(temp_folder):
    file_path = os.path.join(temp_folder, filename)
    try:
        if os.path.isfile(file_path):
            os.unlink(file_path)
    except Exception as e:
        print(f"Error deleting {file_path}: {e}")

print("Start", flush=True)
future_exchange_info = client.futures_exchange_info()
symbols = fetch_future_symbols()
for symbol in symbols:
    print(f"Analyzing {symbol}...", flush=True)
    try:
        result = analyze_swing_highs_lows_patterns(symbol)
        print(result, flush=True)
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}", flush=True)
