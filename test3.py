import os
import ccxt
import pandas as pd
import numpy as np
import ta
import requests
from datetime import datetime

# ดึง API keys และ tokens จาก environment variables
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
line_notify_token = os.getenv('LINE_NOTIFY_TOKEN')

# เชื่อมต่อกับ Binance Futures
exchange = ccxt.binanceusdm({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

# ฟังก์ชันสำหรับส่งข้อความแจ้งเตือนผ่าน LINE Notify
def line_notify(message):
    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {line_notify_token}'}
    data = {'message': message}
    requests.post(url, headers=headers, data=data)

# ดึงข้อมูล OHLCV สำหรับ BTCUSDT ใน time frame 1 ชั่วโมง
symbol = 'BTCUSDT'
timeframe = '1h'
limit = 1000  # จำนวนแท่งเทียน 1000 แท่ง

ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

# แปลงข้อมูลเป็น DataFrame
df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
df.set_index('timestamp', inplace=True)

# คำนวณ indicators โดยใช้ ta
df['ema'] = ta.trend.ema_indicator(df['close'], window=20)
df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)

# ฟังก์ชันสำหรับระบุ wave ตามทฤษฎี Elliott Wave
def identify_elliott_waves(df):
    waves = []
    current_wave = 1
    wave_start = df.index[0]
    trend = 'up'
    prev_extreme = df['low'].iloc[0]
    
    for i in range(1, len(df)):
        if trend == 'up':
            if df['high'].iloc[i] > prev_extreme:
                prev_extreme = df['high'].iloc[i]
            elif df['low'].iloc[i] < df['low'].iloc[i-1] - df['atr'].iloc[i]:
                waves.append((wave_start, df.index[i-1], f"Wave {current_wave}"))
                wave_start = df.index[i]
                current_wave += 1
                if current_wave > 5:
                    trend = 'down'
                    current_wave = 'A'
                prev_extreme = df['low'].iloc[i]
        else:  # trend == 'down'
            if df['low'].iloc[i] < prev_extreme:
                prev_extreme = df['low'].iloc[i]
            elif df['high'].iloc[i] > df['high'].iloc[i-1] + df['atr'].iloc[i]:
                waves.append((wave_start, df.index[i-1], f"Wave {current_wave}"))
                wave_start = df.index[i]
                if current_wave == 'A':
                    current_wave = 'B'
                elif current_wave == 'B':
                    current_wave = 'C'
                else:  # current_wave == 'C'
                    trend = 'up'
                    current_wave = 1
                prev_extreme = df['high'].iloc[i]
    
    # เพิ่ม wave ปัจจุบัน
    waves.append((wave_start, df.index[-1], f"Current Wave {current_wave}"))
    
    return waves, current_wave, trend

# ระบุ waves
waves, current_wave, current_trend = identify_elliott_waves(df)

# สร้างข้อความสรุป
current_price = df['close'].iloc[-1]
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

summary = f"BTCUSDT Elliott Wave Analysis (1h timeframe, last 1000 candles)\n\n"
summary += f"Current Time: {current_time}\n"
summary += f"Current Price: {current_price:.2f}\n"
summary += f"Current Wave: {current_wave}\n"
summary += f"Current Trend: {current_trend.capitalize()}\n\n"

# แสดงเฉพาะ 5 waves ล่าสุด
summary += "Last 5 completed waves:\n"
for start, end, wave in waves[-6:-1]:  # -6:-1 เพื่อแสดง 5 waves ล่าสุดที่สมบูรณ์
    summary += f"{wave}: from {start} to {end}\n"

summary += f"\nTotal waves: {len(waves)}"

# แสดงผลลัพธ์และส่งแจ้งเตือนผ่าน LINE
print(summary)
line_notify(summary)