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
MARKET_BUY_AMOUNT = 30
MAX_POSITION_VALUE = 40
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
           pairs = {pair.id: TradingPair(id=pair.id,base=pair.base,quote=pair.quote,fee=pair.fee,min_base_amount=pair.min_base_amount,min_quote_amount=pair.min_quote_amount) for pair in self.spot_api.list_currency_pairs() if pair.id.count('_USDT') == 1}
           tickers = {t.currency_pair: (float(t.quote_volume), float(t.last)) for t in self.spot_api.list_tickers() if t.currency_pair.count('_USDT') == 1}
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
           print(f"Found {len(self.all_pairs)} pairs")
           return True
       except Exception as e:
           print(f"Error fetching market data: {e}")
           return False
   def get_tradeable_pairs(self) -> List[TradingPair]:
       return sorted([pair for pair in self.all_pairs.values() if pair.volume_24h >= MIN_VOLUME_USDT or pair.id in self.portfolio_coins], key=lambda x: x.volume_24h, reverse=True)
   def place_market_buy(self, pair: str, amount_usdt: float = MARKET_BUY_AMOUNT) -> bool:
       try:
           order = Order(currency_pair=pair,side='buy',amount=str(amount_usdt),type='market',time_in_force='ioc')
           self.spot_api.create_order(order)
           print(f"{GREEN}Successfully placed market buy order for {pair} worth {amount_usdt} USDT{RESET}")
           return True
       except Exception as e:
           print(f"Error placing buy order: {str(e)}")
           return False
   def place_market_sell(self, currency: str, available_amount: Decimal) -> bool:
       try:
           order = Order(currency_pair=f"{currency}_USDT",side='sell',amount=str(available_amount),type='market',time_in_force='ioc')
           self.spot_api.create_order(order)
           print(f"{GREEN}Successfully sold {available_amount} {currency}{RESET}")
           return True
       except Exception as e:
           print(f"Error selling {currency}: {str(e)}")
           return False
   def get_account_balance(self, currency: str) -> float:
       try:
           balances = self.spot_api.list_spot_accounts(currency=currency)
           return float(balances[0].available) if balances else 0.0
       except ApiException as e:
           print(f"Error getting balance for {currency}: {e}")
           return 0.0
   def get_kline_data(self, symbol: str) -> List[dict]:
       try:
           return self.spot_api.list_candlesticks(currency_pair=symbol, interval='1h', limit=576)
       except ApiException as e:
           print(f"Error getting kline data: {e}")
           return []
   def calculate_signals(self, df: pd.DataFrame) -> tuple:
        try:
            df[['high', 'low', 'close', 'open', 'volume']] = df[['high', 'low', 'close', 'open', 'volume']].apply(pd.to_numeric)
            if len(df) < 200:
                return 'NO', False
            df = df.reset_index(drop=True)
            zigzag_len = 9
            fib_factor = 0.33
            df['MA200'] = df['close'].rolling(window=200).mean()
            highs = []
            lows = []
            high_indexes = []
            low_indexes = []
            for i in range(zigzag_len, len(df)-zigzag_len):
                if all(df['high'].iloc[i] > df['high'].iloc[i-zigzag_len:i]) and all(df['high'].iloc[i] > df['high'].iloc[i+1:i+zigzag_len+1]):
                    highs.append(df['high'].iloc[i])
                    high_indexes.append(i)
                if all(df['low'].iloc[i] < df['low'].iloc[i-zigzag_len:i]) and all(df['low'].iloc[i] < df['low'].iloc[i+1:i+zigzag_len+1]):
                    lows.append(df['low'].iloc[i])
                    low_indexes.append(i)
            if len(highs) < 2 or len(lows) < 2:
                return 'NO', False
            h0, h1 = highs[-1], highs[-2]
            l0, l1 = lows[-1], lows[-2]
            h0i, h1i = high_indexes[-1], high_indexes[-2]
            l0i, l1i = low_indexes[-1], low_indexes[-2]
            is_bu_mb = h0 > h1 and h0 > h1 + abs(h1 - l0) * fib_factor
            is_bu_bb = l0 < l1
            if h0i > 0 and l0i > 0:
                ob_candles = df.iloc[h1i:l0i]
                red_candles = ob_candles[ob_candles['close'] < ob_candles['open']]
                has_bu_ob = not red_candles.empty
            current_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]
            current_ma200 = current_candle['MA200']
            is_green_candle = current_candle['close'] > current_candle['open']
            crosses_ma200 = (current_candle['low'] <= current_ma200 <= current_candle['high'])
            above_ma200 = current_candle['close'] > current_ma200
            current_signal = 'NO'
            signal_type = ''
            if (is_bu_mb or is_bu_bb) and has_bu_ob and is_green_candle and above_ma200 and crosses_ma200:
                current_signal = 'BUY'
                signal_type = 'Bu-MB' if is_bu_mb else 'Bu-BB'
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            signal_changed = current_signal not in self.signal_times or self.signal_times[current_signal]['time'] != current_time
            if signal_changed:
                self.signal_times[current_signal] = {'signal': current_signal, 'time': current_time}
            if current_signal == 'BUY':
                print(f"High:{current_candle['high']:.8f} Low:{current_candle['low']:.8f} Close:{current_candle['close']:.8f} MA200:{current_ma200:.8f} Signal:{current_signal} {signal_type}")
            return current_signal, signal_changed
        except Exception as e:
            print(f"Error calculating signals: {str(e)}")
            return 'NO', False
   def check_sell_signal(self, currency: str) -> tuple[bool, float]:
       try:
           kline_data = self.get_kline_data(f"{currency}_USDT")
           if len(kline_data) < 15:
               return False, 0.0
           df = pd.DataFrame(kline_data, columns=['timestamp', 'volume', 'close', 'high', 'low', 'open', 'total', 'amount'])
           df[['high', 'low', 'close', 'open']] = df[['high', 'low', 'close', 'open']].apply(pd.to_numeric)
           current_price = float(df['close'].iloc[-1])
           current_balance = self.get_account_balance(currency)
           position_value = current_balance * current_price
           if position_value > MAX_POSITION_VALUE:
               sell_amount_usdt = 35.0
               sell_amount_coins = sell_amount_usdt / current_price
               print(f"Partial sell signal for {currency}: value above ${MAX_POSITION_VALUE}, selling $35 worth")
               return True, sell_amount_coins
           previous_low = float(df['low'].iloc[-2])
           lowest_14_bars = float(df['low'].iloc[-16:-2].min())
           if previous_low < lowest_14_bars:
               print(f"Full sell signal for {currency}: previous low ({previous_low:.8f}) below 14-bar low ({lowest_14_bars:.8f})")
               return True, current_balance
           return False, 0.0
       except Exception as e:
           print(f"Error checking sell signal for {currency}: {str(e)}")
           return False, 0.0
   def run(self):
       try:
           print("Bot started - scanning pairs")
           self.fetch_all_market_data()
           print("-" * 100)
           print(f"{'Timestamp':<20} {'Pair':<12} {'Signal':<8} {'Price':>12} {'24h Volume':>15}")
           print("-" * 100)
           first_scan = True
           while True:
               current_minute = datetime.now().minute
               if current_minute == 0 or first_scan:
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
                               df = pd.DataFrame(self.get_kline_data(pair.id), columns=['timestamp', 'volume', 'close', 'high', 'low', 'open', 'total', 'amount'])
                               signal, changed = self.calculate_signals(df)
                               current_price = float(df['close'].iloc[-1])
                               print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {pair.id:<12} {signal:<8} {current_price:>12.8f} {pair.volume_24h:>15.2f}")
                               if signal == 'BUY':
                                   symbol = pair.id.split('_')[0]
                                   balance = self.get_account_balance(symbol)
                                   value = balance * current_price
                                   if value < MIN_BALANCE_THRESHOLD and self.get_account_balance('USDT') >= MARKET_BUY_AMOUNT:
                                       self.place_market_buy(pair.id)
                               time.sleep(0.2)
                           except Exception as e:
                               print(f"Error analyzing {pair.id}: {e}")
                               continue
                       print(f"Scan completed at {datetime.now():%Y-%m-%d %H:%M:%S}")
                   except Exception as e:
                       print(f"Error during market scan: {e}")
               time.sleep(10)
       except KeyboardInterrupt:
           print("Bot stopped by user")
       except Exception as e:
           print(f"Fatal error: {e}")
def main():
   API_KEY = "c84d3616806f44e5651912c198094a1b"
   API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"
   trader = GateTrader(API_KEY, API_SECRET)
   trader.run()
if __name__ == "__main__":
   main()