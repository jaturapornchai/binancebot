import pytz
from datetime import datetime
from gate_api import ApiClient, Configuration, SpotApi
import time

API_KEY = "c84d3616806f44e5651912c198094a1b"
API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"
INVALID_PAIRS = ['DILI_USDT', 'POINT_USDT', 'CATCH_OLD_USDT', 'ROOST_OLD_USDT']

class CandleData:
    def __init__(self, time, open, high, low, close):
        self.time = time
        self.open = float(open)
        self.high = float(high)
        self.low = float(low)
        self.close = float(close)

class TradingBot:
    def __init__(self ):
        # Initialize Gate.io API client
        config = Configuration(key=API_KEY, secret=API_SECRET)
        self.client = ApiClient(config)
        self.spot_api = SpotApi(self.client)
        
        self.candlestick_data = {}
        self.buy_indexes = {}
        self.symbols = self.get_spot_pairs()
        
        for symbol in self.symbols:
            self.check_signals(symbol.id)

    def is_valid_pair(self, pair_id): return False if '_OLD' in pair_id or pair_id in INVALID_PAIRS else True
    def get_spot_pairs(self):
        try:
            pairs = [pair for pair in self.spot_api.list_currency_pairs() if pair.id.count('_USDT') == 1 and self.is_valid_pair(pair.id)]
            tickers = self.spot_api.list_tickers()
            volume_dict = {t.currency_pair: float(t.quote_volume) for t in tickers if t.currency_pair.count('_USDT') == 1 and self.is_valid_pair(t.currency_pair)}
            filtered_pairs = [pair for pair in pairs if pair.id in volume_dict and volume_dict[pair.id] >= 100_000]
            for pair in filtered_pairs: pair.volume_24h = volume_dict[pair.id]
            return sorted(filtered_pairs, key=lambda x: x.volume_24h, reverse=True)
        except Exception as e: print(f"Error getting pairs: {e}", flush=True); return []

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
                for idx in buy_detected:
                    candle = candles_data[idx]
                    current_time = time.time()
                    time_diff_minutes = (current_time - candle.time) / 60
                    if time_diff_minutes < 120:
                        print(f"\n{'='*20} {symbol} Buy Signals {'='*20}", flush=True)
                        print(f"Signal Time: {self.format_time(candle.time)} ({time_diff_minutes:.1f} minutes ago)", flush=True)
                        print(f"Price: {candle.close:.6f}", flush=True)
                        print(f"RSI: {rsi_values[idx]:.2f}", flush=True)
                        print("-" * 50, flush=True)
                        return True
                
        except Exception as e:
            print(f'Error analyzing {symbol}: {e}', flush=True)
        
        return False

    def get_symbol_data(self, symbol):
        try:
            candlesticks = self.spot_api.list_candlesticks(
                currency_pair=symbol,
                interval='15m',  # 15-minute intervals
                limit=100
            )
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

if __name__ == '__main__':
    print("Starting trading bot...", flush=True)
    bot = TradingBot()
    print("Trading bot started!", flush=True)
