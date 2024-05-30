import ccxt
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ตั้งค่า API key และ secret
api_key = 'c64a07643c277d2dbd07892bd9804425'
api_secret = '4ef7ba483b69ffcb9735e1e28ec41799ef85950e5b48783ccc47f2e21336f9a5'

# สร้าง client ของ Gate.io
exchange = ccxt.gateio({
    'apiKey': api_key,
    'secret': api_secret
})

# ดึงข้อมูล BTCUSDT time frame 1 ชม.
symbol = 'BTC/USDT'
timeframe = '1h'

# กำหนดช่วงเวลาให้ไม่เกินขีดจำกัดของ API
limit = 1000  # จำนวนแท่งข้อมูลที่ดึงต่อครั้ง
since = exchange.milliseconds() - 1000 * 60 * 60 * 24 * 30  # ดึงข้อมูลย้อนหลัง 30 วัน

# ดึงข้อมูลในช่วงเวลาที่กำหนด
bars = []
while True:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, limit)
    if not ohlcv:
        break
    since = ohlcv[-1][0] + 1
    bars.extend(ohlcv)
    if len(ohlcv) < limit:
        break

data = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
data.set_index('timestamp', inplace=True)

# ฟังก์ชันคำนวณ RSI
def rsi(df, periods=14, ema=True):
    close_delta = df['close'].diff()
    
    if ema:
        up = close_delta.clip(lower=0)
        down = -1 * close_delta.clip(upper=0)
        ma_up = up.ewm(com=periods-1, adjust=True, min_periods=periods).mean()
        ma_down = down.ewm(com=periods-1, adjust=True, min_periods=periods).mean()
    else:
        up = close_delta[close_delta > 0].reindex_like(df)
        down = -1 * close_delta[close_delta < 0].reindex_like(df)
        ma_up = up.rolling(window=periods, min_periods=0).mean()
        ma_down = down.rolling(window=periods, min_periods=0).mean()
    
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

# เพิ่มคอลัมน์ RSI ลงใน dataframe
data['rsi'] = rsi(data, periods=14)

# ฟังก์ชันหา swing high และ swing low
def find_swing_points(data, rsi_col='rsi', lb=5):
    swing_highs = []
    swing_lows = []
    
    for i in range(lb, len(data) - lb):
        if data[rsi_col].iloc[i] == max(data[rsi_col].iloc[i - lb:i + lb + 1]):
            swing_highs.append((data.index[i], data[rsi_col].iloc[i]))
        if data[rsi_col].iloc[i] == min(data[rsi_col].iloc[i - lb:i + lb + 1]):
            swing_lows.append((data.index[i], data[rsi_col].iloc[i]))
    
    return swing_highs, swing_lows

# หา swing points
swing_highs, swing_lows = find_swing_points(data)

# ฟังก์ชันหา divergence
def find_divergence(data, swing_highs, swing_lows, lbR=5):
    divergences = {'bullish': [], 'bearish': []}
    
    for i in range(1, len(swing_lows)):
        if swing_lows[i][1] > swing_lows[i - 1][1] and data['close'][swing_lows[i][0]] < data['close'][swing_lows[i - 1][0]]:
            divergences['bullish'].append(swing_lows[i])
    
    for i in range(1, len(swing_highs)):
        if swing_highs[i][1] < swing_highs[i - 1][1] and data['close'][swing_highs[i][0]] > data['close'][swing_highs[i - 1][0]]:
            divergences['bearish'].append(swing_highs[i])
    
    return divergences

# หา divergence
divergences = find_divergence(data, swing_highs, swing_lows)

# สร้างกราฟ
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

# กราฟราคา
ax1.plot(data.index, data['close'], label='Price', color='black')
ax1.set_title('BOSON/USDT Price')
ax1.set_ylabel('Price')
ax1.legend()

# กราฟ RSI พร้อมเส้น divergence
ax2.plot(data.index, data['rsi'], label='RSI', color='blue')
ax2.axhline(70, linestyle='--', alpha=0.5, color='red')
ax2.axhline(30, linestyle='--', alpha=0.5, color='green')

for point in divergences['bullish']:
    ax2.annotate('Bullish Divergence', xy=(point[0], point[1]), xytext=(point[0], point[1]+5), 
                 arrowprops=dict(facecolor='green', shrink=0.05), fontsize=12, color='green')
    ax1.annotate('Buy', xy=(point[0], data['close'][point[0]]), xytext=(point[0], data['close'][point[0]]+500),
                 arrowprops=dict(facecolor='green', shrink=0.05), fontsize=12, color='green')

for point in divergences['bearish']:
    ax2.annotate('Bearish Divergence', xy=(point[0], point[1]), xytext=(point[0], point[1]-5), 
                 arrowprops=dict(facecolor='red', shrink=0.05), fontsize=12, color='red')

ax2.set_title('RSI with Divergence')
ax2.set_ylabel('RSI')
ax2.legend()

plt.show()
