import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

class ElliottWaveOscillator:
    def __init__(self, sma1_length=5, sma2_length=35, use_percent=True):
        self.sma1_length = sma1_length
        self.sma2_length = sma2_length
        self.use_percent = use_percent

    def get_binance_klines(self, symbol, interval, limit):
        """ดึงข้อมูลจาก Binance"""
        endpoint = "https://api.binance.com/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        response = requests.get(endpoint, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error fetching data: {response.status_code}")

    def calculate_sma(self, prices, period):
        """คำนวณ Simple Moving Average"""
        return pd.Series(prices).rolling(window=period).mean()

    def calculate_ewo(self, df):
        """คำนวณ Elliott Wave Oscillator"""
        src = df['close'].values
        sma1 = self.calculate_sma(src, self.sma1_length)
        sma2 = self.calculate_sma(src, self.sma2_length)
        
        if self.use_percent:
            ewo = (sma1 - sma2) / src * 100
        else:
            ewo = sma1 - sma2
            
        return ewo

    def find_signals(self, df):
        """หาสัญญาณซื้อขายจากการเปลี่ยนสี"""
        ewo = self.calculate_ewo(df)
        df['ewo'] = ewo
        
        buy_signals = []
        sell_signals = []
        
        # หาจุดตัด 0 (เปลี่ยนสี)
        for i in range(1, len(df)):
            # Buy signal: เปลี่ยนจากแดงเป็นเขียว (ตัดขึ้นผ่าน 0)
            if df['ewo'].iloc[i-1] <= 0 and df['ewo'].iloc[i] > 0:
                buy_signals.append({
                    'index': i,
                    'price': df['close'].iloc[i],
                    'ewo': df['ewo'].iloc[i]
                })
            
            # Sell signal: เปลี่ยนจากเขียวเป็นแดง (ตัดลงผ่าน 0)
            elif df['ewo'].iloc[i-1] > 0 and df['ewo'].iloc[i] <= 0:
                sell_signals.append({
                    'index': i,
                    'price': df['close'].iloc[i],
                    'ewo': df['ewo'].iloc[i]
                })
        
        return {'buy': buy_signals, 'sell': sell_signals}

    def plot_analysis(self, df, signals):
        """วาดกราฟแสดงผลการวิเคราะห์"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
        
        # Plot 1: Price and Signal Points
        ax1.plot(df.index, df['close'], label='Price', color='blue', alpha=0.7)
        
        # Plot Buy Signals (เปลี่ยนจากแดงเป็นเขียว)
        for signal in signals['buy']:
            idx = df.index[signal['index']]
            ax1.plot(idx, signal['price'], '^', markersize=10, color='g')
            signal_text = f"BUY\nPrice: {signal['price']:.2f}\nEWO: {signal['ewo']:.2f}"
            ax1.annotate(signal_text,
                        (idx, signal['price']),
                        xytext=(10, 10),
                        textcoords='offset points',
                        bbox=dict(facecolor='lightgreen', alpha=0.7))
        
        # Plot Sell Signals (เปลี่ยนจากเขียวเป็นแดง)
        for signal in signals['sell']:
            idx = df.index[signal['index']]
            ax1.plot(idx, signal['price'], 'v', markersize=10, color='r')
            signal_text = f"SELL\nPrice: {signal['price']:.2f}\nEWO: {signal['ewo']:.2f}"
            ax1.annotate(signal_text,
                        (idx, signal['price']),
                        xytext=(10, -10),
                        textcoords='offset points',
                        bbox=dict(facecolor='lightcoral', alpha=0.7))
        
        ax1.set_title('Price Chart with Buy/Sell Signals')
        ax1.grid(True)
        
        # Plot 2: Elliott Wave Oscillator
        colors = ['g' if x > 0 else 'r' for x in df['ewo']]
        ax2.bar(df.index, df['ewo'], color=colors, alpha=0.7)
        ax2.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        
        # เพิ่มจุดที่เกิดสัญญาณใน EWO
        for signal in signals['buy']:
            idx = df.index[signal['index']]
            ax2.plot(idx, signal['ewo'], '^', color='g', markersize=8)
        for signal in signals['sell']:
            idx = df.index[signal['index']]
            ax2.plot(idx, signal['ewo'], 'v', color='r', markersize=8)
        
        ax2.set_title('Elliott Wave Oscillator')
        ax2.grid(True)
        
        plt.tight_layout()
        plt.show()

def main():
    # ตั้งค่าพารามิเตอร์
    symbol = "BTCUSDT"
    interval = "1h"
    limit = 500
    sma1_length = 5
    sma2_length = 35
    use_percent = True

    # สร้าง ElliottWaveOscillator object
    ewo = ElliottWaveOscillator(sma1_length, sma2_length, use_percent)
    
    # ดึงข้อมูลจาก Binance
    klines = ewo.get_binance_klines(symbol, interval, limit)
    
    # แปลงข้อมูลเป็น DataFrame
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                     'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                                     'taker_buy_quote', 'ignored'])
    
    # แปลงข้อมูลให้เป็นรูปแบบที่ใช้งานได้
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    # ตั้ง timestamp เป็น index
    df.set_index('timestamp', inplace=True)
    
    # หาสัญญาณซื้อขาย
    signals = ewo.find_signals(df)
    
    # วาดกราฟ
    ewo.plot_analysis(df, signals)
    
    # แสดงสัญญาณล่าสุด
    print("\nLatest Signals (Last 24 hours):")
    latest_index = df.index[-1]
    last_24h = latest_index - pd.Timedelta(hours=24)
    
    # แสดงสัญญาณ Buy
    recent_buys = [s for s in signals['buy'] 
                   if df.index[s['index']] > last_24h]
    if recent_buys:
        print("\nBUY Signals (เปลี่ยนจากแดงเป็นเขียว):")
        for signal in recent_buys:
            print(f"\nTime: {df.index[signal['index']]}")
            print(f"Price: {signal['price']:.2f}")
            print(f"EWO: {signal['ewo']:.2f}")
    
    # แสดงสัญญาณ Sell
    recent_sells = [s for s in signals['sell'] 
                    if df.index[s['index']] > last_24h]
    if recent_sells:
        print("\nSELL Signals (เปลี่ยนจากเขียวเป็นแดง):")
        for signal in recent_sells:
            print(f"\nTime: {df.index[signal['index']]}")
            print(f"Price: {signal['price']:.2f}")
            print(f"EWO: {signal['ewo']:.2f}")
    
    if not recent_buys and not recent_sells:
        print("No signals in the last 24 hours")

if __name__ == "__main__":
    main()