import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone

# ตั้งค่า API key และ secret
api_key = 'c64a07643c277d2dbd07892bd9804425'
api_secret = '4ef7ba483b69ffcb9735e1e28ec41799ef85950e5b48783ccc47f2e21336f9a5'

# สร้าง client ของ Gate.io
exchange = ccxt.gateio({
    'apiKey': api_key,
    'secret': api_secret
})

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

def find_swing_points(data, rsi_col='rsi', lb=5):
    swing_highs = []
    swing_lows = []
    
    for i in range(lb, len(data) - lb):
        if data[rsi_col].iloc[i] == max(data[rsi_col].iloc[i - lb:i + lb + 1]):
            swing_highs.append((data.index[i], data[rsi_col].iloc[i]))
        if data[rsi_col].iloc[i] == min(data[rsi_col].iloc[i - lb:i + lb + 1]):
            swing_lows.append((data.index[i], data[rsi_col].iloc[i]))
    
    return swing_highs, swing_lows

def find_divergence(data, swing_highs, swing_lows):
    divergences = {'bullish': [], 'bearish': []}
    
    for i in range(1, len(swing_lows)):
        if swing_lows[i][1] > swing_lows[i - 1][1] and data['close'][swing_lows[i][0]] < data['close'][swing_lows[i - 1][0]]:
            divergences['bullish'].append(swing_lows[i])
    
    for i in range(1, len(swing_highs)):
        if swing_highs[i][1] < swing_highs[i - 1][1] and data['close'][swing_highs[i][0]] > data['close'][swing_highs[i - 1][0]]:
            divergences['bearish'].append(swing_highs[i])
    
    return divergences

def check_buy_div_signal(symbol):
    timeframe = '1h'
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

    data['rsi'] = rsi(data, periods=14)
    swing_highs, swing_lows = find_swing_points(data)
    divergences = find_divergence(data, swing_highs, swing_lows)

    if divergences['bullish']:
        latest_divergence = divergences['bullish'][-1][0]
        time_since_divergence = (data.index[-1] - latest_divergence) // pd.Timedelta(minutes=60)
        if time_since_divergence <= 12:
            print(f"Symbol: {symbol} - Latest bullish divergence detected at {latest_divergence}, {time_since_divergence} time frames ago.")
            return True
    return False

def main():
    markets = exchange.load_markets()
    order_symbols = []
    for symbol in markets:
        if symbol.endswith('/USDT'):
            order_symbols.append(symbol)
    # ลบ 3S และ 3L , 5S และ 5L
    order_symbols = [symbol for symbol in order_symbols if '3S' not in symbol and '3L' not in symbol and '5S' not in symbol and '5L' not in symbol]
    # remove USDC
    order_symbols = [symbol for symbol in order_symbols if 'USDC' not in symbol]
    # random
    np.random.shuffle(order_symbols)
    for symbol in order_symbols:
        buy_signal = check_buy_div_signal(symbol)
        if buy_signal:
            print(f"Symbol: {symbol} - Buy signal detected.")

if __name__ == "__main__":
    main()
