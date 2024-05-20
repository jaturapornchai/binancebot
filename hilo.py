import pandas as pd
from binance.client import Client
from binance.enums import *
import numpy as np
import matplotlib.pyplot as plt
from talib import RSI, ATR

# Binance API credentials
api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'

# Initialize client
client = Client(api_key, api_secret)

def get_historical_data(symbol, interval, lookback):
    frame = pd.DataFrame(client.get_historical_klines(symbol, interval, lookback + ' ago UTC'))
    frame = frame.iloc[:, :6]
    frame.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume']
    frame = frame.set_index('Time')
    frame.index = pd.to_datetime(frame.index, unit='ms')
    frame = frame.astype(float)
    return frame

# Get historical data
df = get_historical_data('BTCUSDT', Client.KLINE_INTERVAL_1HOUR, '2 days')

# Calculate RSI
rsi_period = 14
df['RSI'] = RSI(df['Close'], timeperiod=rsi_period)

# Calculate ATR
df['ATR'] = ATR(df['High'], df['Low'], df['Close'], timeperiod=rsi_period)

# Calculate Overbought and Oversold levels
os_level = 30
ob_level = 70
df['OSLV'] = np.where(df['RSI'] < os_level, 20, 30)
df['OBLV'] = np.where(df['RSI'] > ob_level, 80, 70)

# Alert logic
def check_alerts(row):
    if row['RSI'] < row['OSLV']:
        return 'Long'
    elif row['RSI'] > row['OBLV']:
        return 'Short'
    else:
        return 'Normal'

df['Alert'] = df.apply(check_alerts, axis=1)

# Plotting
plt.figure(figsize=(15, 7))
plt.plot(df['RSI'], label='RSI', color='teal')
plt.fill_between(df.index, df['OSLV'], os_level, color='blue', alpha=0.3)
plt.fill_between(df.index, df['OBLV'], ob_level, color='yellow', alpha=0.3)
plt.axhline(y=os_level, color='gray', linestyle='--')
plt.axhline(y=ob_level, color='gray', linestyle='--')
plt.title('BTCUSDT RSI Analysis')
plt.legend()
plt.show()

# Print alerts
print(df[['RSI', 'Alert']])
