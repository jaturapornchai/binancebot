import ccxt
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Initialize the Binance client
binance = ccxt.binance()

# Fetch historical data for BTCUSDT 1h timeframe for the last month
symbol = 'BTC/USDT'
timeframe = '1h'
since = binance.parse8601('2024-06-19T00:00:00Z')
ohlcv = binance.fetch_ohlcv(symbol, timeframe, since=since)

# Convert data to DataFrame
data = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
data.set_index('timestamp', inplace=True)

# Function to identify peaks and troughs
def find_peaks_troughs(prices, window_size=10):
    peaks = []
    troughs = []
    for i in range(window_size, len(prices) - window_size):
        if prices[i] == max(prices[i-window_size:i+window_size]):
            peaks.append(i)
        if prices[i] == min(prices[i-window_size:i+window_size]):
            troughs.append(i)
    return peaks, troughs

# Identifying peaks and troughs
highs = data['high'].values
lows = data['low'].values

peaks, troughs = find_peaks_troughs(highs)
_, troughs_low = find_peaks_troughs(lows)

# Plotting the price data
plt.figure(figsize=(12, 6))
plt.plot(data.index, data['high'], label='High Prices', color='blue')
plt.plot(data.index, data['low'], label='Low Prices', color='red')

# Plotting peaks and troughs
plt.scatter(data.index[peaks], highs[peaks], marker='^', color='green', label='Peaks')
plt.scatter(data.index[troughs], highs[troughs], marker='v', color='red', label='Troughs')

# Drawing the triangle pattern lines
for i in range(1, len(peaks)):
    plt.plot([data.index[peaks[i-1]], data.index[peaks[i]]], 
             [highs[peaks[i-1]], highs[peaks[i]]], 
             color='green')

for i in range(1, len(troughs)):
    plt.plot([data.index[troughs[i-1]], data.index[troughs[i]]], 
             [highs[troughs[i-1]], highs[troughs[i]]], 
             color='red')

plt.title('Triangle Pattern in BTCUSDT')
plt.xlabel('Time')
plt.ylabel('Price (USD)')
plt.legend()
plt.grid(True)
plt.show()
