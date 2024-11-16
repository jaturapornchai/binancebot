import pytz
from datetime import datetime
from gate_api import ApiClient, Configuration, SpotApi
import time

API_KEY = "c84d3616806f44e5651912c198094a1b"
API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"

class CandleData:
    def __init__(self, time, open, high, low, close):
        self.time = time
        self.open = float(open)
        self.high = float(high)
        self.low = float(low)
        self.close = float(close)

class TradingBot:
    def __init__(self, symbols):
        # Initialize Gate.io API client
        config = Configuration(key=API_KEY, secret=API_SECRET)
        self.client = ApiClient(config)
        self.spot_api = SpotApi(self.client)
        
        self.candlestick_data = {}
        self.buy_indexes = {}
        self.symbols = symbols
        print("Starting trading bot...", flush=True)
        print(f"Monitoring symbols: {', '.join(symbols)}", flush=True)
        print("-" * 50, flush=True)
        
        for symbol in self.symbols:
            self.check_signals(symbol)

    def check_signals(self, symbol):
        try:
            original_data = self.get_symbol_data(symbol)
            candles_data = [
                CandleData(
                    int(e[0]),  # timestamp
                    float(e[5]),  # open
                    float(e[3]),  # high
                    float(e[4]),  # low
                    float(e[2])   # close
                )
                for e in original_data
            ]
            rsi_values = self.calculate_rsi(candles_data, 14)
            buy_detected = self.detect_hammer_ll(candles_data, rsi_values)
            
            if buy_detected:
                print(f"\n{'='*20} {symbol} Buy Signals {'='*20}", flush=True)
                for idx in buy_detected:
                    candle = candles_data[idx]
                    current_time = time.time()
                    time_diff_minutes = (current_time - candle.time) / 60
                    
                    print(f"Signal Time: {self.format_time(candle.time)} ({time_diff_minutes:.1f} minutes ago)", flush=True)
                    print(f"Price: {candle.close:.6f}", flush=True)
                    print(f"RSI: {rsi_values[idx]:.2f}", flush=True)
                    print("-" * 50, flush=True)
            else:
                print(f"No buy signals found for {symbol}", flush=True)
                
        except Exception as e:
            print(f'Error analyzing {symbol}: {e}', flush=True)

    def get_symbol_data(self, symbol):
        try:
            candlesticks = self.spot_api.list_candlesticks(
                currency_pair=symbol,
                interval='15m',  # 15-minute intervals
                limit=100
            )
            print(f"Retrieved {len(candlesticks)} candlesticks for {symbol}", flush=True)
            return candlesticks
        except Exception as e:
            raise Exception(f'Failed to load data: {e}')

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

        if len(gains) < period:
            return [50] * len(data)

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi_values.append(100 - (100 / (1 + rs)) if rs != 0 else 0)

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = avg_gain / avg_loss if avg_loss != 0 else 0
            rsi_values.append(100 - (100 / (1 + rs)) if rs != 0 else 0)

        return [50] * period + rsi_values

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

    def format_time(self, timestamp):
        thailand_tz = pytz.timezone('Asia/Bangkok')
        utc_time = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.utc)
        thailand_time = utc_time.astimezone(thailand_tz)
        return thailand_time.strftime('%Y-%m-%d %H:%M:%S')

    def monitor_signals(self, interval_seconds=60):
        """
        Continuously monitor for new buy signals
        """
        print(f"\nStarting continuous monitoring...", flush=True)
        print(f"Checking every {interval_seconds} seconds", flush=True)
        print("Press Ctrl+C to stop", flush=True)
        print("-" * 50, flush=True)
        
        while True:
            try:
                current_time = self.format_time(int(time.time()))
                print(f"\nChecking signals at {current_time}", flush=True)
                
                for symbol in self.symbols:
                    self.check_signals(symbol)
                
                print(f"\nNext check in {interval_seconds} seconds...", flush=True)
                time.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                print("\nMonitoring stopped by user", flush=True)
                break
            except Exception as e:
                print(f"Error during monitoring: {e}", flush=True)
                print(f"Retrying in {interval_seconds} seconds...", flush=True)
                time.sleep(interval_seconds)

if __name__ == '__main__':
    # Gate.io uses underscore format for trading pairs
    symbols = ['BTC_USDT', 'ETH_USDT', 'XRP_USDT', 'LTC_USDT', 'ADA_USDT']
    
    bot = TradingBot(symbols)
    bot.monitor_signals(interval_seconds=60)  # Check every minute