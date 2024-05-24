import ccxt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ตั้งค่า API key และ secret
api_key = 'c64a07643c277d2dbd07892bd9804425'
api_secret = '4ef7ba483b69ffcb9735e1e28ec41799ef85950e5b48783ccc47f2e21336f9a5'

# สร้าง client ของ Gate.io
exchange = ccxt.gateio({
    'apiKey': api_key,
    'secret': api_secret
})

def fetch_usdt_volume_symbols(exchange, timeframe='1h', limit=145):
    markets = exchange.load_markets()
    usdt_symbols = [symbol for symbol in markets if symbol.endswith('/USDT')]

    high_volume_symbols = []

    for symbol in usdt_symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if len(ohlcv) < 45:
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            current_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].iloc[:-1].tail(144).mean()

            if current_volume > avg_volume * 5:
                print(f"Symbol: {symbol}, Current Volume: {current_volume}, Average Volume: {avg_volume}")
                high_volume_symbols.append({
                    'symbol': symbol,
                    'current_volume': current_volume,
                    'average_volume': avg_volume
                })
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")

    return high_volume_symbols

# เรียกใช้งานฟังก์ชัน
result = fetch_usdt_volume_symbols(exchange)
result
