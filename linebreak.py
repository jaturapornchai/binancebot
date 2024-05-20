from sklearn.linear_model import LinearRegression
import os
import time
import ccxt
import numpy as np
import pandas as pd
from binance.client import Client
import requests
from scipy.stats import linregress

api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"
ignore_symbols = ['DONUSDT','USDCUSDT','SRMUSDT','MOVRUSDT']
save_symbols = []
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret
})

# Connect to Binance
client = Client(api_key, api_secret)

def send_line_notify(message):
    headers = {
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)

def fetch_future_symbols():
    info = client.futures_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol'] and item['status'] == 'TRADING']
    symbols = [symbol for symbol in symbols if not any(char.isdigit() for char in symbol)]
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]
    symbols.sort()
    return symbols


def fetch_data(symbol, timeframe, limit):
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def linear_regression_channel(data, length):
    def linear_regression_slope(series):
        x = np.arange(len(series))
        slope, _ = np.polyfit(x, series, 1)
        return slope

    data['regression_slope'] = data['close'].rolling(window=length).apply(linear_regression_slope)
    data['mean'] = data['close'].rolling(window=length).mean()
    data['stddev'] = data['close'].rolling(window=length).std()
    data['upper'] = data['mean'] + 2 * data['stddev']
    data['lower'] = data['mean'] - 2 * data['stddev']
    return data

def trading_signal(data):
    last_row = data.iloc[-1]

    # ตรวจสอบเทรนด์และการเปลี่ยนแปลงของราคา
    if last_row['close'] > last_row['upper'] and last_row['regression_slope'] > 0:
        return 'long'
    elif last_row['close'] < last_row['lower'] and last_row['regression_slope'] < 0:
        return 'short'
    else:
        return "normal"

if __name__ == "__main__":
    future_symbols = [symbol for symbol in fetch_future_symbols() if '_' not in symbol and not any(char.isdigit() for char in symbol)]
    print(f'Checking {len(future_symbols)} symbols...')
    file_name = 'listcoinall.txt'
    # try delete file
    try:
        os.remove(file_name)
    except:
        pass
    # save to listcoin.txt
    with open(file_name, 'w') as f:
        for item in future_symbols:
            f.write("%s\n" % item)
    while True:
        if int(time.strftime('%M')) % 15 == 0 or 1 == 1:
            for symbol in future_symbols:
                try:        
                    timeframe = '1h'     
                    length = 100         
                    data = fetch_data(symbol, timeframe, length)
                    data = linear_regression_channel(data, length)
                    signal = trading_signal(data)
                    if signal == 'long':
                        # font blue
                        print(f'\033[94m{symbol} มีสัญญาณ Long\033[0m')
                        save_symbols.append(symbol)
                        send_line_notify(f'{symbol} มีสัญญาณ Long')
                    elif signal == 'short':
                        # font red
                        print(f'\033[91m{symbol} มีสัญญาณ Short\033[0m')                        
                        save_symbols.append(symbol)
                        send_line_notify(f'{symbol} มีสัญญาณ Short')
                    else:
                        # แสดงจุด ไม่ขึ้นบรรทัดใหม่
                        pass

                except Exception as e:
                    print(f'Error processing {symbol}: {e}')
                    future_symbols.remove(symbol)
                
            if len(save_symbols) > 0:
                print(f'มีสัญญาณทั้งหมด {len(save_symbols)} สัญญาณ')
                file_name = 'listcoin.txt'
                # try delete file
                try:
                    os.remove(file_name)
                except:
                    pass
                # save to listcoin.txt
                with open(file_name, 'w') as f:
                    for item in save_symbols:
                        f.write("%s\n" % item)
        time.sleep(10)
        if int(time.strftime('%M')) % 4 == 0:
            # กรณี position หมด ให้ส่ง line notify
            print('Check position')
            positions = client.futures_position_information()
            count = 0
            for position in positions:
                position_amount = float(position['positionAmt'])
                if position_amount != 0:
                    count += 1
            if count == 0:
                send_line_notify('Position หมดแล้ว กรุณาเช็คด่วน')
        break
                        
