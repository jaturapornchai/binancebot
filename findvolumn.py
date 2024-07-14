import requests
from typing import List

def get_high_volume_futures_symbols(min_volume_usdt: float = 10_000_000) -> List[str]:
    def get_futures_symbols() -> List[str]:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url)
        data = response.json()
        return [symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING']

    def get_latest_prices(symbols: List[str]) -> dict:
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        response = requests.get(url)
        data = response.json()
        return {item['symbol']: float(item['price']) for item in data if item['symbol'] in symbols}

    def get_24h_volume(symbols: List[str]) -> dict:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        response = requests.get(url)
        data = response.json()
        return {item['symbol']: float(item['volume']) for item in data if item['symbol'] in symbols}

    symbols = get_futures_symbols()
    prices = get_latest_prices(symbols)
    volumes = get_24h_volume(symbols)

    filtered_symbols = []
    for symbol in symbols:
        if symbol in prices and symbol in volumes:
            volume_usdt = prices[symbol] * volumes[symbol]
            if volume_usdt > min_volume_usdt:
                filtered_symbols.append(symbol)

    return filtered_symbols

# ตัวอย่างการใช้งาน
if __name__ == "__main__":
    high_volume_symbols = get_high_volume_futures_symbols()
    print(f"Symbols with 24h volume > 10,000,000 USDT: {len(high_volume_symbols)}")
    print("Symbols:", high_volume_symbols)