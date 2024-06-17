import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from binance.client import Client

# กรอก API key และ secret ของคุณที่นี่
api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'

client = Client(api_key, api_secret)

# ดึงข้อมูล BTCUSDT จาก Binance
def get_btcusdt_1h_data():
    klines = client.get_klines(symbol='BTCUSDT', interval=Client.KLINE_INTERVAL_1HOUR)
    data = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume',
        'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
    data['close'] = data['close'].astype(float)
    return data[['timestamp', 'close']]

# ฟังก์ชันสำหรับการคำนวณ Elliott Wave เบื้องต้น
def calculate_elliott_wave(data):
    data['wave'] = np.nan  # สร้างคอลัมน์ใหม่สำหรับเก็บข้อมูลคลื่น
    wave_points = []
    wave_labels = ['1', '2', '3', '4', '5', 'a', 'b', 'c', 'x']
    label_index = 0
    
    for i in range(2, len(data) - 2):
        if label_index >= len(wave_labels):
            break
        if data['close'][i] > data['close'][i - 1] and data['close'][i] > data['close'][i + 1]:
            wave_points.append((i, wave_labels[label_index]))
            label_index += 1
        elif data['close'][i] < data['close'][i - 1] and data['close'][i] < data['close'][i + 1]:
            wave_points.append((i, wave_labels[label_index]))
            label_index += 1
    
    if wave_points:
        wave_indices, wave_types = zip(*wave_points)
        data.loc[wave_indices, 'wave'] = wave_types
    return data

# แสดงผลกราฟ
def plot_elliott_wave(data):
    plt.figure(figsize=(12, 6))
    plt.plot(data['timestamp'], data['close'], label='Close Price')
    
    peaks = data[data['wave'].isin(['1', '3', '5', 'a', 'c'])]
    troughs = data[data['wave'].isin(['2', '4', 'b', 'x'])]
    
    plt.scatter(peaks['timestamp'], peaks['close'], color='red', label='Peak')
    plt.scatter(troughs['timestamp'], troughs['close'], color='green', label='Trough')
    
    for i, txt in enumerate(data['wave'].dropna()):
        plt.annotate(txt, (data['timestamp'][i], data['close'][i]), textcoords="offset points", xytext=(0,10), ha='center')
    
    plt.xlabel('Time')
    plt.ylabel('Price')
    plt.title('BTCUSDT 1H Elliott Wave Analysis')
    plt.legend()
    plt.show()

# Main function
if __name__ == "__main__":
    data = get_btcusdt_1h_data()
    data = calculate_elliott_wave(data)
    plot_elliott_wave(data)
