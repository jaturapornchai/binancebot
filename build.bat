@echo off
echo Building Binance Bot Docker image...
docker build -t binancebot .

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ Build successful!
    echo.
    echo To run the bot:
    echo   docker-compose up -d
    echo.
    echo To view logs:
    echo   docker-compose logs -f
) else (
    echo.
    echo ❌ Build failed!
)

pause
