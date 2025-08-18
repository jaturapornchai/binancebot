# 🚀 Binance Futures Trading Bot - Deployment Guide

## 📋 Prerequisites
- Python 3.8+
- Binance Futures API credentials
- DeepSeek API key
- Docker (optional for containerized deployment)

## 🔧 Environment Setup

### 1. Create `.env` file
```env
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_SECRET=your_binance_secret_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

## 🐳 Docker Deployment

### Build and run with Docker Compose
```bash
docker-compose up -d
```

### Or build manually
```bash
docker build -t binance-bot .
docker run -d --name binance-bot --env-file .env binance-bot
```

## 📊 Bot Configuration

The bot uses these default settings in `config.py`:
- **Timeframe**: 1h (hourly candles)
- **Leverage**: 5x
- **Margin per trade**: 100 USDT
- **Minimum volume**: 10M USDT
- **Balance threshold**: 100 USDT

## 🔄 Features

### Core Trading
- EMA-based signal detection
- AI-powered trade decisions via DeepSeek
- Automated SL/TP placement
- Position size calculation

### Position Management
- Automatic cleanup of incomplete positions
- Order management and cancellation
- Real-time PNL monitoring

### Risk Management
- Leverage control
- Balance monitoring
- Volume filtering
- Dynamic coin discovery

## 📝 Logs and Monitoring

The bot provides detailed logging:
- Position status and PNL
- Order executions
- Cleanup operations
- Error handling

## ⚠️ Important Notes

1. **Test Mode**: Always test with small amounts first
2. **API Permissions**: Ensure Futures trading is enabled
3. **Risk Management**: Never risk more than you can afford to lose
4. **Monitoring**: Keep an eye on positions and market conditions

## 🛠️ Troubleshooting

### Common Issues
- **API Errors**: Check credentials and permissions
- **Balance Issues**: Ensure sufficient USDT balance
- **Connection**: Verify internet connectivity
- **Dependencies**: Check Python version and packages

### Support
Check the logs for detailed error messages and debugging information.
