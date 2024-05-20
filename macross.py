import ccxt
import pandas as pd
import matplotlib.pyplot as plt

def get_market_state(symbol, timeframe):
    # Initialize the Binance API client
    exchange = ccxt.binance()

    # Fetch historical price data
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe)

    # Create a DataFrame from the fetched data
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)

    # Calculate 50MA and 200MA
    df['short'] = df['close'].rolling(window=50).mean()
    df['long'] = df['close'].rolling(window=200).mean()

    # Determine if it's a crossover point
    df['crossover'] = None
    for i in range(1, len(df)):
        if (df['short'].iloc[i] > df['long'].iloc[i]) and (df['short'].iloc[i - 1] <= df['long'].iloc[i - 1]):
            df.at[df.index[i], 'crossover'] = 'long'
        elif (df['short'].iloc[i] < df['long'].iloc[i]) and (df['short'].iloc[i - 1] >= df['long'].iloc[i - 1]):
            df.at[df.index[i], 'crossover'] = 'short'

    # Determine the market state
    last_row = df.iloc[-1]
    if last_row['crossover'] == 'long':
        return 'long'
    elif last_row['crossover'] == 'short':
        return 'short'
    else:
        return 'normal'

# Example usage:
symbol = 'LDO/USDT'
timeframe = '15m'
market_state = get_market_state(symbol, timeframe)

print("Market State:", market_state)
