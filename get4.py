import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import talib

from binance.client import Client
from binance.enums import *
# Binance API credentials
api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'

# LINE Notify token
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"


# Initialize the Binance client
client = Client(api_key, api_secret)


# Function to fetch historical data
def get_historical_data(symbol, interval, lookback):
    frame = pd.DataFrame(client.get_historical_klines(symbol, interval, lookback + ' ago UTC'))
    frame = frame.iloc[:,:6]
    frame.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume']
    frame = frame.set_index('Time')
    frame.index = pd.to_datetime(frame.index, unit='ms')
    frame = frame.astype(float)
    return frame

# Function to identify RSI divergences
def identify_divergences(df):
    df['bull_div'] = np.nan
    df['bear_div'] = np.nan
    
    for i in range(1, len(df)):
        # Adjusted conditions for bullish and bearish divergences
        if df['RSI'].iloc[i] > df['RSI'].iloc[i-1] and df['Close'].iloc[i] <= df['Close'].iloc[i-1]:
            df['bull_div'].iloc[i] = df['Close'].iloc[i]

        if df['RSI'].iloc[i] < df['RSI'].iloc[i-1] and df['Close'].iloc[i] >= df['Close'].iloc[i-1]:
            df['bear_div'].iloc[i] = df['Close'].iloc[i]

    return df# Fetch data
symbol = "BTCUSDT"
interval = Client.KLINE_INTERVAL_4HOUR
lookback = "130 days"

df = get_historical_data(symbol, interval, lookback)

# Calculate RSI
df['RSI'] = talib.RSI(df['Close'].values, timeperiod=14)

# Identify divergences
df = identify_divergences(df)

# Plotting
plt.figure(figsize=(12,8))

# Price chart
plt.subplot(2,1,1)
plt.plot(df.index, df['Close'], label='Close Price')
plt.scatter(df.index, df['bull_div'], color='green', label='Bullish Divergence', marker='^')
plt.scatter(df.index, df['bear_div'], color='red', label='Bearish Divergence', marker='v')
plt.title('Price Chart with Divergences')
plt.legend()

# RSI chart
plt.subplot(2,1,2)
plt.plot(df.index, df['RSI'], label='RSI')
plt.title('RSI Chart')
plt.legend()

plt.show()