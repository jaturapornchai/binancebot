from binance.client import Client
import matplotlib.pyplot as plt
import numpy as np

api_key = 'wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN'
api_secret = '8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU'
client = Client(api_key, api_secret)

# ดึงข้อมูลแท่งเทียน 15 นาที
candles = client.get_klines(symbol='BTCUSDT', interval=Client.KLINE_INTERVAL_15MINUTE)

# แปลงข้อมูลแท่งเทียน
closes = np.array([float(candle[4]) for candle in candles])
highs = np.array([float(candle[2]) for candle in candles])
lows = np.array([float(candle[3]) for candle in candles])
times = [candle[0] for candle in candles]

# ฟังก์ชันหาจุด Swing High
def find_swing_high(highs, period=20):
    swing_high = []
    for i in range(period, len(highs) - period):
        if highs[i] == max(highs[i-period:i+period+1]):
            if len(swing_high) == 0 or (i - swing_high[-1][0] > period):
                swing_high.append((i, highs[i]))
    return swing_high

# ฟังก์ชันหาจุด Swing Low
def find_swing_low(lows, period=20):
    swing_low = []
    for i in range(period, len(lows) - period):
        if lows[i] == min(lows[i-period:i+period+1]):
            if len(swing_low) == 0 or (i - swing_low[-1][0] > period):
                swing_low.append((i, lows[i]))
    return swing_low

# หาจุด Swing High และ Swing Low
period = 20
swing_highs = find_swing_high(highs, period)
swing_lows = find_swing_low(lows, period)

# ตรวจสอบสัญญาณ BUY และ SELL ในแท่งเทียนปัจจุบัน (แท่งล่าสุด)
current_index = len(closes) - 1  # แท่งเทียนปัจจุบันคือแท่งสุดท้าย
current_price = closes[current_index]

buy_signal = False
sell_signal = False

# ตรวจสอบจุด Buy เมื่อราคาปิดใกล้กับ Swing Low
for (swing_low_index, swing_low_price) in swing_lows:
    if current_index == swing_low_index and current_price <= swing_low_price * 1.01:  # ใกล้ Swing Low 1%
        buy_signal = True
        break

# ตรวจสอบจุด Sell เมื่อราคาปิดใกล้กับ Swing High
for (swing_high_index, swing_high_price) in swing_highs:
    if current_index == swing_high_index and current_price >= swing_high_price * 0.99:  # ใกล้ Swing High 1%
        sell_signal = True
        break

# แสดงกราฟพร้อมสัญญาณ
plt.figure(figsize=(10, 6))
plt.plot(closes, label='Close Price')

# แสดงจุด Swing High บนกราฟ
for (i, price) in swing_highs:
    plt.scatter(i, price, color='red', label='Swing High' if i == swing_highs[0][0] else "", marker='^')

# แสดงจุด Swing Low บนกราฟ
for (i, price) in swing_lows:
    plt.scatter(i, price, color='green', label='Swing Low' if i == swing_lows[0][0] else "", marker='v')

# แสดงสัญญาณ Buy หรือ Sell สำหรับแท่งเทียนปัจจุบัน
if buy_signal:
    plt.scatter(current_index, current_price, color='blue', label='Current Buy Signal', marker='o')
if sell_signal:
    plt.scatter(current_index, current_price, color='orange', label='Current Sell Signal', marker='x')

plt.title('BTCUSDT 15-minute Close Price with Swing High, Low, and Current Buy/Sell Signals')
plt.xlabel('Time')
plt.ylabel('Price')
plt.legend()
plt.show()

# แสดงผลลัพธ์ Buy หรือ Sell
if buy_signal:
    print("สัญญาณ Buy ที่แท่งเทียนปัจจุบัน")
elif sell_signal:
    print("สัญญาณ Sell ที่แท่งเทียนปัจจุบัน")
else:
    print("ไม่มีสัญญาณที่แท่งเทียนปัจจุบัน")
