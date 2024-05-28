import ccxt
import pandas as pd
from datetime import datetime, timedelta
import time
from termcolor import colored

# Set up Gate.io API
exchange = ccxt.gateio()

# Fetch OHLCV data from Gate.io
def fetch_recent_ohlcv(symbol, timeframe='1h', limit=900):
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return data
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return []

# Calculate RSI
def calculate_rsi(df, window=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=window, min_periods=1).mean()
    avg_loss = loss.rolling(window=window, min_periods=1).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Detect RSI Divergences
def detect_divergence(df, rsi_col='rsi', price_col='close', lbL=5, lbR=5, rangeUpper=60, rangeLower=5):
    bull_divergences = []
    bear_divergences = []

    for i in range(lbR, len(df) - lbR):
        rsi_window = df[rsi_col].iloc[i - lbR:i + lbR + 1]
        price_window = df[price_col].iloc[i - lbR:i + lbR + 1]

        # Bullish Divergence: ราคาลดลง แต่ RSI เพิ่มขึ้น
        if rsi_window.iloc[-1] > rsi_window.iloc[0] and price_window.iloc[-1] < price_window.iloc[0]:
            bull_divergences.append((df.index[i], df[price_col].iloc[i]))

        # Bearish Divergence: ราคาเพิ่มขึ้น แต่ RSI ลดลง
        if rsi_window.iloc[-1] < rsi_window.iloc[0] and price_window.iloc[-1] > price_window.iloc[0]:
            bear_divergences.append((df.index[i], df[price_col].iloc[i]))

    return bull_divergences, bear_divergences

# Main function to fetch data, calculate RSI, detect divergence, and display results
def analyze_symbols(symbols, timeframe='1h', lookback_hours=6):
    for symbol in symbols:
        data = fetch_recent_ohlcv(symbol, timeframe)
        if not data:
            continue

        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df['rsi'] = calculate_rsi(df)

        bull_divs, bear_divs = detect_divergence(df, lbL=5, lbR=5)

        # Check for Divergences in the specified lookback hours
        current_time = df.index[-1]
        lookback_period = timedelta(hours=lookback_hours)
        recent_bull_divs = [d for d in bull_divs if d[0] >= current_time - lookback_period]
        recent_bear_divs = [d for d in bear_divs if d[0] >= current_time - lookback_period]

        # Print the latest Divergence if any
        if recent_bull_divs:
            latest_bull_div = recent_bull_divs[-1]
            print(colored(f"RSI Divergences for {symbol}: Latest Bullish Divergence detected at {latest_bull_div[0]}.", 'green'))
        if recent_bear_divs:
            latest_bear_div = recent_bear_divs[-1]
            print(colored(f"RSI Divergences for {symbol}: Latest Bearish Divergence detected at {latest_bear_div[0]}.", 'red'))
        if not recent_bull_divs and not recent_bear_divs:
            print(colored(f"RSI Divergences for {symbol}: No divergence in the last {lookback_hours} hours", 'white'))

# Function to run every first minute of the hour
def run_analysis():
    markets = exchange.load_markets()
    order_symbols = []
    for symbol in markets:
        if symbol.endswith('/USDT'):
            order_symbols.append(symbol)
    # ลบ 3S และ 3L , 5S และ 5L
    order_symbols = [symbol for symbol in order_symbols if '3S' not in symbol and '3L' not in symbol and '5S' not in symbol and '5L' not in symbol]
    # remove USDC
    order_symbols = [symbol for symbol in order_symbols if 'USDC' not in symbol]
    print("Order buy low")
    analyze_symbols(order_symbols, timeframe='1h', lookback_hours=6)
    while True:
        current_time = datetime.now()
        if current_time.minute == 0:
            analyze_symbols(order_symbols, timeframe='1h', lookback_hours=6)
            # Wait for the next hour
            time.sleep(3600)
        else:
            # Sleep for a minute and check again
            time.sleep(60)

# Start the analysis process
run_analysis()
