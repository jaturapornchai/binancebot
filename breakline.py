import ccxt
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf

# Binance API setup
api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
})

# Fetching data
symbol = 'BTC/USDT'
timeframe = '1h'
limit = 500
bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
df.set_index('timestamp', inplace=True)  # Set the timestamp as the index

# MACD Calculation
short_window = 12
long_window = 26
df['short_ma'] = df['close'].rolling(window=short_window, min_periods=1).mean()
df['long_ma'] = df['close'].rolling(window=long_window, min_periods=1).mean()
df['macd'] = df['short_ma'] - df['long_ma']

# Signal Generation
df['signal'] = 0
df.iloc[short_window:, df.columns.get_loc('signal')] = np.where(df['short_ma'][short_window:] > df['long_ma'][short_window:], 1, 0)
df['position'] = df['signal'].diff()

# Support and Resistance Calculation
lookback = 20
df['swing_high'] = df['high'][(df['high'].shift(1) < df['high']) & (df['high'].shift(-1) < df['high'])]
df['swing_low'] = df['low'][(df['low'].shift(1) > df['low']) & (df['low'].shift(-1) > df['low'])]

# Plotting
apds = [
    mpf.make_addplot(df['macd'], panel=1, color='red', type='bar', ylabel='MACD'),
    mpf.make_addplot(df['short_ma'], panel=0, color='orange'),
    mpf.make_addplot(df['long_ma'], panel=0, color='purple'),
    mpf.make_addplot(df['swing_high'], panel=0, type='scatter', markersize=100, marker='^', color='red'),
    mpf.make_addplot(df['swing_low'], panel=0, type='scatter', markersize=100, marker='v', color='green'),
]

fig, axes = mpf.plot(df, type='candle', addplot=apds, figratio=(2,1), figscale=1.5, 
                     style='charles', title=f'{symbol} MACD Signal Chart',
                     returnfig=True)

# Marking the buy/sell positions
for i in range(len(df)):
    if df['position'].iloc[i] == 1:
        axes[0].annotate('BUY', (df.index[i], df['low'].iloc[i]), textcoords="offset points", xytext=(0,10),
                         ha='center', color='green')
    elif df['position'].iloc[i] == -1:
        axes[0].annotate('SELL', (df.index[i], df['high'].iloc[i]), textcoords="offset points", xytext=(0,-10),
                         ha='center', color='red')

plt.show()
