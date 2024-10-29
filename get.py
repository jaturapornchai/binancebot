import requests
import pandas as pd
from datetime import datetime, timedelta
import time

def get_binance_data(symbol, interval, start_time, end_time):
    """
    ดึงข้อมูลราคาจาก Binance API
    
    Parameters:
    - symbol: คู่เหรียญ (เช่น 'BTCUSDT')
    - interval: timeframe (เช่น '1h')
    - start_time: เวลาเริ่มต้น (timestamp)
    - end_time: เวลาสิ้นสุด (timestamp)
    """
    
    endpoint = "https://api.binance.com/api/v3/klines"
    
    params = {
        'symbol': symbol,
        'interval': interval,
        'startTime': int(start_time * 1000),
        'endTime': int(end_time * 1000),
        'limit': 1000
    }
    
    response = requests.get(endpoint, params=params)
    
    # เพิ่มการตรวจสอบสถานะการตอบกลับ
    if response.status_code != 200:
        raise Exception(f"API Error: {response.status_code} - {response.text}")
        
    data = response.json()
    
    return data

def create_dataframe(data):
    """แปลงข้อมูลจาก API เป็น DataFrame ตามรูปแบบที่ต้องการ"""
    
    columns = [
        'Open time',
        'Open',
        'High',
        'Low',
        'Close',
        'Volume',
        'Close time',
        'Quote asset volume',
        'Number of trades',
        'Taker buy base asset volume',
        'Taker buy quote asset volume',
        'Ignore'
    ]
    
    df = pd.DataFrame(data, columns=columns)
    
    # แปลง timestamps เป็น datetime
    df['Open time'] = pd.to_datetime(df['Open time'], unit='ms')
    df['Close time'] = pd.to_datetime(df['Close time'], unit='ms')
    
    # แปลงค่าต่างๆ เป็น float
    numeric_columns = [
        'Open', 'High', 'Low', 'Close', 'Volume',
        'Quote asset volume', 'Taker buy base asset volume',
        'Taker buy quote asset volume'
    ]
    df[numeric_columns] = df[numeric_columns].astype(float)
    
    # แปลง Number of trades เป็น integer
    df['Number of trades'] = df['Number of trades'].astype(int)
    
    # ลบคอลัมน์ Ignore ที่ไม่ได้ใช้
    df = df.drop('Ignore', axis=1)
    
    return df

def main():
    # กำหนดพารามิเตอร์
    symbol = 'APEUSDT'
    interval = '1h'  # เปลี่ยนเป็น interval 1 ชั่วโมง
    
    # คำนวณช่วงเวลา (10 วันย้อนหลัง)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=10)
    
    # แปลงเวลาเป็น timestamp
    start_timestamp = time.mktime(start_time.timetuple())
    end_timestamp = time.mktime(end_time.timetuple())
    
    try:
        # ดึงข้อมูล
        print(f"กำลังดึงข้อมูล {symbol} (interval {interval}) จาก {start_time.strftime('%Y-%m-%d %H:%M')} "
              f"ถึง {end_time.strftime('%Y-%m-%d %H:%M')}...")
        data = get_binance_data(symbol, interval, start_timestamp, end_timestamp)
        
        # สร้าง DataFrame
        df = create_dataframe(data)
        
        # บันทึกเป็น CSV
        filename = f"{symbol}_{interval}_{start_time.strftime('%Y%m%d_%H%M')}_{end_time.strftime('%Y%m%d_%H%M')}.csv"
        df.to_csv(filename, index=False)
        print(f"บันทึกข้อมูลเรียบร้อยแล้วที่: {filename}")
        
        # แสดงข้อมูลตัวอย่าง
        print(f"\nจำนวนแท่งเทียนทั้งหมด: {len(df)}")
        print("\nตัวอย่างข้อมูล:")
        print(df.head())
        print("\nข้อมูลสถิติ:")
        print(df.describe())
        
        # แสดงข้อมูลเพิ่มเติม
        print("\nข้อมูลคอลัมน์:")
        print(df.info())
        
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")

if __name__ == "__main__":
    main()