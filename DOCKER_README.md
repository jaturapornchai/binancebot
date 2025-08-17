# Running Binance Bot with Docker

This guide explains how to run the Binance trading bot using Docker Desktop.

## Prerequisites

- Docker Desktop installed and running
- Valid Binance API credentials
- Valid DeepSeek API key

## Quick Start

### Method 1: Using Docker Compose (Recommended)

1. **Build and run the container:**
   ```bash
   docker-compose up -d
   ```

2. **View logs:**
   ```bash
   docker-compose logs -f
   ```

3. **Stop the bot:**
   ```bash
   docker-compose down
   ```

### Method 2: Using Docker directly

1. **Build the image:**
   ```bash
   docker build -t binancebot .
   ```

2. **Run the container:**
   ```bash
   docker run -d --name binancebot --env-file .env binancebot
   ```

3. **View logs:**
   ```bash
   docker logs -f binancebot
   ```

4. **Stop and remove:**
   ```bash
   docker stop binancebot
   docker rm binancebot
   ```

## Configuration

The bot reads configuration from environment variables. Make sure your `.env` file contains:

```bash
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret_key
DEEPSEEK_API_KEY=your_deepseek_key
SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,LTCUSDT
# ... other settings
```

## Monitoring

- **Check container status:** `docker ps`
- **View real-time logs:** `docker-compose logs -f binancebot`
- **Container health:** `docker inspect binancebot --format='{{.State.Health.Status}}'`

## Troubleshooting

- **Container won't start:** Check logs with `docker-compose logs binancebot`
- **API errors:** Verify your API keys in `.env` file
- **Permission issues:** Ensure Docker Desktop is running with proper permissions

## Security Notes

- Never commit `.env` file with real API keys
- Use testnet for development: `BINANCE_TESTNET=true`
- Consider using Docker secrets for production deployments
