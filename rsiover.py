import pandas as pd
from binance.client import Client
import os
import time
import ccxt
import numpy as np
import pandas as pd
from binance.client import Client
import requests
import pandas as pd
from binance.client import Client
from binance.enums import *
import numpy as np

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


def get_rsi_signal(symbol="BTCUSDT", interval='1h', oversold=25, overbought=75, periods=14):
    # Fetch historical data
    candles = client.get_historical_klines(symbol, interval, "1 day ago UTC")

    # Prepare DataFrame
    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['close'] = pd.to_numeric(df['close'])

    # RSI Calculation
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(window=periods).mean()
    ma_down = down.rolling(window=periods).mean()
    rs = ma_up / ma_down
    rsi = 100 - (100 / (1 + rs))
    df['RSI'] = rsi

    # Determine the trading signal
    last_rsi = df['RSI'].iloc[-1]
    if last_rsi > overbought:
        return "short"
    elif last_rsi < oversold:
        return "long"
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
        if int(time.strftime('%M')) == 0:
            for symbol in future_symbols:
                try:        
                    #time.sleep(60)
                    signal =  get_rsi_signal(symbol, '1h', 25, 75, 14)
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
        time.sleep(30)
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
                        
