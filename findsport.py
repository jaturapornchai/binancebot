from typing import List, Dict
from datetime import datetime
import time
import numpy as np
from dataclasses import dataclass
from gate_api import ApiClient, Configuration, SpotApi

@dataclass
class TradingPair:
    id: str
    base: str
    quote: str
    last_price: float = 0.0
    volume_24h: float = 0.0
    second_last_vol: float = 0.0
    third_last_vol: float = 0.0
    avg_volume: float = 0.0
    volume_change: float = 0.0
    
class VolumeScanner:
    def __init__(self, api_key: str, api_secret: str):
        config = Configuration(key=api_key, secret=api_secret, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.spot_api = SpotApi(self.client)
        self.MIN_24H_VOLUME = 1_000_000  # Minimum 24h volume in USDT
        self.LOOKBACK_PERIODS = 500  # จำนวน candles ย้อนหลัง

    def scan_volume_change(self):
        """สแกนหาเหรียญที่มีการเปลี่ยนแปลงของ volume โดยดู timeframe ที่ 2-3 ย้อนหลัง"""
        print(f"\n{'=' * 140}")
        print(f"Scanning volume change (comparing 2nd & 3rd last candles)... {datetime.now():%Y-%m-%d %H:%M:%S}")
        print(f"{'=' * 140}")
        print(f"{'Pair':<12} {'Price':<12} {'24h Vol(USDT)':<20} {'2nd Last Vol':<20} {'3rd Last Vol':<20} {'Change %':<12} {'Last Update'}")
        print(f"{'-' * 140}")

        try:
            # ดึงข้อมูลคู่เทรดทั้งหมด
            pairs = {
                pair.id: TradingPair(
                    id=pair.id,
                    base=pair.base,
                    quote=pair.quote
                )
                for pair in self.spot_api.list_currency_pairs()
                if pair.quote == 'USDT'
            }

            # ดึงข้อมูล ticker และกรองเฉพาะคู่ที่มี volume 24h > 1M USDT
            tickers = {
                t.currency_pair: (float(t.quote_volume), float(t.last))
                for t in self.spot_api.list_tickers()
                if t.currency_pair in pairs 
                and float(t.quote_volume) >= self.MIN_24H_VOLUME
            }

            # อัพเดตข้อมูลตลาด
            for pair_id, (volume_24h, price) in tickers.items():
                if pair_id in pairs:
                    pairs[pair_id].volume_24h = volume_24h
                    pairs[pair_id].last_price = price

            # ตรวจสอบแต่ละคู่เทรด
            for pair_id in tickers.keys():
                try:
                    # ดึงข้อมูล candle ย้อนหลัง
                    candles = self.spot_api.list_candlesticks(
                        currency_pair=pair_id,
                        interval='1h',
                        limit=self.LOOKBACK_PERIODS + 3  # +3 for current + 2nd & 3rd last candles
                    )
                    
                    if len(candles) >= self.LOOKBACK_PERIODS + 3:
                        # แยก candles สำหรับการคำนวณ
                        historical_candles = candles[:-3]  # ไม่รวม 3 แท่งล่าสุด
                        second_last_candle = candles[-2]  # แท่งที่ 2
                        third_last_candle = candles[-3]  # แท่งที่ 3
                        
                        # Volume ของแท่งที่ 2 และ 3 (USDT)
                        second_last_vol = float(second_last_candle[6])
                        third_last_vol = float(third_last_candle[6])
                        
                        # คำนวณค่าเฉลี่ย volume ย้อนหลัง
                        historical_volumes = [float(c[6]) for c in historical_candles]
                        avg_volume = np.mean(historical_volumes)
                        
                        pairs[pair_id].second_last_vol = second_last_vol
                        pairs[pair_id].third_last_vol = third_last_vol
                        pairs[pair_id].avg_volume = avg_volume
                        
                        if third_last_vol > 0 and avg_volume > 0:
                            volume_change = ((second_last_vol / third_last_vol) - 1) * 100
                            avg_change = ((second_last_vol / avg_volume) - 1) * 100
                            pairs[pair_id].volume_change = volume_change

                            # แสดงผลถ้า volume เปลี่ยนแปลงมากกว่า 500% เทียบกับค่าเฉลี่ย
                            if avg_change > 500:
                                print(
                                    f"{pair_id:<12} "
                                    f"{pairs[pair_id].last_price:<12.8f} "
                                    f"{pairs[pair_id].volume_24h:>15,.0f} USDT "
                                    f"{second_last_vol:>15,.0f} USDT "
                                    f"{third_last_vol:>15,.0f} USDT "
                                    f"{volume_change:>10.1f}% "
                                    f"{datetime.now():%H:%M:%S}"
                                )

                    time.sleep(0.1)  # ป้องกัน rate limit

                except Exception as e:
                    print(f"Error analyzing {pair_id}: {e}")
                    continue

        except Exception as e:
            print(f"Error scanning market: {e}")

def main():
    API_KEY = "c84d3616806f44e5651912c198094a1b"
    API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"
    
    scanner = VolumeScanner(API_KEY, API_SECRET)
    
    while True:
        scanner.scan_volume_change()
        time.sleep(10)  # รอ 10 วินาทีก่อนสแกนรอบใหม่

if __name__ == "__main__":
    main()