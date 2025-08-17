# 🚀 Binance Trading Bot Deployment Guide

## Quick Deployment (4 Commands Only)

### 1. Build & Push
```bash
docker buildx build --platform linux/amd64 -t jaturapornchai/binancebot:amd64 . --push
```

### 2. Deploy to Server
```bash
ssh root@178.128.55.234 "docker pull jaturapornchai/binancebot:amd64 && docker stop binancebot; docker rm binancebot; docker run -d --name binancebot --restart unless-stopped jaturapornchai/binancebot:amd64"
```

### 3. Check Bot Status
```bash
ssh root@178.128.55.234 "docker ps -a"
```

### 4. View Bot Logs
```bash
ssh root@178.128.55.234 "docker logs binancebot -f"
```

**Done! Your bot is now running on the server.**
