# Binance Trading Bot with DeepSeek AI Integration

Automated Binance Futures trading bot powered by DeepSeek AI for intelligent market analysis and decision making.

## Features ✨

- **Real money trading** on Binance Futures (USDT-M)
- **AI-powered analysis** using DeepSeek API with deepseek-chat model
- **Enhanced Signal Detection System** for parsing Thai/English AI responses
- **Dual content extraction** supporting both `message.content` and `message.reasoning_content`
- **Compact OHLCV format** for token efficiency (144 timeframes = 36 hours)
- **Automated position management** with 5x leverage
- **Continuous loop operation** aligned to 15-minute intervals

## Quick Start 🚀

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` and fill in your API keys:
```bash
# Binance API Settings
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_SECRET_KEY=your_binance_secret_key_here

# DeepSeek AI Settings
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

### 3. Test DeepSeek Integration
```bash
python app.py
```

### 4. Run the Bot
```bash
python app.py
```

## How It Works 🤖

### Trading Logic Flow

1. **LOOP1**: Time synchronization (align to 0, 15, 30, 45 minutes)
2. **LOOP2**: Check existing positions → Ask AI to CLOSE or HOLD
3. **LOOP3**: Check coins without positions → Ask AI for LONG/SHORT/HOLD
4. **OPEN ORDER**: Execute trades with proper margin and leverage setup

### AI Integration

- **Language**: Thai communication with AI for cultural context
- **Model**: GLM-4.5 with thinking/reasoning enabled
- **Prompt**: Comprehensive market data in compact OHLCV format
- **Response**: Natural language (not JSON required)
- **Detection**: Enhanced keyword system for LONG/SHORT/HOLD/CLOSE signals

### Data Format

**Compact OHLCV**: `T{id}[O,H,L,C]V{volume}`
- 10 candles per line for readability
- 144 total timeframes (36 hours @ 15m)
- No colors or emojis for token efficiency

Example:
```
T1[117265.30,117290.10,117199.90,117235.20]V244 T2[117305.90,117380.50,117235.60,117265.40]V314 ...
```

## Enhanced Signal Detection 🎯

### Keywords (Thai/English)
- **LONG**: long, buy, ซื้อ, เปิดลอง, bullish
- **SHORT**: short, sell, ขาย, เปิดช็อต, bearish  
- **HOLD**: hold, รอ, ถือ, คงสถานะ, sideway
- **CLOSE**: close, ปิด, exit, ทำกำไร, ตัดขาดทุน

### Scoring System
- Each keyword match: +2 points
- Highest score wins
- Default action: HOLD

## Configuration ⚙️

| Setting | Default | Description |
|---------|---------|-------------|
| `SYMBOLS` | 6 major coins | Trading pairs |
| `TIMEFRAME` | 15m | Chart timeframe |
| `LEVERAGE` | 5x | Position leverage |
| `MARGIN_PER_TRADE_USDT` | $100 | Position size |
| `MIN_BALANCE_USDT` | $100 | Minimum balance threshold |

## Safety Features 🛡️

- **Isolated margin** mode for risk containment
- **One-way position** mode (no hedge)
- **Real-time balance** checks before trading  
- **Position conflict** prevention
- **Error handling** with retry mechanisms
- **Detailed logging** of all AI interactions

## Files Structure 📁

```
├── app.py                  # Main trading bot
├── requirements.txt        # Python dependencies
├── .env.example           # Environment template
├── app.py                  # Main trading bot
├── prompt_new_position.txt # AI prompt for new positions  
├── prompt_existing_position.txt # AI prompt for existing positions
├── docs/
│   └── command.md         # Complete specifications
└── README.md              # This file
```

## Rules & Compliance 📋

- ✅ Real money trading only
- ✅ No modification of `docs/` folder
- ✅ DeepSeek API (deepseek-chat model) for analysis
- ✅ Thai language AI communication
- ✅ Natural language AI responses (no JSON requirement)
- ✅ Enhanced Signal Detection System
- ✅ Display both prompt and response with reasoning
- ✅ AI-only decision making (no hardcoded rules)
- ✅ 144+ timeframes historical data
- ✅ Compact OHLCV format for token efficiency
- ✅ max_tokens=1000 for complete responses
- ✅ Dual content extraction support

## Testing 🧪

Run the comprehensive test:
```bash
python app.py
```

This will verify:
- DeepSeek API connectivity
- JSON response parsing
- Enhanced Signal Detection
- Compact OHLCV format parsing
- Thai language processing

## Troubleshooting 🔧

### Common Issues

1. **"No response content from DeepSeek"**
   - Check if `DEEPSEEK_API_KEY` is valid
   - The bot supports JSON response parsing with fallback

2. **Invalid API keys**
   - Ensure Binance API has Futures trading permissions
   - Verify DeepSeek API key is active

3. **Insufficient balance**
   - Check minimum USDT balance ($100 default)
   - Verify available margin for leveraged trading

### Debug Mode
Add environment variable for verbose logging:
```bash
DEBUG=true python app.py
```

## Disclaimer ⚠️

This bot trades with real money on live markets. Use at your own risk. Always test with small amounts first and understand the risks of leveraged trading.

---

Built with ❤️ using DeepSeek AI for intelligent crypto trading
