from binance.client import Client
import pandas as pd
from datetime import datetime, timedelta

def fetch_and_save_bitcoin_prices(api_key, api_secret):
    # Initialize the Binance client with your API credentials
    client = Client(api_key=api_key, api_secret=api_secret)

    # Calculate the start and end timestamps for the past year
    end_time = datetime.now()
    start_time = end_time - timedelta(days=65)

    # Convert timestamps to milliseconds for the API call
    start_str = int(start_time.timestamp() * 1000)
    end_str = int(end_time.timestamp() * 1000)

    # Fetch historical klines (OHLCV data) for BTC/USDT on 1-hour intervals
    klines = client.get_historical_klines("BTCUSDT", Client.KLINE_INTERVAL_1HOUR, start_str, end_str)

    # Create a DataFrame with the appropriate column names
    columns = ['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time', 'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 'Taker Buy Quote Asset Volume', 'Ignore']
    df = pd.DataFrame(klines, columns=columns)

    # Convert timestamps from milliseconds to readable dates
    df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
    df['Close Time'] = pd.to_datetime(df['Close Time'], unit='ms')

    # Optionally, you can drop the 'Ignore' column if not needed
    df = df.drop(columns=['Ignore'])

    # Save the DataFrame to a CSV file
    csv_file_path = "BTCUSDT_hourly_prices.csv"
    df.to_csv(csv_file_path, index=False)

    print(f"Saved Bitcoin prices to {csv_file_path}")

# Replace 'YOUR_API_KEY' and 'YOUR_API_SECRET' with your actual Binance API credentials
api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'

fetch_and_save_bitcoin_prices(api_key, api_secret)
