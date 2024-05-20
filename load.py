import ccxt
import pandas as pd
import talib

# Connect to Binance exchange
exchange = ccxt.binance()

# Define the symbol and timeframe
symbol = 'BTCUSDT'
timeframe = '4h'

# Fetch historical data
bars = exchange.fetch_ohlcv(symbol, timeframe)

# Convert data to a DataFrame
df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

# Calculate some example indicators using TA-Lib
df['SMA'] = talib.SMA(df['close'])
df['RSI'] = talib.RSI(df['close'])

# Save the DataFrame to a CSV file
csv_filename = symbol + '_4h_data.csv'
df.to_csv(csv_filename, index=False)

print(f"Data saved to {csv_filename}")
