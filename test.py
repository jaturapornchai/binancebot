import ccxt
import pandas as pd
import numpy as np

# ตั้งค่า API key และ secret
api_key = 'c64a07643c277d2dbd07892bd9804425'
api_secret = '4ef7ba483b69ffcb9735e1e28ec41799ef85950e5b48783ccc47f2e21336f9a5'

# สร้าง client ของ Gate.io
exchange = ccxt.gateio({
    'apiKey': api_key,
    'secret': api_secret
})

def check_ema_cross(symbol):
    try:
        # ดึงข้อมูลในกรอบเวลา 1 ชั่วโมง
        timeframe = '1h'
        limit = 500

        # ดึงข้อมูลแท่งเทียน (ohlcv)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

        # สร้าง DataFrame จากข้อมูลแท่งเทียน
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # แปลง timestamp เป็นวันที่และเวลาในเวลาโลก (UTC)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # คำนวณ EMA 200
        df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()

        # หาจุดตัดของราคาและ EMA 200
        cross_up = df[(df['close'].shift(1) < df['EMA200'].shift(1)) & (df['close'] > df['EMA200'])]
        cross_down = df[(df['close'].shift(1) > df['EMA200'].shift(1)) & (df['close'] < df['EMA200'])]

        # ตรวจหาจุดตัดล่าสุด
        if not cross_up.empty and cross_up['timestamp'].iloc[-1] == df['timestamp'].iloc[-1]:
            return "Up"
        elif not cross_down.empty and cross_down['timestamp'].iloc[-1] == df['timestamp'].iloc[-1]:
            return "Down"
        else:
            return None
    except Exception as e:
        return f"Error: {e}"

# ตัวอย่างการเรียกใช้ฟังก์ชัน
symbol = 'BTC/USDT'
result = check_ema_cross(symbol)
print(f"The latest cross for {symbol} is: {result}")
