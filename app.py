from typing import List, Dict
from decimal import Decimal
import logging, time, pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional, Dict
from gate_api import ApiClient, Configuration, SpotApi, Order, ApiException
GREEN = '\033[32m'
RESET = '\033[0m'
MIN_VOLUME_USDT = 1_000_000
MIN_BALANCE_THRESHOLD = 5 
MARKET_BUY_AMOUNT = 30
@dataclass
class TradingPair:
    id: str
    base: str
    quote: str
    fee: str
    min_base_amount: str
    min_quote_amount: str
    volume_24h: float = 0.0
    last_price: float = 0.0
class GateTrader:
    def __init__(self, api_key, api_secret):
        config = Configuration(key=api_key, secret=api_secret, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.spot_api = SpotApi(self.client)
        self.signal_times = {}
        self.all_pairs: Dict[str, TradingPair] = {}
        self.portfolio_coins = set()
    def has_number(self, text: str) -> bool:
        return any(char.isdigit() for char in text)
    def fetch_all_market_data(self):
        try:
            pairs = {
                pair.id: TradingPair(
                    id=pair.id,
                    base=pair.base,
                    quote=pair.quote,
                    fee=pair.fee,
                    min_base_amount=pair.min_base_amount,
                    min_quote_amount=pair.min_quote_amount
                )
                for pair in self.spot_api.list_currency_pairs()
                if pair.id.count('_USDT') == 1 and not self.has_number(pair.base)
            }
            tickers = {t.currency_pair: (float(t.quote_volume), float(t.last)) for t in self.spot_api.list_tickers() if t.currency_pair in pairs}
            for pair_id, (volume, price) in tickers.items():
                if pair_id in pairs:
                    pairs[pair_id].volume_24h = volume
                    pairs[pair_id].last_price = price
            accounts = self.spot_api.list_spot_accounts()
            self.portfolio_coins.clear()
            for account in accounts:
                if account.currency != 'USDT' and float(account.available) > 0:
                    pair_id = f"{account.currency}_USDT"
                    if pair_id in tickers and float(account.available) * tickers[pair_id][1] >= MIN_BALANCE_THRESHOLD:
                        self.portfolio_coins.add(pair_id)
            self.all_pairs = pairs
            print(f"Found {len(self.all_pairs)} pairs", flush=True)
            return True
        except Exception as e:
            print(f"Error fetching market data: {e}", flush=True)
            return False
    def get_tradeable_pairs(self) -> List[TradingPair]:
        return sorted([pair for pair in self.all_pairs.values() if pair.volume_24h >= MIN_VOLUME_USDT or pair.id in self.portfolio_coins], key=lambda x: x.volume_24h)
    def place_market_buy(self, pair: str, amount_usdt: float = MARKET_BUY_AMOUNT) -> bool:
        try:
            order = Order(currency_pair=pair, side='buy', amount=str(amount_usdt), type='market', time_in_force='ioc')
            self.spot_api.create_order(order)
            print(f"{GREEN}Successfully placed market buy order for {pair} worth {amount_usdt} USDT{RESET}", flush=True)
            return True
        except Exception as e:
            print(f"Error placing buy order: {str(e)}", flush=True)
            return False
    def place_market_sell(self, currency: str, available_amount: Decimal) -> bool:
        try:
            order = Order(currency_pair=f"{currency}_USDT", side='sell', amount=str(available_amount), type='market', time_in_force='ioc')
            self.spot_api.create_order(order)
            print(f"{GREEN}Successfully sold {available_amount} {currency}{RESET}", flush=True)
            return True
        except Exception as e:
            print(f"Error selling {currency}: {str(e)}", flush=True)
            return False
    def get_account_balance(self, currency: str) -> float:
        try:
            balances = self.spot_api.list_spot_accounts(currency=currency)
            return float(balances[0].available) if balances else 0.0
        except ApiException as e:
            print(f"Error getting balance for {currency}: {e}", flush=True)
            return 0.0
    def calculate_signals(self, pair_id: str) -> tuple:
        try:
            candles = self.spot_api.list_candlesticks(currency_pair=pair_id, interval='1h', limit=502)
            if len(candles) < 502:
                return 'NO', False
            second_last_vol = float(candles[-2][6])
            third_last_vol = float(candles[-3][6])
            historical_vols = [float(c[6]) for c in candles[:-3]]
            avg_volume = np.mean(historical_vols)
            if avg_volume > 0:
                vol_change = ((second_last_vol / avg_volume) - 1) * 100
                if vol_change > 500 and second_last_vol > third_last_vol:
                    print(f"Volume increase: {vol_change:.1f}% for {pair_id}", flush=True)
                    print(f"Second last volume: {second_last_vol:,.0f} USDT", flush=True)
                    print(f"Third last volume: {third_last_vol:,.0f} USDT", flush=True)
                    print(f"Average volume: {avg_volume:,.0f} USDT", flush=True)
                    return 'BUY', True
            return 'NO', False
        except Exception as e:
            print(f"Error calculating signals: {str(e)}", flush=True)
            return 'NO', False
    def check_sell_signal(self, currency: str) -> tuple[bool, float]:
        try:
            candles = self.spot_api.list_candlesticks(currency_pair=f"{currency}_USDT", interval='1h', limit=15)
            if len(candles) < 15:
                return False, 0.0
            current_low = float(candles[-1][3])
            prev_lowest = min(float(c[3]) for c in candles[-15:-1])
            current_balance = self.get_account_balance(currency)
            if current_low < prev_lowest:
                print(f"Sell signal for {currency}:", flush=True)
                print(f"Current Low: {current_low:.8f}", flush=True)
                print(f"Previous 14 candles lowest: {prev_lowest:.8f}", flush=True)
                return True, current_balance
            return False, 0.0
        except Exception as e:
            print(f"Error checking sell signal for {currency}: {str(e)}", flush=True)
            return False, 0.0
    def run(self):
        try:
            print("Bot started - scanning pairs", flush=True)
            self.fetch_all_market_data()
            print("-" * 100, flush=True)
            print(f"{'Timestamp':<20} {'Pair':<12} {'Signal':<8} {'Price':>12} {'24h Volume':>15}", flush=True)
            print("-" * 100, flush=True)
            first_scan = True
            while True:
                current_time = datetime.now()
                if (current_time.minute == 0) or first_scan:
                    first_scan = False
                    try:
                        balances = [{'currency': b.currency, 'available': Decimal(str(b.available))} for b in self.spot_api.list_spot_accounts() if b.currency != 'USDT' and float(b.available) > 0 and float(b.available) * float(self.all_pairs.get(f"{b.currency}_USDT", TradingPair("","","","","","")).last_price) > 5]
                        for balance in balances:
                            should_sell, sell_amount = self.check_sell_signal(balance['currency'])
                            if should_sell:
                                self.place_market_sell(balance['currency'], Decimal(str(sell_amount)))
                            time.sleep(0.2)
                        if not self.fetch_all_market_data():
                            time.sleep(60)
                            continue
                        for pair in self.get_tradeable_pairs():
                            try:
                                signal, changed = self.calculate_signals(pair.id)
                                print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {pair.id:<12} {signal:<8} {pair.last_price:>12.8f} {pair.volume_24h:>15.2f}", flush=True)
                                if signal == 'BUY':
                                    symbol = pair.id.split('_')[0]
                                    balance = self.get_account_balance(symbol)
                                    value = balance * pair.last_price
                                    if value < MIN_BALANCE_THRESHOLD and self.get_account_balance('USDT') >= MARKET_BUY_AMOUNT:
                                        self.place_market_buy(pair.id)
                                time.sleep(0.2)
                            except Exception as e:
                                print(f"Error analyzing {pair.id}: {e}", flush=True)
                                continue
                        print(f"Scan completed at {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
                    except Exception as e:
                        print(f"Error during market scan: {e}", flush=True)
                time.sleep(10)
        except KeyboardInterrupt:
            print("Bot stopped by user", flush=True)
        except Exception as e:
            print(f"Fatal error: {e}", flush=True)
def main():
    API_KEY = "c84d3616806f44e5651912c198094a1b"
    API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"
    trader = GateTrader(API_KEY, API_SECRET)
    trader.run()
if __name__ == "__main__":
    main()