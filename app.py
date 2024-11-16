import time, pandas as pd, numpy as np
from dataclasses import dataclass
from typing import List
from gate_api import ApiClient, Configuration, SpotApi, Order
API_KEY = "c84d3616806f44e5651912c198094a1b"
API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"
INVALID_PAIRS = ['DILI_USDT', 'POINT_USDT', 'CATCH_OLD_USDT', 'ROOST_OLD_USDT']
@dataclass
class BlockEvent:
    timestamp: float
    price: float
    type: str
    strength: float
class GateioScanner:
    def __init__(self):
        self.config = Configuration(key=API_KEY, secret=API_SECRET, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(self.config)
        self.spot_api = SpotApi(self.client)
    def is_valid_pair(self, pair_id): return False if '_OLD' in pair_id or pair_id in INVALID_PAIRS else True
    def get_spot_pairs(self):
        try:
            pairs = [pair for pair in self.spot_api.list_currency_pairs() if pair.id.count('_USDT') == 1 and self.is_valid_pair(pair.id)]
            tickers = self.spot_api.list_tickers()
            volume_dict = {t.currency_pair: float(t.quote_volume) for t in tickers if t.currency_pair.count('_USDT') == 1 and self.is_valid_pair(t.currency_pair)}
            filtered_pairs = [pair for pair in pairs if pair.id in volume_dict and volume_dict[pair.id] >= 50_000]
            for pair in filtered_pairs: pair.volume_24h = volume_dict[pair.id]
            return sorted(filtered_pairs, key=lambda x: x.volume_24h, reverse=True)
        except Exception as e: print(f"Error getting pairs: {e}", flush=True); return []
    def get_klines(self, pair, limit=144):
        try: return self.spot_api.list_candlesticks(currency_pair=pair, interval='1h', limit=limit) if self.is_valid_pair(pair) else None
        except Exception as e: print(f"Error getting klines for {pair}: {e}", flush=True); return None
    def safe_float_convert(self, value):
        try: return float(value) if isinstance(value, (int, float)) else float(''.join(c for c in value if c.isdigit() or c in '.-')) if isinstance(value, str) and ''.join(c for c in value if c.isdigit() or c in '.-') else 0.0
        except: return 0.0
    def get_spot_price(self, pair: str) -> float:
        try: return float(self.spot_api.list_tickers(currency_pair=pair)[0].last) if self.is_valid_pair(pair) else 0.0
        except Exception as e: print(f"Error getting price for {pair}: {e}", flush=True); return 0.0
    def get_account_balance(self, symbol: str) -> float:
        try: return next((float(b.available) for b in self.spot_api.list_spot_accounts() if b.currency.lower() == symbol.lower()), 0.0)
        except Exception as e: print(f"Error getting balance: {str(e)}", flush=True); return 0.0
    def place_market_buy(self, pair: str, amount_usdt: float = 20):
        try: return self.spot_api.create_order(Order(currency_pair=pair, side='buy', amount=str(amount_usdt), type='market', time_in_force='ioc')) if self.is_valid_pair(pair) else False
        except Exception as e: print(f"Error placing buy order: {str(e)}", flush=True); return False
    def place_market_sell(self, pair: str, amount: float):
        try: return self.spot_api.create_order(Order(currency_pair=pair, side='sell', amount=str(amount), type='market', time_in_force='ioc')) if self.is_valid_pair(pair) else False
        except Exception as e: print(f"Error placing sell order: {str(e)}", flush=True); return False
    def find_swing_points(self, df: pd.DataFrame, window: int = 9):
        highs, lows = [], []
        for i in range(window, len(df)-window):
            left_high, right_high = df['high'].iloc[i-window:i].max(), df['high'].iloc[i+1:i+window+1].max()
            left_low, right_low = df['low'].iloc[i-window:i].min(), df['low'].iloc[i+1:i+window+1].min()
            if df['high'].iloc[i] > max(left_high, right_high): highs.append((i, df['high'].iloc[i]))
            if df['low'].iloc[i] < min(left_low, right_low): lows.append((i, df['low'].iloc[i]))
        return highs, lows
    def check_bear_blocks(self, df: pd.DataFrame):
        try:
            if len(df) < 24: return None
            last_24_candles = df.iloc[-24:]
            volume_increase = (last_24_candles['volume'].mean() / df['volume'].mean() - 1) * 100
            if volume_increase < 20: return None
            highs, lows = self.find_swing_points(df)
            last_candle, prev_high = df.iloc[-1], None
            for i in range(len(last_24_candles)-1, -1, -1):
                candle = last_24_candles.iloc[i]
                candle_idx = len(df) - 24 + i
                if candle['close'] > candle['open']:
                    for low_idx, low_val in lows:
                        if low_idx == candle_idx and last_candle['close'] > candle['low']:
                            return {'block': BlockEvent(timestamp=candle.name, price=candle['low'], type='Be-OB', strength=volume_increase),
                                    'signal': "SELL 📉", 'current_price': last_candle['close'], 'volume': last_candle['volume']}
                elif candle['close'] < candle['open']:
                    for high_idx, high_val in highs:
                        if high_idx == candle_idx - 1:
                            if prev_high is None: prev_high = high_val
                            if high_val < prev_high and last_candle['close'] > candle['low']:
                                return {'block': BlockEvent(timestamp=candle.name, price=candle['low'], type='Be-MB', strength=volume_increase),
                                        'signal': "SELL 📉", 'current_price': last_candle['close'], 'volume': last_candle['volume']}
            return None
        except Exception as e: print(f"Error checking bear blocks: {e}", flush=True); return None
    def check_bull_blocks(self, df: pd.DataFrame):
        try:
            if len(df) < 24: return None
            last_24_candles = df.iloc[-24:]
            volume_increase = (last_24_candles['volume'].mean() / df['volume'].mean() - 1) * 100
            if volume_increase < 20: return None
            highs, lows = self.find_swing_points(df)
            last_candle, prev_low = df.iloc[-1], None
            for i in range(len(last_24_candles)-1, -1, -1):
                candle = last_24_candles.iloc[i]
                candle_idx = len(df) - 24 + i
                if candle['open'] > candle['close']:
                    for high_idx, high_val in highs:
                        if high_idx == candle_idx and last_candle['close'] < candle['high']:
                            return {'block': BlockEvent(timestamp=candle.name, price=candle['high'], type='Bu-OB', strength=volume_increase),
                                    'signal': "BUY 🚀", 'current_price': last_candle['close'], 'volume': last_candle['volume']}
                elif candle['close'] > candle['open']:
                    for low_idx, low_val in lows:
                        if low_idx == candle_idx - 1:
                            if prev_low is None: prev_low = low_val
                            if low_val > prev_low and last_candle['close'] < candle['high']:
                                return {'block': BlockEvent(timestamp=candle.name, price=candle['high'], type='Bu-MB', strength=volume_increase),
                                        'signal': "BUY 🚀", 'current_price': last_candle['close'], 'volume': last_candle['volume']}
            return None
        except Exception as e: print(f"Error checking bull blocks: {e}", flush=True); return None
    def scan_for_buys(self):
        try:
            pairs = self.get_spot_pairs()
            print(f"\nScanning {len(pairs)} pairs for buy signals...", flush=True)
            signals = []
            for pair in pairs:
                try:
                    klines = self.get_klines(pair.id)
                    if not klines or any(c.isdigit() for c in pair.id.split('_')[0]): continue
                    df = pd.DataFrame([{
                        'timestamp': self.safe_float_convert(k[0]),
                        'volume': self.safe_float_convert(k[1]),
                        'close': self.safe_float_convert(k[2]),
                        'high': self.safe_float_convert(k[3]),
                        'low': self.safe_float_convert(k[4]),
                        'open': self.safe_float_convert(k[5])
                    } for k in klines if len(k) >= 6])
                    if df.empty or df.isnull().values.any(): continue
                    df = df.set_index('timestamp').sort_index()
                    bull_result = self.check_bull_blocks(df)
                    if bull_result:
                        symbol = pair.id.split('_')[0]
                        usdt_balance = self.get_account_balance('USDT')
                        symbol_balance = self.get_account_balance(symbol)
                        current_price = self.get_spot_price(pair.id)
                        symbol_balance_usdt = symbol_balance * current_price
                        if bull_result['signal'] == "BUY 🚀" and symbol_balance_usdt < 5 and usdt_balance >= 20:
                            if self.place_market_buy(pair.id, 20):
                                bull_result['auto_trade'] = True
                                print(f"ซื้อ {pair.id} มูลค่า $20 สำเร็จ ({bull_result['block'].type})")
                        signals.append({'pair': pair.id, **bull_result})
                except Exception as e: print(f"Error processing {pair.id}: {e}", flush=True)
            return signals
        except Exception as e: print(f"Scan error: {e}", flush=True); return []
    def scan_market(self):
        print("\nChecking portfolio for sell signals...", flush=True)
        self.scan_for_buys()
def main():
    while True:
        try:
            scanner = GateioScanner()
            scanner.scan_market()
            print("\nScanner finished. Waiting 15 minutes...", flush=True)
            time.sleep(60 * 15)
        except Exception as e: print(f"Error: {e}", flush=True); time.sleep(60)
if __name__ == "__main__": main()