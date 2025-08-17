# PowerShell script to manage Binance Bot Docker container
param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("start", "stop", "restart", "logs", "status", "build")]
    [string]$Action = "help"
)

function Show-Help {
    Write-Host "Binance Bot Docker Manager" -ForegroundColor Green
    Write-Host "Usage: .\manage-bot.ps1 [action]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Actions:" -ForegroundColor Cyan
    Write-Host "  start    - Start the bot container"
    Write-Host "  stop     - Stop the bot container"
    Write-Host "  restart  - Restart the bot container"
    Write-Host "  logs     - Show bot logs (real-time)"
    Write-Host "  status   - Show container status"
    Write-Host "  build    - Build/rebuild the Docker image"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Cyan
    Write-Host "  .\manage-bot.ps1 start"
    Write-Host "  .\manage-bot.ps1 logs"
}

switch ($Action.ToLower()) {
    "start" {
        Write-Host "🚀 Starting Binance Bot..." -ForegroundColor Green
        docker-compose up -d
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Bot started successfully!" -ForegroundColor Green
            Write-Host "Use '.\manage-bot.ps1 logs' to view logs" -ForegroundColor Yellow
        }
    }
    "stop" {
        Write-Host "🛑 Stopping Binance Bot..." -ForegroundColor Red
        docker-compose down
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Bot stopped successfully!" -ForegroundColor Green
        }
    }
    "restart" {
        Write-Host "🔄 Restarting Binance Bot..." -ForegroundColor Yellow
        docker-compose down
        docker-compose up -d
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Bot restarted successfully!" -ForegroundColor Green
        }
    }
    "logs" {
        Write-Host "📋 Showing bot logs (Ctrl+C to exit)..." -ForegroundColor Cyan
        docker-compose logs -f
    }
    "status" {
        Write-Host "📊 Container Status:" -ForegroundColor Cyan
        docker ps --filter "name=binancebot"
        Write-Host ""
        Write-Host "📊 Container Health:" -ForegroundColor Cyan
        $health = docker inspect binancebot --format='{{.State.Health.Status}}' 2>$null
        if ($health) {
            Write-Host "Health Status: $health" -ForegroundColor $(if ($health -eq "healthy") { "Green" } else { "Red" })
        }
        else {
            Write-Host "Container not running or health check not available" -ForegroundColor Yellow
        }
    }
    "build" {
        Write-Host "🔨 Building Docker image..." -ForegroundColor Blue
        docker build -t binancebot .
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Image built successfully!" -ForegroundColor Green
        }
    }
    default {
        Show-Help
    }
}
