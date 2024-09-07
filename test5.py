import ccxt
import pandas as pd
import matplotlib.pyplot as plt

# สร้าง instance ของ Binance
exchange = ccxt.binance()

# ดึงข้อมูล OHLCV (Open, High, Low, Close, Volume) สำหรับ BTC/USDT ใน Time Frame 1 ชั่วโมง
symbol = 'BTC/USDT'
timeframe = '1h'
limit = 1000  # ดึงข้อมูล 1000 แท่งล่าสุด

ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

# แปลงข้อมูลเป็น DataFrame
df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

# หาคลื่นแรก (Wave 1)
def find_first_wave(df):
    min_index = df['close'].idxmin()  # หาจุดต่ำสุด
    first_wave_end = df['close'].iloc[min_index:].idxmax()  # หาจุดสูงสุดหลังจากจุดต่ำสุด
    return min_index, first_wave_end

min_index, first_wave_end = find_first_wave(df)

# สร้างกราฟแสดงคลื่นแรก
plt.figure(figsize=(14, 8))
plt.plot(df['timestamp'], df['close'], label='BTC/USDT Price')

# แสดงตำแหน่งของคลื่นแรกบนกราฟ
plt.annotate('Wave 1 Start', xy=(df['timestamp'].iloc[min_index], df['close'].iloc[min_index]), 
             xytext=(10, 30), textcoords='offset points', 
             arrowprops=dict(facecolor='black', shrink=0.05),
             horizontalalignment='right', verticalalignment='bottom')

plt.annotate('Wave 1 End', xy=(df['timestamp'].iloc[first_wave_end], df['close'].iloc[first_wave_end]), 
             xytext=(10, 30), textcoords='offset points', 
             arrowprops=dict(facecolor='black', shrink=0.05),
             horizontalalignment='right', verticalalignment='bottom')

plt.title('BTC/USDT Price with First Wave Identification')
plt.xlabel('Date')
plt.ylabel('Price')
plt.legend()
plt.grid(True)
plt.show()
