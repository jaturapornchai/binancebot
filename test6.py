import requests
from typing import List, Tuple
from binance.client import Client
import numpy as np

def get_futures_symbols() -> List[str]:
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    return [symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING']

def calculate_fibonacci_levels(prices):
    max_price = max(prices)
    min_price = min(prices)
    diff = max_price - min_price
    
    fib_levels = {
        "0.382": min_price + diff * 0.382,
        "0.5": min_price + diff * 0.5,
        "0.618": min_price + diff * 0.618,
        "0.786": min_price + diff * 0.786,
        "0.886": min_price + diff * 0.886,  # เพิ่มระดับ 0.886
        "1.0": max_price,
        "1.272": max_price + diff * 0.272,
        "1.618": max_price + diff * 0.618
    }
    
    return fib_levels

def check_harmonic_pattern(prices) -> Tuple[bool, str]:
    X, A, B, C, D = prices[-5:]
    
    XA_fib = calculate_fibonacci_levels([X, A])
    AB_fib = calculate_fibonacci_levels([A, B])
    BC_fib = calculate_fibonacci_levels([B, C])
    CD_fib = calculate_fibonacci_levels([C, D])

    # Gartley Pattern
    if (XA_fib["0.618"] <= B <= XA_fib["0.786"]) and (BC_fib["0.382"] <= D <= BC_fib["0.886"]):
        return True, "Gartley"
    
    # Bat Pattern
    if (XA_fib["0.382"] <= B <= XA_fib["0.5"]) and (BC_fib["0.382"] <= D <= BC_fib["0.886"]):
        return True, "Bat"
    
    # Butterfly Pattern
    if (XA_fib["0.786"] <= B <= XA_fib["0.886"]) and (CD_fib["1.272"] <= D <= CD_fib["1.618"]):
        return True, "Butterfly"
    
    # Crab Pattern
    if (XA_fib["0.618"] <= B <= XA_fib["0.786"]) and (CD_fib["1.618"] <= D <= CD_fib["2.618"]):
        return True, "Crab"
    
    return False, ""

def find_harmonic_patterns(symbol: str, interval: str = '1h', client=None):
    klines = client.get_klines(symbol=symbol, interval=interval)
    prices = [float(kline[4]) for kline in klines]
    
    if len(prices) >= 5:
        found, pattern_name = check_harmonic_pattern(prices)
        if found:
            return True, pattern_name
    
    return False, ""

def main():
    client = Client(api_key='FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il', api_secret='nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt')  # สร้าง object client ก่อนใช้งาน
    symbols = get_futures_symbols()
    
    for symbol in symbols:
        found, pattern_name = find_harmonic_patterns(symbol, client=client)
        if found:
            print(f"Harmonic pattern '{pattern_name}' found in {symbol}")

if __name__ == "__main__":
    main()
