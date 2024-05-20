import datetime
import pandas as pd
import ccxt
import requests

line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"

def send_line_notify(message):
    """Send notifications through LINE Notify."""
    headers = {
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': 'SPOT : ' + message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def get_spot_symbols():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    # Filter for symbols that are trading and end with USDT
    spot_symbols = {symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING' and symbol['quoteAsset'] == 'USDT'}
    return spot_symbols

def get_futures_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    # Filter for symbols that are trading and end with USDT
    futures_symbols = {symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING' and symbol['quoteAsset'] == 'USDT'}
    return futures_symbols

def find_spot_only_symbols():
    spot_symbols = get_spot_symbols()
    futures_symbols = get_futures_symbols()
    # Find symbols that are in spot but not in futures
    spot_only_symbols = spot_symbols - futures_symbols
    return spot_only_symbols

def find_volume(symbol, timeframe='1d'):
    # Initialize the exchange - make sure to configure this part with your chosen exchange
    exchange = ccxt.binance()  # Example using Binance; adjust accordingly
    
    # Fetch the last 45 days to include the previous day for comparison
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=45)

    # Create a DataFrame with the fetched data
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    # Convert timestamp from milliseconds to a datetime format
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # Calculate the average volume of the previous 44 days
    avg_volume = df['volume'].iloc[:-1].mean()

    # Get the volume for the last day
    last_volume = df['volume'].iloc[-1]

    if last_volume > avg_volume * 2:
        return 'long'
    else:
        return 'hold'
                              
def main():
    spot_only_symbols = find_spot_only_symbols()
    print("USDT pairs available on Binance Spot but not on Binance Futures:", spot_only_symbols)
    # Write to file for import in tradingview or other uses
    with open("spot_only_symbols.txt", "w") as f:
        for symbol in sorted(spot_only_symbols):  # Sorting symbols alphabetically
            f.write(symbol + "\n")

    first_run = True
    while True:
        if datetime.datetime.now().minute == 0 or first_run:
            first_run = False
            for symbol in spot_only_symbols:                    
                try:
                    #change_leverage(symbol)
                    signal =  find_volume(symbol)
                    if signal == 'short' or signal == 'long':
                        print(signal + " " + symbol)
                        send_line_notify(f"Found {signal} signal for {symbol}")
                except Exception as e:
                    print(f'Error: {e}' + " " + symbol)
                    # if e find 'invalid' remove from spot_symbols
                    if 'insufficient' in str(e):
                        print(f"Insufficient balance stop.")
                        break
                    if 'Invalid' in str(e):
                        spot_only_symbols.remove(symbol)      
            print("Sleeping for an hour")

if __name__ == "__main__":
    main()
