from datetime import datetime
import time, pandas as pd, numpy as np
from dataclasses import dataclass
from typing import List
from gate_api import ApiClient, Configuration, SpotApi, Order

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

@dataclass
class GateioScanner:
    def __init__(self):
        self.config = Configuration(key=API_KEY, secret=API_SECRET, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(self.config)
        self.spot_api = SpotApi(self.client)

    def is_valid_pair(self, pair_id):
        return False if '_OLD' in pair_id or pair_id in INVALID_PAIRS else True

    def get_spot_pairs(self):
        try:
            pairs = [pair for pair in self.spot_api.list_currency_pairs() if pair.id.count('_USDT') == 1 and self.is_valid_pair(pair.id)]
            tickers = self.spot_api.list_tickers()
            volume_dict = {t.currency_pair: float(t.quote_volume) for t in tickers if t.currency_pair.count('_USDT') == 1 and self.is_valid_pair(t.currency_pair)}
            filtered_pairs = [pair for pair in pairs if pair.id in volume_dict and volume_dict[pair.id] >= 100_000]
            for pair in filtered_pairs:
                pair.volume_24h = volume_dict[pair.id]
            return sorted(filtered_pairs, key=lambda x: x.volume_24h, reverse=True)
        except Exception as e:
            print(f"Error getting pairs: {e}", flush=True)
            return []

    def get_spot_price(self, pair: str) -> float:
        try:
            return float(self.spot_api.list_tickers(currency_pair=pair)[0].last) if self.is_valid_pair(pair) else 0.0
        except Exception as e:
            print(f"Error getting price for {pair}: {e}", flush=True)
            return 0.0

    def get_account_balance(self, symbol: str) -> float:
        try:
            return next((float(b.available) for b in self.spot_api.list_spot_accounts() if b.currency.lower() == symbol.lower()), 0.0)
        except Exception as e:
            print(f"Error getting balance: {str(e)}", flush=True)
            return 0.0

    def place_market_buy(self, pair: str, amount_usdt: float = 20):
        try:
            return self.spot_api.create_order(Order(currency_pair=pair, side='buy', amount=str(amount_usdt), type='market', time_in_force='ioc')) if self.is_valid_pair(pair) else False
        except Exception as e:
            print(f"Error placing buy order: {str(e)}", flush=True)
            return False

    def check_buy_signals(self, symbol):
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
                    if time_diff_minutes < 60:
                        print(f"\n{'='*20} {symbol} Buy Signals {'='*20}", flush=True)
                        print(f"Signal Time: ({time_diff_minutes:.1f} minutes ago)", flush=True)
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

    def scan_for_buys(self):
        try:
            pairs = self.get_spot_pairs()
            print(f"\nScanning {len(pairs)} pairs for buy signals...", flush=True)
            for pair in pairs:
                try:
                    if self.check_buy_signals(pair.id):
                        symbol = pair.id.split('_')[0]
                        usdt_balance = self.get_account_balance('USDT')
                        symbol_balance = self.get_account_balance(symbol)
                        current_price = self.get_spot_price(pair.id)
                        symbol_balance_usdt = symbol_balance * current_price
                        if symbol_balance_usdt < 5 and usdt_balance >= 20:
                            self.place_market_buy(pair.id, 20)
                            print(f"Buy order placed for {pair.id}", flush=True)
                        else:
                            print(f"Skipping buy for {pair.id}. Symbol balance USDT: {symbol_balance_usdt:.2f}, USDT balance: {usdt_balance:.2f}", flush=True)
                except Exception as e:
                    print(f"Error processing {pair.id}: {e}", flush=True)
        except Exception as e:
            print(f"Scan error: {e}", flush=True)
            return []

    def scan_for_sells(self):
        try:
            # Get all account balances at once
            all_balances = self.spot_api.list_spot_accounts()
            
            # Get all tickers at once
            tickers = {t.currency_pair: t for t in self.spot_api.list_tickers()}
            
            # Process each balance
            for balance in all_balances:
                symbol = balance.currency
                available_amount = float(balance.available)
                
                # Skip if no balance or if it's USDT
                if available_amount <= 0 or symbol == 'USDT':
                    continue
                    
                # Check if there's a USDT pair for this currency
                currency_pair = f"{symbol}_USDT"
                ticker = tickers.get(currency_pair)
                
                if ticker:
                    current_price = float(ticker.last)
                    
                    # Calculate total USDT value
                    total_usdt_value = available_amount * current_price
                    
                    # Check if total USDT value is more than $25
                    if total_usdt_value > 25:
                        # If value is over $25, sell $10 worth
                        amount_to_sell = 10 / current_price
                        
                        # Make sure we don't try to sell more than we have
                        amount_to_sell = min(amount_to_sell, available_amount)
                        
                        # Create sell order
                        if amount_to_sell > 0:
                            self.spot_api.create_order(
                                Order(
                                    currency_pair=currency_pair,
                                    side='sell',
                                    amount=str(amount_to_sell),
                                    type='market',
                                    time_in_force='ioc'
                                )
                            )
                            print(f"Sold ${10} worth of {symbol}", flush=True)
                            print(f"Current holdings: {available_amount:.8f} {symbol}", flush=True)
                            print(f"Total USDT value: ${total_usdt_value:.2f}", flush=True)
                        
        except Exception as e:
            print(f"Error selling: {e}", flush=True)

    def scan_market(self):
        print("\nChecking portfolio for sell signals...", flush=True)
        self.scan_for_sells()
        print("\nChecking market for buy signals...", flush = True)
        self.scan_for_buys()

def main():
    first_run = True
    while True:
        try:
            if datetime.now().minute % 15 == 0 or first_run:
                first_run = False
                print("Starting scanner...", flush=True)
                scanner = GateioScanner()
                scanner.scan_market()
                print("\nScanner finished. Waiting 15 minutes...", flush=True)
        except Exception as e:
            print(f"Error: {e}", flush=True)

        time.sleep(10)

if __name__ == "__main__":
    main()
