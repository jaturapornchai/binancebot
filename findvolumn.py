import requests
from typing import List
from statistics import mean
import schedule
import time
from datetime import datetime

line_token = "aMFv92TD5VFEXQ3fU9gN1sAaWWrkyVoo6VlJe95hvE7"

def send_line_notify(message):
    try:
        headers = {
            'Authorization': f'Bearer {line_token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        payload = {'message': message}
        response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
        if response.status_code == 200:
            print("LINE notification sent successfully", flush=True)
        else:
            print(f"Failed to send LINE notification. Status code: {response.status_code}", flush=True)
    except Exception as e:
        print(f"Error sending LINE message: {e}", flush=True)

def get_high_buy_volume_futures_symbols() -> List[str]:
    def get_futures_symbols() -> List[str]:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url)
        data = response.json()
        return [symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING']

    def get_buy_volume_data(symbols: List[str]) -> dict:
        url = "https://fapi.binance.com/futures/data/takerlongshortRatio"
        results = {}
        for symbol in symbols:
            params = {
                "symbol": symbol,
                "period": "15m",
                "limit": 144  # 6 days (144 hours)
            }
            response = requests.get(url, params=params)
            data = response.json()
            
            buy_volumes = [float(item['buyVol']) for item in data]
            #print(f"Processing {symbol}: {buy_volumes}")            
            
            # Calculate the average of the last 144 time frames (6 days)
            average_144 = mean(buy_volumes)
            
            average_compare = average_144 * 4
            if buy_volumes[-1] > average_compare and buy_volumes[-2] > average_compare and buy_volumes[-3] > average_compare:
                results[symbol] = (buy_volumes[-3:], average_144)
                print(f"Processed {symbol}: Last 3 Volumes = {buy_volumes[-3:]}, Average = {average_144}")
        return results

    symbols = get_futures_symbols()
    volume_data = get_buy_volume_data(symbols)

    filtered_symbols = []
    for symbol, (last_3_volumes, average_144) in volume_data.items():
        filtered_symbols.append(symbol)

    return filtered_symbols

def job():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Job started at {current_time}")
    high_buy_volume_symbols = get_high_buy_volume_futures_symbols()
    
    if high_buy_volume_symbols:
        line_message = "High Buy Volume Futures Symbols:\n"
        line_message += "\n".join(high_buy_volume_symbols)
        send_line_notify(line_message)
    
    print(f"Notification sent at {current_time}")

if __name__ == "__main__":
    job()
    schedule.every().hour.at(":00").do(job)
    schedule.every().hour.at(":15").do(job)
    schedule.every().hour.at(":30").do(job)
    schedule.every().hour.at(":45").do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(1)
