# AI Trading Prompt Templates

ไฟล์เหล่านี้เป็น prompt templates สำหรับ AI trading bot ที่จะถูกส่งไปยัง DeepSeek API

## ไฟล์ Prompt Templates

### 1. `prompt_new_position.txt`
- ใช้เมื่อยังไม่มี position เปิดอยู่
- ถาม AI ว่าควรเปิด LONG, SHORT หรือ HOLD
- Variables ที่ใช้:
  - `{symbol}` - ชื่อเหรียญ เช่น BTCUSDT
  - `{timeframe}` - ช่วงเวลา เช่น 15m
  - `{current_price}` - ราคาปัจจุบัน
  - `{total_candles}` - จำนวนแท่งเทียนทั้งหมด
  - `{ohlcv_data}` - ข้อมูล OHLCV ในรูปแบบ compact

### 2. `prompt_existing_position.txt`
- ใช้เมื่อมี position เปิดอยู่แล้ว
- ถาม AI ว่าควรปิด (CLOSE) หรือถือ (HOLD) ต่อ
- Variables ที่ใช้:
  - `{symbol}` - ชื่อเหรียญ
  - `{timeframe}` - ช่วงเวลา
  - `{current_price}` - ราคาปัจจุบัน
  - `{total_candles}` - จำนวนแท่งเทียน
  - `{ohlcv_data}` - ข้อมูล OHLCV
  - `{position_type}` - LONG หรือ SHORT
  - `{position_size}` - ขนาดของ position

## การแก้ไข Prompt

1. เปิดไฟล์ `.txt` ที่ต้องการแก้ไข
2. แก้ไขเนื้อหาตามต้องการ โดยคงรูปแบบ `{variable}` ไว้
3. บันทึกไฟล์
4. รันโปรแกรม `app.py` ใหม่

## ตัวอย่างการใช้งาน

```python
# โปรแกรมจะอ่าน template และแทนค่าตัวแปร
template = load_prompt_template("prompt_new_position.txt")
prompt = template.format(
    symbol="BTCUSDT",
    timeframe="15m", 
    current_price="67235.20",
    total_candles=144,
    ohlcv_data="T1[67200,67300,67150,67235]V1234 ..."
)
```

## หมายเหตุ

- ไฟล์ต้องเป็น encoding UTF-8
- หากไฟล์ไม่พบ โปรแกรมจะใช้ default template
- การแก้ไข prompt จะมีผลทันทีเมื่อรันโปรแกรมใหม่
