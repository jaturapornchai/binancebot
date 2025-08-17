
## 🔄 System Workflow

### การทำงานของระบบ (ทุก 1 ชั่วโมง)

```
┌──────────────────────────────────────────────────────────┐
│ 🕐 LOOP1: Time Sync (นาทีที่ 0)                          │
├──────────────────────────────────────────────────────────┤
│ 📊 LOOP2: Analyze Existing Positions                    │
│   - ตรวจสอบ positions ที่เปิดอยู่                        │
│   - ดึงข้อมูล 1h (144 bars)                             │
│   - ถาม AI: CLOSE หรือ HOLD?                            │
│   - ดำเนินการตามคำแนะนำ                                 │
├──────────────────────────────────────────────────────────┤
│ 🎯 LOOP3: Find New Opportunities                        │
│   - 🔍 ค้นหาเหรียญใน binance futures ที่มียอดซื้อขาย    │
│     24 ชม.ย้อนหลัง สูงกว่า $1,000,000                   │
│   - 🎲 สับไพ่เหรียญที่ค้นหาได้                           │
│   - ✅ ตรวจสอบเหรียญที่ไม่มี position                    │
│   - 📊 ดึงข้อมูล 1h (144 bars)                          │
│   - 🤖 ถาม AI: LONG/SHORT/HOLD?                         │
│   - 🚀 เปิด position ใหม่ถ้าได้สัญญาณ                   │
└──────────────────────────────────────────────────────────┘
```

### ⚡ ขั้นตอนการทำงาน

#### 1️⃣ LOOP1 - Time Synchronization
- รอจนถึงนาทีที่ 0 ของชั่วโมง
- เตรียมระบบสำหรับรอบการวิเคราะห์

#### 2️⃣ LOOP2 - Position Management

สำหรับแต่ละ position ที่เปิดอยู่:
- 📈 ดึงข้อมูลราคา **1h** (144 แท่ง)
- 🤖 ส่งข้อมูลให้ **DeepSeek AI** วิเคราะห์
- 📋 รับคำแนะนำ: **CLOSE** หรือ **HOLD**
- ⚡ ดำเนินการตามคำแนะนำ

#### 3️⃣ LOOP3 - Opportunity Discovery
**Advanced Coin Selection Process:**
- 🔍 **Dynamic Coin Discovery**: ค้นหาเหรียญใน Binance Futures ที่มี 24h volume > $1,000,000
- 🎲 **Random Shuffling**: สับไพ่เหรียญที่ผ่านเกณฑ์เพื่อกระจายโอกาส
- 💰 **Balance Check**: ตรวจสอบยอดเงิน USDT (ต้อง ≥ $100)
- ✅ **Position Filter**: เลือกเฉพาะเหรียญที่ไม่มี position อยู่
- 📊 **Technical Analysis**: ดึงข้อมูลราคา **1h** (144 แท่ง)
- 🧠 **AI Decision**: ส่งข้อมูลให้ **DeepSeek AI** วิเคราะห์  
- 🎯 **Signal Processing**: รับคำแนะนำ **LONG**, **SHORT** หรือ **HOLD**
- 🚀 **Position Opening**: เปิด position ใหม่ถ้าได้สัญญาณ

