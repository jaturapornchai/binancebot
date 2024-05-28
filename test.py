import ccxt
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

# ตั้งค่า API key และ secret
api_key = 'c64a07643c277d2dbd07892bd9804425'
api_secret = '4ef7ba483b69ffcb9735e1e28ec41799ef85950e5b48783ccc47f2e21336f9a5'

# สร้าง client ของ Gate.io
exchange = ccxt.gateio({
    'apiKey': api_key,
    'secret': api_secret
})

def fetch_ohlcv(symbol, timeframe='1h', limit=100):
    """
    ดึงข้อมูล OHLCV จาก Gate.io
    """
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def linear_regression_channel(df):
    """
    สร้าง Linear Regression Channel จากข้อมูลราคา
    """
    X = np.arange(len(df)).reshape(-1, 1)
    y = df['close'].values

    model = LinearRegression().fit(X, y)
    trend = model.predict(X)

    residuals = y - trend
    std_dev = np.std(residuals)

    upper_channel = trend + 2 * std_dev
    lower_channel = trend - 2 * std_dev

    df['upper_channel'] = upper_channel
    df['lower_channel'] = lower_channel
    df['trend'] = trend
    
    return df

def check_price_breakout(symbol):
    """
    ตรวจสอบสถานะราคาว่าตัดขึ้นหรือลงจาก Linear Regression Channel หรือไม่
    """
    df = fetch_ohlcv(symbol)
    df = linear_regression_channel(df)
    
    if df['close'].iloc[-1] > df['upper_channel'].iloc[-1]:
        return True
    return False

if __name__ == '__main__':
    markets = exchange.load_markets()
    order_symbols = []
    for symbol in markets:
        if symbol.endswith('/USDT'):
            order_symbols.append(symbol)
    # ลบ 3S และ 3L , 5S และ 5L
    order_symbols = [symbol for symbol in order_symbols if '3S' not in symbol and '3L' not in symbol and '5S' not in symbol and '5L' not in symbol]
    # remove USDC
    order_symbols = [symbol for symbol in order_symbols if 'USDC' not in symbol]
    print("Order buy low")
    for symbol in order_symbols:
        try:
            result = check_price_breakout(symbol)
            if result != "ปรกติ":
                print(symbol, result)
        except Exception as e:
            print(e)
