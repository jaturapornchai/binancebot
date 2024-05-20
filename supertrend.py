from sklearn.linear_model import LinearRegression
import os
import time
import ccxt
from binance.client import Client
import requests
from scipy.stats import linregress
import numpy as np
import pandas as pd
from binance.enums import *

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


def heikin_ashi(df):
    df['HA_Close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    ha_open = [(df['open'][0] + df['close'][0]) / 2]
    for i in range(1, len(df)):
        ha_open.append((ha_open[i-1] + df['HA_Close'].iloc[i-1]) / 2)
    df['HA_Open'] = ha_open
    df['HA_High'] = df[['HA_Open', 'HA_Close', 'high']].max(axis=1)
    df['HA_Low'] = df[['HA_Open', 'HA_Close', 'low']].min(axis=1)
    return df

def atr(df, period=14):
    df['H-L'] = abs(df['high'] - df['low'])
    df['H-PC'] = abs(df['high'] - df['close'].shift(1))
    df['L-PC'] = abs(df['low'] - df['close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(period).mean()
    return df

def supertrend(df, atr_period=7, multiplier=3.0):
    atr(df, atr_period)
    df['Upperband'] = ((df['HA_High'] + df['HA_Low']) / 2) + (multiplier * df['ATR'])
    df['Lowerband'] = ((df['HA_High'] + df['HA_Low']) / 2) - (multiplier * df['ATR'])
    df['In_Uptrend'] = True

    for current in range(1, len(df.index)):
        previous = current - 1

        if df['HA_Close'][current] > df['Upperband'][previous]:
            df.loc[current, 'In_Uptrend'] = True
        elif df['HA_Close'][current] < df['Lowerband'][previous]:
            df.loc[current, 'In_Uptrend'] = False
        else:
            df.loc[current, 'In_Uptrend'] = df['In_Uptrend'][previous]

            if df['In_Uptrend'][current]:
                if df['Lowerband'][current] < df['Lowerband'][previous]:
                    df.loc[current, 'Lowerband'] = df['Lowerband'][previous]

            if not df['In_Uptrend'][current]:
                if df['Upperband'][current] > df['Upperband'][previous]:
                    df.loc[current, 'Upperband'] = df['Upperband'][previous]

    return df

def fetch_data(symbol):
    candles = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE)
    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['open'] = pd.to_numeric(df['open'])
    df['high'] = pd.to_numeric(df['high'])
    df['low'] = pd.to_numeric(df['low'])
    df['close'] = pd.to_numeric(df['close'])
    df['volume'] = pd.to_numeric(df['volume'])
    return df

def get_signal(symbol):
    df = fetch_data(symbol)
    df = heikin_ashi(df)
    df = supertrend(df)

    df['Trend_Change'] = df['In_Uptrend'].ne(df['In_Uptrend'].shift())
    df['Signal'] = 'normal'
    df.loc[df['Trend_Change'] & df['In_Uptrend'], 'Signal'] = 'long'
    df.loc[df['Trend_Change'] & ~df['In_Uptrend'], 'Signal'] = 'short'

    # Return the signal of the last row
    return df.iloc[-1]['Signal']

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
            save_symbols = []
            for symbol in future_symbols:
                try:        
                    signal = get_signal(symbol)
                    print(f'{symbol} {signal}')
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
        
                        
