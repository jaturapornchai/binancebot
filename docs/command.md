# Binance Trading Bot - คู่มือการใช้งาน

## การตั้งค่าพารามิเตอร์ในไฟล์ app.py

```python
# เหรียญที่เทรด
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "LTCUSDT"]

# ช่วงเวลา Multi-timeframe
TIMEFRAME_1H = "1h"    # ภาพใหญ่
TIMEFRAME_15M = "15m"  # จุดเข้า

# ยอดเงินขั้นต่ำ
MIN_BALANCE_USDT = 100.0

# Leverage
LEVERAGE = 5

# จำนวนเงินต่อการเทรด
MARGIN_PER_TRADE_USDT = 100.0

# ช่วงเวลาการวนลูป (นาที)
SLEEP_MINUTES = 15
```

## การตั้งค่าโหมดเทรด

```python
# Force modes (สำหรับทดสอบ)
FORCE_BUY = False   # บังคับซื้อ
FORCE_SELL = False  # บังคับขาย

# AI Analysis
DEEPSEEK_ENABLED = True  # เปิด/ปิด AI
```

## 🔄 System Workflow

### การทำงานของระบบ

#### Step 1: รอบการทำงาน (ทุก 15 นาที)

Bot จะทำงานในลูปต่อไปนี้:

#### 1.1 LOOP1 - ตรวจสอบสถานะ

- ตรวจสอบ positions ที่เปิดอยู่
- ตรวจสอบยอดเงิน USDT

#### 1.2 LOOP2 - วิเคราะห์ positions เดิม

สำหรับแต่ละ position ที่เปิดอยู่:

- ดึงข้อมูลราคา **1h** (144 แท่ง) สำหรับ**ภาพใหญ่**
- ดึงข้อมูลราคา **15m** (144 แท่ง) สำหรับ**จุดเข้า**
- ส่งข้อมูลทั้ง 2 timeframe ให้ DeepSeek AI วิเคราะห์
- รับคำแนะนำ: CLOSE หรือ HOLD
- ดำเนินการตามคำแนะนำ

#### 1.3 LOOP3 - หา positions ใหม่

สำหรับเหรียญที่ไม่มี position:

- ตรวจสอบยอดเงิน USDT ถ้าน้อยกว่า $100 ให้รอรอบถัดไป เพราะไม่ต้องหาเหรียญต่อไป เงินหมด
- ดึงข้อมูลราคา **1h** (144 แท่ง) สำหรับ**ภาพใหญ่**
- ดึงข้อมูลราคา **15m** (144 แท่ง) สำหรับ**จุดเข้า**
- ส่งข้อมูลทั้ง 2 timeframe ให้ DeepSeek AI วิเคราะห์
- รับคำแนะนำ: LONG, SHORT หรือ HOLD
- เปิด position ใหม่ถ้าได้สัญญาณ

## การตัดสินใจของ AI

### สำหรับ Position เดิม

AI จะวิเคราะห์และตอบ JSON:

```json
{
  "action": "CLOSE" หรือ "HOLD",
  "confidence": 1-10,
  "reasoning": "เหตุผลรวมถึงสถานะ PNL",
  "patterns": ["pattern ที่พบ"]
}
```

### สำหรับ Position ใหม่

```json
{
  "action": "LONG" หรือ "SHORT" หรือ "HOLD", 
  "confidence": 1-10,
  "reasoning": "เหตุผลการตัดสินใจ",
  "patterns": ["pattern ที่พบ"]
}
```

## การดำเนินการ

- **LONG**: เปิด Long position
- **SHORT**: เปิด Short position  
- **CLOSE**: ปิด position ที่เปิดอยู่
- **HOLD**: ไม่ดำเนินการ

## การรันระบบ

### 1. เตรียมไฟล์ .env

```env
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret_key  
DEEPSEEK_API_KEY=your_deepseek_key
```

### 2. รันด้วย Docker (แนะนำ)

```bash
docker build -t binancebot .
docker run -d --name binancebot --env-file .env binancebot
```

### 3. รันด้วย Python

```bash
python app.py
```

### 4. ตรวจสอบสถานะ

```bash
# ดู logs
docker logs -f binancebot

# ดูสถานะ
docker ps

# หยุดระบบ
docker stop binancebot
```

## การทำงานต่อเนื่อง

- Bot รอจนถึงนาทีที่ 0, 15, 30, 45
- กลับไปทำ LOOP1 อีกรอบ
- ทำงาน 24/7 อย่างต่อเนื่อง

---

## หมายเหตุ

⚠️ **ใช้เงินจริง** - ระวังการตั้งค่า
🤖 **AI ตัดสินใจ** - DeepSeek วิเคราะห์ทุกการเทรด
🔄 **ทำงานต่อเนื่อง** - 24/7 ทุก 15 นาที
