import ccxt
import pandas as pd
import numpy as np
import talib
import matplotlib.pyplot as plt

# ตั้งค่า API key และ secret
api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'

# สร้าง client ของ Binance
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret
})

# ดึงข้อมูลราคาจาก Binance
symbol = 'BTC/USDT'
timeframe = '1h'
since = exchange.parse8601('2023-01-01T00:00:00Z')
ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since)
df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
df.set_index('timestamp', inplace=True)

# คำนวณ RSI
df['rsi'] = talib.RSI(df['close'], timeperiod=14)

# ฟังก์ชันหาจุด pivot
def pivot_points(series, left, right):
    pivots = []
    for i in range(left, len(series) - right):
        pivot = True
        for j in range(1, left + 1):
            if series[i] > series[i - j]:
                pivot = False
        for j in range(1, right + 1):
            if series[i] > series[i + j]:
                pivot = False
        if pivot:
            pivots.append(i)
    return pivots

# หาจุด pivot สำหรับราคาและ RSI
left = 5
right = 5
df['pivot_low'] = [i in pivot_points(df['low'], left, right) for i in range(len(df))]
df['pivot_high'] = [i in pivot_points(df['high'], left, right) for i in range(len(df))]
df['rsi_pivot_low'] = [i in pivot_points(df['rsi'], left, right) for i in range(len(df))]
df['rsi_pivot_high'] = [i in pivot_points(df['rsi'], left, right) for i in range(len(df))]

# ตรวจหา Divergences
def detect_divergence(df, type='bullish'):
    if type == 'bullish':
        price_pivot = df['pivot_low']
        rsi_pivot = df['rsi_pivot_high']
        price_condition = lambda i: df['low'][i] < df['low'][i - 1]
        rsi_condition = lambda i: df['rsi'][i] > df['rsi'][i - 1]
    else:
        price_pivot = df['pivot_high']
        rsi_pivot = df['rsi_pivot_low']
        price_condition = lambda i: df['high'][i] > df['high'][i - 1]
        rsi_condition = lambda i: df['rsi'][i] < df['rsi'][i - 1]
    
    divergence = []
    for i in range(len(df)):
        if price_pivot[i] and rsi_pivot[i]:
            if price_condition(i) and rsi_condition(i):
                divergence.append(i)
    return divergence

bullish_divergence = detect_divergence(df, type='bullish')
bearish_divergence = detect_divergence(df, type='bearish')

# สร้างกราฟ
plt.figure(figsize=(14, 10))

# กราฟราคา
plt.subplot(2, 1, 1)
plt.plot(df.index, df['close'], label='Close Price')
plt.scatter(df.index[bullish_divergence], df['close'][bullish_divergence], marker='^', color='g', label='Bullish Divergence')
plt.scatter(df.index[bearish_divergence], df['close'][bearish_divergence], marker='v', color='r', label='Bearish Divergence')
plt.title('BTC/USDT Price with Divergences')
plt.legend()

# กราฟ RSI
plt.subplot(2, 1, 2)
plt.plot(df.index, df['rsi'], label='RSI', color='b')
plt.axhline(70, linestyle='--', alpha=0.5, color='r')
plt.axhline(30, linestyle='--', alpha=0.5, color='g')
plt.scatter(df.index[bullish_divergence], df['rsi'][bullish_divergence], marker='^', color='g')
plt.scatter(df.index[bearish_divergence], df['rsi'][bearish_divergence], marker='v', color='r')
plt.title('RSI with Divergences')
plt.legend()

plt.show()
