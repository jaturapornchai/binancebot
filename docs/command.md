# กฏ
ใช้ time frame 1h ท├── หยุดถ้า Balance < $25
ดึงข้อมูลย้อนหลัง 500 time frame เพื่อวิเคราะห์ และส่งให้ ai
ใช้ Volume Spike Analysis ในการหาสัญญาณ (เพิ่มขึ้น 500% จากค่าเฉลี่ย)

# 📊 Volume Spike Trading Bot - Step การทำงาน

## 🔄 Main Process Flow

### 1. **Initialization & Setup**
```
🚀 Bot เริ่มต้น
├── โหลด Environment Variables (.env)
├── ตั้งค่า API Config (Binance + DeepSeek)
├── สร้าง Binance Futures Client
├── ตั้งค่า Trading Mode (CROSSED margin)
└── แสดงข้อมูล Config ($25 margin, 10x leverage)
```

### 2. **Balance & Position Check**
```
💰 Balance Management
├── ตรวจสอบ USDT Balance
├── ตรวจสอบ Position ที่มีอยู่
├── ตรวจสอบ Open Orders
└── หยุดถ้า Balance < $50
```

### 3. **Symbol Discovery**
```
🎲 Symbol Selection
├── ดึงรายการ Symbols ที่มี Volume > $10M
├── สุ่มลำดับ Symbols (shuffle)
├── กรองเอา Symbols ที่มี Position แล้วออก
└── เริ่มสแกน Symbol ทีละตัว
```

### 4. **Volume Spike Analysis**
```
📊 Volume Analysis per Symbol
├── ดึง OHLCV data 500 timeframes (1h)
├── Parse ข้อมูล Volume
├── คำนวณ Volume Statistics:
│   ├── Average Volume (200 periods)
│   ├── Current Volume
│   └── Volume Spike Ratio (Current/Average)
├── ตรวจสอบ Volume Spike ≥ 500% (5x):
│   ├── HIGH Strength: ≥ 1000% (10x)
│   ├── MEDIUM Strength: ≥ 700% (7x)
│   └── LOW Strength: 500-699% (5-6.9x)
└── ถ้าไม่เจอ Spike = HOLD
```

### 5. **AI Analysis & Decision**
```
🤖 AI Decision Making (เมื่อเจอ Volume Spike)
├── โหลด prompt_volume_analysis.txt
├── ส่งข้อมูล Volume Spike ไป DeepSeek
├── AI วิเคราะห์:
│   ├── Volume Spike Strength (HIGH/MEDIUM/LOW)
│   ├── Market Context & Timing
│   ├── Price Action around Volume Spike
│   ├── Support/Resistance Levels
│   └── Risk/Reward Ratio
├── AI ตอบ JSON:
│   ├── position: LONG/SHORT/HOLD
│   ├── confidence: 0-100%
│   ├── reasoning: เหตุผลภาษาไทย
│   ├── target_price: เป้าหมายกำไร
│   └── stop_loss_price: จุดตัดขาดทุน
└── Validate AI Response
```

### 6. **Trade Execution**
```
⚡ Trade Execution (ถ้า AI = LONG/SHORT)
├── ตรวจสอบ Balance อีกครั้ง ($25 minimum)
├── ตั้งค่า CROSSED margin mode
├── ตั้งค่า Leverage 10x
├── คำนวณ Quantity:
│   ├── Notional = $25 × 10x = $250
│   ├── Quantity = $250 ÷ Current Price
│   ├── ปรับตาม LOT_SIZE filter
│   └── ตรวจสอบ MIN_NOTIONAL
├── วาง Market Order (BUY/SELL)
├── ติดตาม Order Status จนเสร็จ
├── บันทึกผลการเทรด (JSON log)
└── ประกาศ Position เปิดสำเร็จ
```

### 8. **Position Protection System**
```
🛡️ Auto Cleanup & Protection (ทุก cycle - อัตโนมัติ)
├── **Auto Orphaned Orders Cleanup**:
│   ├── ตรวจสอบ Position ที่มีอยู่จริง
│   ├── เปรียบเทียบกับ Orders ที่มี
│   ├── หา Orders ที่ไม่มี Position (orphaned)
│   ├── ยกเลิก Orphaned Orders อัตโนมัติ
│   └── รายงานผลการ Cleanup
├── **Position Protection**:
│   ├── สแกนหา Position ที่ไม่มี SL/TP
│   ├── ส่งข้อมูล Position ไป AI
│   ├── AI กำหนด Stop Loss & Take Profit
│   ├── วาง STOP_MARKET order (SL)
│   ├── วาง TAKE_PROFIT_MARKET order (TP)
│   └── ยืนยันการสร้าง Protection
└── แสดง Portfolio Summary
```

### 9. **Cycle Management**
```
⏰ Cycle Control
├── แสดง Portfolio Status:
│   ├── Position Summary (Symbol, Side, PnL)
│   ├── Total Unrealized PnL
│   └── Account Balance
├── รอจนถึงนาทีแรกของชั่วโมงถัดไป
├── แสดง Countdown Timer
└── เริ่ม Cycle ใหม่
```

## 📈 Key Features

### **Linear Regression Channel System**
- **Single Timeframe**: 100-period regression analysis เพียงตัวเดียว
- **Smart Breakout Detection**: 12 timeframes ย้อนหลัง (ตรวจสอบการทะลุ channel)
- **Signal Types**: UPWARD/DOWNWARD/NONE classification
- **Trend Alignment**: UP/DOWN/SIDEWAYS trend direction

### **AI-Powered Decision Making**
- **DeepSeek Integration**: GPT-4 level analysis
- **Thai Language Reasoning**: เหตุผลภาษาไทย
- **Risk Management**: Stop Loss & Take Profit calculation
- **Context Awareness**: Market condition analysis

### **Risk Management**
- **$25 Margin per Trade**: ลดความเสี่ยงและ position size
- **10x Leverage**: Controlled leverage
- **Auto SL/TP**: AI-generated protection สำหรับทุก position
- **Auto Orphaned Order Cleanup**: ป้องกันและแก้ไข Orders ผิดพลาดอัตโนมัติ

### **Production Features**
- **Docker Deployment**: Containerized production
- **Auto Restart**: unless-stopped policy
- **24/7 Operation**: Thailand timezone
- **Real-time Logging**: Complete audit trail

## 🚨 Error Handling

### **API Errors**
```
❌ Error Scenarios
├── Binance API Rate Limits → Retry with backoff
├── DeepSeek API Timeout → Skip symbol, continue
├── Insufficient Balance → Stop scanning
├── Invalid Symbol Data → Skip to next symbol
└── Network Issues → Retry mechanism
```

### **Data Validation**
```
✅ Validation Steps
├── OHLCV Data completeness
├── Channel calculation validity
├── AI Response JSON format
├── Trade execution confirmation
└── Position protection verification
```

## 📊 Performance Monitoring

### **Trading Metrics**
- **Scan Rate**: Symbols scanned per cycle
- **Signal Rate**: % of symbols with signals
- **Execution Rate**: Successful trades per signals
- **Portfolio PnL**: Real-time profit/loss tracking

### **System Health**
- **API Response Times**: Binance + DeepSeek latency
- **Memory Usage**: Python process monitoring
- **Docker Status**: Container health checks
- **Log Analysis**: Error frequency tracking
