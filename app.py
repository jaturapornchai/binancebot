from typing import List, Dict
from decimal import Decimal
import logging,time,pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional, Dict
from gate_api import ApiClient, Configuration, SpotApi, Order, ApiException
GREEN = '\033[32m'
RESET = '\033[0m'
MIN_VOLUME_USDT = 100_000
MIN_BALANCE_THRESHOLD = 5
MARKET_BUY_AMOUNT = 20
LOOKBACK_PERIODS = 100
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
        self.last_scan_minute = -1
    def fetch_all_market_data(self):
        try:
            print("\nFetching all market data...", flush=True)
            pairs = {pair.id: TradingPair(id=pair.id,base=pair.base,quote=pair.quote,fee=pair.fee,min_base_amount=pair.min_base_amount,min_quote_amount=pair.min_quote_amount) for pair in self.spot_api.list_currency_pairs() if pair.id.count('_USDT') == 1}
            tickers = {t.currency_pair: (float(t.quote_volume), float(t.last)) for t in self.spot_api.list_tickers() if t.currency_pair.count('_USDT') == 1}
            for pair_id, (volume, price) in tickers.items():
                if pair_id in pairs:
                    pairs[pair_id].volume_24h = volume
                    pairs[pair_id].last_price = price
            accounts = self.spot_api.list_spot_accounts()
            self.portfolio_coins.clear()
            for account in accounts:
                if account.currency != 'USDT':
                    balance = float(account.available)
                    if balance > 0:
                        pair_id = f"{account.currency}_USDT"
                        if pair_id in tickers:
                            value = balance * tickers[pair_id][1]
                            if value >= MIN_BALANCE_THRESHOLD:
                                self.portfolio_coins.add(pair_id)
            self.all_pairs = pairs
            print(f"Found {len(self.all_pairs)} total pairs")
            print(f"Portfolio contains {len(self.portfolio_coins)} coins with value > ${MIN_BALANCE_THRESHOLD}")
            return True
        except Exception as e:
            print(f"Error fetching market data: {e}", flush=True)
            return False
    def get_tradeable_pairs(self) -> List[TradingPair]:
        return sorted([pair for pair in self.all_pairs.values() if pair.volume_24h >= MIN_VOLUME_USDT or pair.id in self.portfolio_coins], key=lambda x: x.volume_24h, reverse=True)
    def place_market_buy(self, pair: str, amount_usdt: float = MARKET_BUY_AMOUNT) -> bool:
        try:
            order = Order(currency_pair=pair,side='buy',amount=str(amount_usdt),type='market',time_in_force='ioc')
            self.spot_api.create_order(order)
            print(f"{GREEN}Successfully placed market buy order for {pair} worth {amount_usdt} USDT{RESET}", flush=True)
            return True
        except Exception as e:
            print(f"Error placing buy order: {str(e)}", flush=True)
            return False
    def place_market_sell(self, currency: str, available_amount: Decimal) -> bool:
        try:
            order = Order(currency_pair=f"{currency}_USDT",side='sell',amount=str(available_amount),type='market',time_in_force='ioc')
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
    def get_kline_data(self, symbol: str, interval: str = '15m', limit: int = LOOKBACK_PERIODS + 10) -> List[dict]:
        try:
            return self.spot_api.list_candlesticks(currency_pair=symbol,interval='15m',limit=limit)
        except ApiException as e:
            print(f"Error getting kline data: {e}", flush=True)
            return []
    def check_sell_signal(self, currency: str) -> bool:
        try:
            kline_data = self.get_kline_data(f"{currency}_USDT")
            if not kline_data or len(kline_data) < LOOKBACK_PERIODS: return False
            df = pd.DataFrame(kline_data, columns=['timestamp', 'volume', 'close', 'high', 'low', 'open', 'total', 'amount'])
            df[['high', 'low', 'close', 'open']] = df[['high', 'low', 'close', 'open']].apply(pd.to_numeric)
            _, _, lower_line, _ = self.calculate_regression_channel(df.tail(100))
            if lower_line is None:
                return False
            current_candle = df.iloc[-1]
            previous_candle = df.iloc[-2]
            # Check if price breaks below lower line
            breaks_lower = current_candle['close'] < lower_line[-1] and previous_candle['close'] >= lower_line[-2]
            return breaks_lower
        except Exception as e:
            print(f"Error checking sell signal for {currency}: {str(e)}", flush=True)
            return False
    def scan_and_sell(self, balances: List[Dict]):
        print("\nScanning holdings for sell conditions...", flush=True)
        for balance in balances:
            try:
                currency = balance['currency']
                available = balance['available']
                if self.check_sell_signal(currency):
                    print(f"Selling {available} {currency}", flush=True)
                    self.place_market_sell(currency, available)
                time.sleep(0.2)
            except Exception as e:
                print(f"Error processing {currency}: {str(e)}", flush=True)
    def calculate_regression_channel(self, df: pd.DataFrame, length: int = 100, dev_length: float = 2.0) -> tuple:
        try:
            y = df['close'].values
            x = np.arange(len(y))
            x = x[-length:]
            y = y[-length:]
            slope, intercept = np.polyfit(x, y, 1)
            middle_line = slope * x + intercept
            deviation = np.sqrt(np.sum((y - middle_line) ** 2) / length)
            upper_line = middle_line + deviation * dev_length
            lower_line = middle_line - deviation * dev_length
            return middle_line, upper_line, lower_line, slope
        except Exception as e:
            print(f"Error calculating regression channel: {str(e)}")
            return None, None, None, None
    def calculate_signals(self, df: pd.DataFrame) -> tuple:
        try:
            df[['high', 'low', 'close', 'open', 'volume']] = df[['high', 'low', 'close', 'open', 'volume']].apply(pd.to_numeric)
            middle_line, upper_line, lower_line, slope = self.calculate_regression_channel(df.tail(100))
            if upper_line is None:
                return 'HOLD', False
            current_candle = df.iloc[-1]
            trend_up = slope > 0
            channel_height = upper_line[-1] - lower_line[-1]
            quarter_height = channel_height / 4
            bottom_quarter_upper_bound = lower_line[-1] + quarter_height
            price_in_bottom_quarter = current_candle['close'] <= bottom_quarter_upper_bound and current_candle['close'] >= lower_line[-1]
            is_bullish = current_candle['close'] > current_candle['open']
            df['signal'] = 'HOLD'
            if trend_up and price_in_bottom_quarter and is_bullish:
                df.loc[df.index[-1], 'signal'] = 'BUY'
            current_signal = df['signal'].iloc[-1]
            signal_changed = False
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if current_signal not in self.signal_times or self.signal_times[current_signal]['time'] != current_time:
                self.signal_times[current_signal] = {'signal': current_signal, 'time': current_time}
                signal_changed = True
            return current_signal, signal_changed
        except Exception as e:
            print(f"Error calculating signals: {str(e)}")
            return 'HOLD', False
    def handle_buy_signal(self, pair: TradingPair, current_price: float):
        try:
            symbol = pair.id.split('_')[0]
            usdt_balance = self.get_account_balance('USDT')
            symbol_balance = self.get_account_balance(symbol)
            symbol_balance_usdt = symbol_balance * current_price
            if symbol_balance_usdt < MIN_BALANCE_THRESHOLD:
                if usdt_balance >= MARKET_BUY_AMOUNT:
                    print(f"\nPosition value ({symbol_balance_usdt:.2f} USDT) below threshold. Placing market buy...", flush=True)
                    self.place_market_buy(pair.id)
                else:
                    print(f"\nInsufficient USDT balance ({usdt_balance:.2f}) for market buy", flush=True)
            else:
                print(f"\nCurrent position value ({symbol_balance_usdt:.2f} USDT) above threshold. No action needed.", flush=True)
        except Exception as e:
            print(f"Error handling buy signal: {str(e)}", flush=True)
    def get_non_zero_balances(self) -> List[Dict]:
        try:
            balances = []
            for balance in self.spot_api.list_spot_accounts():
                if float(balance.available) > 0 and balance.currency != 'USDT':
                    amount = Decimal(str(balance.available))
                    if amount * Decimal(str(self.all_pairs.get(f"{balance.currency}_USDT", TradingPair("","","","","","")).last_price)) > Decimal('5'):
                        balances.append({'currency': balance.currency, 'available': amount})
            return balances
        except Exception as e:
            print(f"Error fetching balances: {str(e)}", flush=True)
            return []
    def run(self):
        try:
            print("\nInitializing trading bot...", flush=True)
            print("Bot will scan at minutes: 0, 15, 30, 45", flush=True)
            self.fetch_all_market_data()
            print(f"\nStarting initial market scan...", flush=True)
            print("-" * 100)
            print(f"{'Timestamp':<20} {'Pair':<12} {'Signal':<8} {'Price':>12} {'24h Volume':>15}")
            print("-" * 100, flush=True)
            first_scan = True
            while True:
                if datetime.now().minute % 15 == 0 or first_scan:
                    first_scan = False
                    try:
                        sell_coins = self.get_non_zero_balances()
                        if sell_coins: self.scan_and_sell(sell_coins)
                        print(f"\nStarting market scan", flush=True)
                        if not self.fetch_all_market_data():
                            print("Failed to fetch market data. Will retry next scan.", flush=True)
                            time.sleep(60)
                            continue
                        pairs = self.get_tradeable_pairs()
                        for pair in pairs:
                            try:
                                kline_data = self.get_kline_data(pair.id)
                                if not kline_data or len(kline_data) < LOOKBACK_PERIODS: continue
                                df = pd.DataFrame(kline_data, columns=['timestamp', 'volume', 'close', 'high', 'low', 'open', 'total', 'amount'])
                                current_signal, signal_changed = self.calculate_signals(df)
                                current_price = float(df['close'].iloc[-1])
                                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<20} {pair.id:<12} {current_signal:<8} {current_price:>12.8f} {pair.volume_24h:>15.2f}", flush=True)
                                if current_signal == 'BUY': self.handle_buy_signal(pair, current_price)
                                time.sleep(0.2)
                            except Exception as e:
                                print(f"Error analyzing {pair.id}: {e}", flush=True)
                                continue
                        print(f"\nScan completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    except Exception as e:
                        print(f"Error during market scan: {e}", flush=True)
                time.sleep(10)                    
        except KeyboardInterrupt:
            print("\nBot stopped by user.", flush=True)
        except Exception as e:
            print(f"Fatal error: {e}", flush=True)
def main():
    API_KEY = "c84d3616806f44e5651912c198094a1b"
    API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"
    trader = GateTrader(API_KEY, API_SECRET)
    trader.run()
if __name__ == "__main__":
    main()