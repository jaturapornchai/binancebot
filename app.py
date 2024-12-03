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
MIN_VOLUME_USDT = 100_000
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

    def fetch_all_market_data(self):
        try:
            pairs = {pair.id: TradingPair(
                id=pair.id,
                base=pair.base,
                quote=pair.quote,
                fee=pair.fee,
                min_base_amount=pair.min_base_amount,
                min_quote_amount=pair.min_quote_amount
            ) for pair in self.spot_api.list_currency_pairs() if pair.id.count('_USDT') == 1}
            
            tickers = {t.currency_pair: (float(t.quote_volume), float(t.last)) 
                      for t in self.spot_api.list_tickers() if t.currency_pair.count('_USDT') == 1}
            
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
        return sorted(
            [pair for pair in self.all_pairs.values() 
             if pair.volume_24h >= MIN_VOLUME_USDT or pair.id in self.portfolio_coins],
            key=lambda x: x.volume_24h,
            reverse=True
        )

    def place_market_buy(self, pair: str, amount_usdt: float = MARKET_BUY_AMOUNT) -> bool:
        try:
            order = Order(
                currency_pair=pair,
                side='buy',
                amount=str(amount_usdt),
                type='market',
                time_in_force='ioc'
            )
            self.spot_api.create_order(order)
            print(f"{GREEN}Successfully placed market buy order for {pair} worth {amount_usdt} USDT{RESET}", flush=True)
            return True
        except Exception as e:
            print(f"Error placing buy order: {str(e)}", flush=True)
            return False

    def place_market_sell(self, currency: str, available_amount: Decimal) -> bool:
        try:
            order = Order(
                currency_pair=f"{currency}_USDT",
                side='sell',
                amount=str(available_amount),
                type='market',
                time_in_force='ioc'
            )
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

    def get_kline_data(self, symbol: str) -> List[dict]:
        try:
            # Changed from 1h to 4h timeframe, adjusted limit to maintain similar historical data range
            return self.spot_api.list_candlesticks(currency_pair=symbol, interval='4h', limit=144)
        except ApiException as e:
            print(f"Error getting kline data: {e}", flush=True)
            return []

    def calculate_signals(self, df: pd.DataFrame) -> tuple:
        try:
            df[['high', 'low', 'close', 'open', 'volume']] = df[['high', 'low', 'close', 'open', 'volume']].apply(pd.to_numeric)
            if len(df) < 30:
                return 'NO', False

            df = df.reset_index(drop=True)
            df['EMA10'] = df['close'].ewm(span=10, adjust=False).mean()
            df['EMA30'] = df['close'].ewm(span=30, adjust=False).mean()

            current_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]
            
            current_cross = current_candle['EMA10'] > current_candle['EMA30']
            prev_cross = prev_candle['EMA10'] <= prev_candle['EMA30']
            
            current_signal = 'NO'
            if current_cross and prev_cross:
                current_signal = 'BUY'
                print(f"EMA Crossover - EMA10:{current_candle['EMA10']:.8f} EMA30:{current_candle['EMA30']:.8f}", flush=True)

            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            signal_changed = current_signal not in self.signal_times or self.signal_times[current_signal]['time'] != current_time
            
            if signal_changed:
                self.signal_times[current_signal] = {'signal': current_signal, 'time': current_time}
                
            return current_signal, signal_changed
        except Exception as e:
            print(f"Error calculating signals: {str(e)}", flush=True)
            return 'NO', False

    def check_sell_signal(self, currency: str) -> tuple[bool, float]:
        try:
            kline_data = self.get_kline_data(f"{currency}_USDT")
            if len(kline_data) < 10:
                return False, 0.0

            df = pd.DataFrame(kline_data, columns=['timestamp', 'volume', 'close', 'high', 'low', 'open', 'total', 'amount'])
            df[['high', 'low', 'close', 'open']] = df[['high', 'low', 'close', 'open']].apply(pd.to_numeric)
            
            df['EMA5'] = df['close'].ewm(span=5, adjust=False).mean()
            df['EMA10'] = df['close'].ewm(span=10, adjust=False).mean()
            
            current_balance = self.get_account_balance(currency)
            current_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]
            
            ema_cross_down = (current_candle['EMA5'] < current_candle['EMA10'] and 
                            prev_candle['EMA5'] >= prev_candle['EMA10'])
            
            if ema_cross_down:
                print(f"Sell signal for {currency}: EMA5 crossed below EMA10 - Selling entire position", flush=True)
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
                if (current_time.hour % 4 == 0 and current_time.minute == 0) or first_scan:
                    first_scan = False
                    try:
                        # Check for sell signals
                        balances = [
                            {'currency': b.currency, 'available': Decimal(str(b.available))}
                            for b in self.spot_api.list_spot_accounts()
                            if b.currency != 'USDT' and float(b.available) > 0 
                            and float(b.available) * float(self.all_pairs.get(f"{b.currency}_USDT", 
                                                        TradingPair("","","","","","")).last_price) > 5
                        ]
                        
                        for balance in balances:
                            should_sell, sell_amount = self.check_sell_signal(balance['currency'])
                            if should_sell:
                                self.place_market_sell(balance['currency'], Decimal(str(sell_amount)))
                            time.sleep(0.2)

                        if not self.fetch_all_market_data():
                            time.sleep(60)
                            continue

                        # Scan for buy signals
                        for pair in self.get_tradeable_pairs():
                            try:
                                df = pd.DataFrame(
                                    self.get_kline_data(pair.id),
                                    columns=['timestamp', 'volume', 'close', 'high', 'low', 'open', 'total', 'amount']
                                )
                                signal, changed = self.calculate_signals(df)
                                current_price = float(df['close'].iloc[-1])
                                
                                print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {pair.id:<12} {signal:<8} "
                                      f"{current_price:>12.8f} {pair.volume_24h:>15.2f}", flush=True)
                                
                                if signal == 'BUY':
                                    symbol = pair.id.split('_')[0]
                                    balance = self.get_account_balance(symbol)
                                    value = balance * current_price
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