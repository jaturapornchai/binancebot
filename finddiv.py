import pytz
from datetime import datetime
import requests
import matplotlib.pyplot as plt
import numpy as np

class CandleData:
    def __init__(self, time, open, high, low, close):
        self.time = time
        self.open = open
        self.high = high
        self.low = low
        self.close = close

class TradingBot:
    def __init__(self, symbols):
        self.candlestick_data = {}
        self.buy_indexes = {}
        self.symbols = symbols
        for symbol in self.symbols:
            self.fetch_data(symbol)
        self.plot_candlestick_charts()

    def fetch_data(self, symbol):
        try:
            original_data = self.get_symbol_data(symbol)
            candles_data = [
                CandleData(e['time'], e['open'], e['high'], e['low'], e['close'])
                for e in original_data
            ]
            rsi_values = self.calculate_rsi(candles_data, 14)
            buy_detected = self.detect_hammer_ll(candles_data, rsi_values)
            self.candlestick_data[symbol] = candles_data
            self.buy_indexes[symbol] = buy_detected
        except Exception as e:
            print(f'Error fetching data for {symbol}: {e}')

    def get_symbol_data(self, symbol):
        url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=100'
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return [
                {
                    'time': e[0],
                    'open': float(e[1]),
                    'high': float(e[2]),
                    'low': float(e[3]),
                    'close': float(e[4]),
                }
                for e in data
            ]
        else:
            raise Exception('Failed to load data')

    def calculate_rsi(self, data, period):
        rsi_values = []
        gains = []
        losses = []

        for i in range(1, len(data)):
            change = data[i].close - data[i - 1].close
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(-change)

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi_values.append(100 - (100 / (1 + rs)) if rs != 0 else 0)

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = avg_gain / avg_loss if avg_loss != 0 else 0
            rsi_values.append(100 - (100 / (1 + rs)) if rs != 0 else 0)

        return [50] * period + rsi_values  # Fill initial values with 50

    def detect_hammer_ll(self, data, rsi_values):
        buy_indexes = []
        min_swing_distance = 5

        for i in range(min_swing_distance, len(data) - min_swing_distance):
            is_ll = (
                data[i].low < data[i - 1].low
                and data[i].low < data[i + 1].low
                and data[i].low < data[i - min_swing_distance].low
                and data[i].low < data[i + min_swing_distance].low
            )

            is_hammer = (
                (data[i].high - data[i].low) > 1.5 * abs(data[i].open - data[i].close)
                and (data[i].close - data[i].low) / (data[i].high - data[i].low) > 0.4
                and (data[i].open - data[i].low) / (data[i].high - data[i].low) > 0.4
            )

            is_rsi_oversold = 30 < rsi_values[i] < 50

            if is_ll and is_hammer and is_rsi_oversold:
                buy_indexes.append(i)

        return buy_indexes

    def plot_candlestick_charts(self):
        for symbol in self.symbols:
            if symbol not in self.candlestick_data:
                continue

            plt.figure(figsize=(10, 5))
            dates = np.arange(len(self.candlestick_data[symbol]))
            high_prices = [c.high for c in self.candlestick_data[symbol]]
            low_prices = [c.low for c in self.candlestick_data[symbol]]
            open_prices = [c.open for c in self.candlestick_data[symbol]]
            close_prices = [c.close for c in self.candlestick_data[symbol]]

            # Plot the candlestick chart
            for i in range(len(self.candlestick_data[symbol])):
                color = 'green' if close_prices[i] > open_prices[i] else 'red'
                plt.plot([dates[i], dates[i]], [low_prices[i], high_prices[i]], color=color)
                plt.plot([dates[i] - 0.1, dates[i] + 0.1], [open_prices[i], open_prices[i]], color=color)
                plt.plot([dates[i] - 0.1, dates[i] + 0.1], [close_prices[i], close_prices[i]], color=color)

            # Plot the buy signal with label for legend and time
            for index in self.buy_indexes[symbol]:
                buy_time = self.candlestick_data[symbol][index].time
                formatted_time = self.format_time(buy_time)  # Format time as you like
                plt.scatter(dates[index], self.candlestick_data[symbol][index].low, color='blue', label=f'BUY at {formatted_time}' if index == self.buy_indexes[symbol][0] else '')

            # Set title, labels and legend
            plt.title(f'{symbol} - LL Detection with Hammer Buy Signal')
            plt.xlabel('Time')
            plt.ylabel('Price')
            plt.legend(loc='best')  # Ensure the legend is placed correctly
            plt.show()

    def format_time(self, timestamp):
        # ตั้งค่าเขตเวลาของประเทศไทย (GMT+7)
        thailand_tz = pytz.timezone('Asia/Bangkok')
        
        # แปลง timestamp เป็นเวลาตาม UTC แล้วแปลงเป็นเขตเวลาไทย
        utc_time = datetime.utcfromtimestamp(timestamp / 1000).replace(tzinfo=pytz.utc)
        thailand_time = utc_time.astimezone(thailand_tz)
        
        # แสดงเวลาในรูปแบบที่ต้องการ
        return thailand_time.strftime('%Y-%m-%d %H:%M:%S')

    def get_buy_signal(self, symbol):
        try:
            original_data = self.get_symbol_data(symbol)
            candles_data = [
                CandleData(e['time'], e['open'], e['high'], e['low'], e['close'])
                for e in original_data
            ]
            rsi_values = self.calculate_rsi(candles_data, 14)
            buy_detected = self.detect_hammer_ll(candles_data, rsi_values)
            return buy_detected
        except Exception as e:
            print(f'Error fetching data for {symbol}: {e}')
            return []

if __name__ == '__main__':
    symbols = ['ADAUSDT']  # Example symbols
    
    bot = TradingBot(symbols)
