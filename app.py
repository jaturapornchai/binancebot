import json
import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, cast

from binance.um_futures import UMFutures
from dotenv import load_dotenv
from openai import OpenAI


def countdown_sleep(total_seconds: int, target_hour: int, reason: str = "Waiting"):
    """
    🕐 Real-time countdown display with live updates every second
    Shows dynamic countdown timer that refreshes every second until target time
    """
    if total_seconds <= 0:
        print("⏰ Already past the target time, continuing immediately")
        time.sleep(1)
        return
    
    # Convert to Thailand time (UTC+7)
    thailand_target_hour = (target_hour + 7) % 24
    print(f"\n{reason} until {thailand_target_hour:02d}:00:00 (Thailand Time)")                        # ดึงข้อมูลย้อนหลัง 1h (144 bars) สำหรับการวิเคราะห์    print("=" * 50)
    
    for remaining in range(int(total_seconds), 0, -1):
        minutes = remaining // 60
        seconds = remaining % 60
        hours = minutes // 60
        minutes = minutes % 60
        
        if hours > 0:
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            time_str = f"{minutes:02d}:{seconds:02d}"
            
        print(f"\r⏰ {reason}: {time_str} remaining...", end="", flush=True)
        time.sleep(1)
    
    print(f"\r⏰ {reason}: 00:00 - Time's up! Continuing...{' ' * 20}")
    print("=" * 50)


# --- Config and helpers -----------------------------------------------------


@dataclass
class Config:
    api_key: str
    api_secret: str
    timeframe: str
    min_balance_usdt: float
    leverage: int
    margin_per_trade_usdt: float
    min_volume_usdt: float
    force_buy: bool
    force_sell: bool
    deepseek_api_key: Optional[str]
    recv_window: int = 7000


def load_config() -> Config:
    load_dotenv()
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_SECRET_KEY", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("Missing BINANCE_API_KEY or BINANCE_SECRET_KEY in .env")

    return Config(
        api_key=api_key,
        api_secret=api_secret,
        timeframe=os.getenv("TIMEFRAME", "1h"),
        min_balance_usdt=float(os.getenv("MIN_BALANCE_USDT", "100")),
        leverage=int(os.getenv("LEVERAGE", "5")),
        margin_per_trade_usdt=float(os.getenv("MARGIN_PER_TRADE_USDT", "100")),
        min_volume_usdt=float(os.getenv("MIN_VOLUME_USDT", "10000000")),
        force_buy=os.getenv("FORCE_BUY", "false").lower() in ("1", "true", "yes"),
        force_sell=os.getenv("FORCE_SELL", "false").lower() in ("1", "true", "yes"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "sk-f90e70eaf46c4190925a787e94cafb4d").strip() or None,
    )


def retry_call(fn, *args, retries=3, backoff=1.5, **kwargs):
    last_exc = None
    delay = 0.6
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # broad to keep bot running
            last_exc = e
            time.sleep(delay)
            delay *= backoff
    if last_exc:
        raise last_exc


# --- Binance Futures helpers -------------------------------------------------

def ensure_one_way_mode(um: UMFutures):
    try:
        mode = retry_call(um.get_position_mode)
        if isinstance(mode, dict):
            dual = bool(mode.get("dualSidePosition", False))
            if dual:
                retry_call(um.change_position_mode, dualSidePosition=False)
                print("- Switched position mode to One-way")
    except Exception as e:
        # Non-fatal
        print(f"! Could not verify/set position mode: {e}")


def get_available_usdt(um: UMFutures) -> float:
    bals = retry_call(um.balance)
    if not isinstance(bals, list):
        return 0.0
    for b in bals:
        if isinstance(b, dict) and b.get("asset") == "USDT":
            try:
                return float(b.get("availableBalance", b.get("balance", 0.0)))
            except Exception:
                try:
                    return float(b.get("balance", 0.0))
                except Exception:
                    return 0.0
    return 0.0


def get_mark_price(um: UMFutures, symbol: str) -> float:
    data = retry_call(um.mark_price, symbol=symbol)
    try:
        if isinstance(data, dict):
            mp = data.get("markPrice", 0.0)
            return float(mp if mp is not None else 0.0)
    except Exception:
        pass
    # Fallback via ticker price if needed
    ticker = retry_call(um.ticker_price, symbol=symbol)
    if isinstance(ticker, dict):
        return float(ticker.get("price", 0.0))
    return 0.0


def get_exchange_filters(um: UMFutures) -> Dict[str, Dict[str, Any]]:
    info = retry_call(um.exchange_info)
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(info, dict):
        return out
    for s in info.get("symbols", []) or []:
        sym = s.get("symbol")
        filters_list = s.get("filters", []) or []
        filt: Dict[str, Any] = {cast(str, f.get("filterType")): f for f in filters_list if isinstance(f, dict) and isinstance(f.get("filterType"), str)}
        if isinstance(sym, str) and sym:
            out[sym] = filt
    return out


def get_high_volume_symbols(um: UMFutures, min_volume_usdt: float = 10_000_000) -> List[str]:
    """
    🔍 Dynamic Coin Discovery: ค้นหาเหรียญใน Binance Futures ที่มี 24h volume > $10,000,000
    🎲 Random Shuffling: สับไพ่เหรียญที่ผ่านเกณฑ์เพื่อกระจายโอกาส
    """
    try:
        # ดึงข้อมูล 24h ticker statistics
        tickers = retry_call(um.ticker_24hr_price_change)
        if not isinstance(tickers, list):
            print("! Failed to get 24h ticker data, no symbols available")
            return []
        
        high_volume_symbols = []
        
        for ticker in tickers:
            if not isinstance(ticker, dict):
                continue
                
            symbol = ticker.get("symbol", "")
            quote_volume = ticker.get("quoteVolume", "0")
            
            try:
                # ตรวจสอบว่าเป็น USDT pair และ volume สูงกว่าเกณฑ์
                if (symbol.endswith("USDT") and 
                    float(quote_volume) >= min_volume_usdt and
                    symbol not in ["USDCUSDT", "BUSDUSDT", "TUSDUSDT"]):  # หลีกเลี่ยง stablecoin pairs
                    
                    high_volume_symbols.append(symbol)
                    
            except (ValueError, TypeError):
                continue
        
        # เรียงลำดับตาม volume (สูงไปต่ำ)
        high_volume_symbols.sort(key=lambda x: float(
            next((t.get("quoteVolume", "0") for t in tickers if t.get("symbol") == x), "0")
        ), reverse=True)
        
        # 🎲 สับไพ่เหรียญที่ผ่านเกณฑ์ทั้งหมด
        random.shuffle(high_volume_symbols)
        
        print(f"🔍 Found {len(high_volume_symbols)} symbols with volume > ${min_volume_usdt:,.0f}")
        print(f"🎲 Shuffled all {len(high_volume_symbols)} symbols for trading")
        
        # ส่งคืน symbols ทั้งหมดที่ผ่านเกณฑ์
        return high_volume_symbols
        
    except Exception as e:
        print(f"! Error in get_high_volume_symbols: {e}")
        print("! No symbols available")
        return []


def get_1h_data(um: UMFutures, symbol: str, limit: int = 144) -> Dict[str, List[float]]:
    """Get OHLCV data for 1h timeframe only"""
    opens, highs, lows, closes, volumes = get_klines_data(um, symbol, "1h", limit)
    return {
        "opens": opens,
        "highs": highs, 
        "lows": lows,
        "closes": closes,
        "volumes": volumes
    }


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Calculate Exponential Moving Average (EMA) for 1h timeframe"""
    if not prices or len(prices) < 2:
        return []
    
    ema_values = []
    multiplier = 2 / (period + 1)
    
    # For EMA, we can start with the first price if we don't have enough data for SMA
    if len(prices) < period:
        # Use first price as initial EMA when insufficient data
        ema_values.append(prices[0])
        start_idx = 1
    else:
        # Start with SMA for the first value when we have enough data
        sma = sum(prices[:period]) / period
        ema_values.append(sma)
        start_idx = period
    
    # Calculate EMA for remaining values
    for i in range(start_idx, len(prices)):
        ema = (prices[i] * multiplier) + (ema_values[-1] * (1 - multiplier))
        ema_values.append(ema)
    
    return ema_values


def is_candle_crossing_ema99(symbol: str, data_1h: Dict[str, List[float]]) -> bool:
    """
    🔍 Technical Filter: Check EMA alignment and candle crossing EMA25
    Returns True if:
    1. EMA7 > EMA25 > EMA99 (uptrend) OR EMA7 < EMA25 < EMA99 (downtrend)
    2. Latest candle crosses EMA25 line
    Optimized for 1h timeframe with 144 bars (6 days) of data
    """
    try:
        closes = data_1h.get("closes", [])
        highs = data_1h.get("highs", [])
        lows = data_1h.get("lows", [])
        
        # Need at least 99 candles for EMA99 calculation
        if not closes or len(closes) < 99:
            print(f"    ❌ EMA Filter {symbol}: Insufficient data ({len(closes)} bars)")
            return False
            
        # Calculate all EMAs
        ema7_values = calculate_ema(closes, 7)
        ema25_values = calculate_ema(closes, 25)
        ema99_values = calculate_ema(closes, 99)
        
        if not ema7_values or not ema25_values or not ema99_values:
            print(f"    ❌ EMA Filter {symbol}: EMA calculation failed")
            return False
            
        # Get latest EMA values
        latest_ema7 = ema7_values[-1]
        latest_ema25 = ema25_values[-1]
        latest_ema99 = ema99_values[-1]
        latest_high = highs[-1]
        latest_low = lows[-1]
        latest_close = closes[-1]
        
        # Check EMA alignment: 7>25>99 (uptrend) or 7<25<99 (downtrend)
        uptrend_alignment = latest_ema7 > latest_ema25 > latest_ema99
        downtrend_alignment = latest_ema7 < latest_ema25 < latest_ema99
        ema_aligned = uptrend_alignment or downtrend_alignment
        
        # Check if candle crosses EMA25 (candle body or wick touches EMA25)
        candle_crosses_ema25 = (latest_low <= latest_ema25 <= latest_high)
        
        # Final decision: EMA aligned AND candle crosses EMA25
        filter_passed = ema_aligned and candle_crosses_ema25
        
        if filter_passed:
            trend = "uptrend" if uptrend_alignment else "downtrend"
            print(f"    ✅ EMA Filter {symbol}: {trend} alignment + candle crosses EMA25")
            print(f"       EMA7:{latest_ema7:.4f} EMA25:{latest_ema25:.4f} EMA99:{latest_ema99:.4f}")
            print(f"       Candle: H:{latest_high:.4f} L:{latest_low:.4f} C:{latest_close:.4f}")
        else:
            if not ema_aligned:
                print(f"    ❌ EMA Filter {symbol}: EMAs not aligned")
                print(f"       EMA7:{latest_ema7:.4f} EMA25:{latest_ema25:.4f} EMA99:{latest_ema99:.4f}")
            elif not candle_crosses_ema25:
                trend = "uptrend" if uptrend_alignment else "downtrend"
                print(f"    ❌ EMA Filter {symbol}: {trend} aligned but candle doesn't cross EMA25")
                print(f"       EMA25:{latest_ema25:.4f} Candle: H:{latest_high:.4f} L:{latest_low:.4f}")
            
        return filter_passed
        
    except Exception as e:
        print(f"    ⚠️ EMA calculation error {symbol}: {e}")
        return False


def get_klines_data(um: UMFutures, symbol: str, interval: str, limit: int = 144) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
    """Get OHLCV data from klines. Returns (opens, highs, lows, closes, volumes)"""
    klines = retry_call(um.klines, symbol=symbol, interval=interval, limit=limit)
    if not isinstance(klines, list):
        return ([], [], [], [], [])
    
    opens, highs, lows, closes, volumes = [], [], [], [], []
    for k in klines:
        if isinstance(k, list) and len(k) >= 6:
            try:
                opens.append(float(k[1]))    # open
                highs.append(float(k[2]))    # high
                lows.append(float(k[3]))     # low
                closes.append(float(k[4]))   # close
                volumes.append(float(k[5]))  # volume
            except (ValueError, TypeError):
                continue
    return (opens, highs, lows, closes, volumes)


def load_prompt_template(filename: str) -> str:
    """Load prompt template from file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"⚠️ Prompt file {filename} not found, using default template")
        return ""
    except Exception as e:
        print(f"⚠️ Error loading prompt file {filename}: {e}")
        return ""


def decide_signals_via_deepseek(symbol: str, data_1h: Dict[str, List[float]], api_key: str, current_position: float = 0.0, pnl: float = 0.0) -> Tuple[bool, bool, bool]:
    """Call DeepSeek to decide LONG/SHORT/CLOSE/HOLD from Thai prompt using 1h analysis.
    Returns (buy_sig, sell_sig, hold_sig). On error, returns (False, False, False).
    """
    # Guard: need enough data - send all to AI for analysis
    if not data_1h or len(data_1h.get("closes", [])) < 20:
        print("! Not enough price data for AI analysis")
        return (False, False, False)

    current_price = data_1h["closes"][-1]

    # สร้าง 1h OHLCV data text
    ohlcv_data = ""
    
    # 1h data only
    ohlcv_data += "=== 1H TIMEFRAME ===\n"
    h1_opens = data_1h["opens"]
    h1_highs = data_1h["highs"] 
    h1_lows = data_1h["lows"]
    h1_closes = data_1h["closes"]
    h1_volumes = data_1h["volumes"]
    
    min_len = min(len(h1_opens), len(h1_highs), len(h1_lows), len(h1_closes), len(h1_volumes))
    for i in range(min_len):
        ohlcv_data += f"H{i+1}[{h1_opens[i]},{h1_highs[i]},{h1_lows[i]},{h1_closes[i]}]V{int(h1_volumes[i])}"
        if (i + 1) % 10 == 0:
            ohlcv_data += "\n"
        else:
            ohlcv_data += " "
    ohlcv_data += "\n\n"
    
    # เลือก prompt template ตามสถานการณ์
    if abs(current_position) > 1e-12:
        # CASE 1: มี position อยู่แล้ว - ใช้ prompt_existing_position.txt
        template = load_prompt_template("prompt_existing_position.txt")
        if not template:
            # ถ้าไม่มี .txt ให้หยุดระบบ
            print("❌ CRITICAL ERROR: prompt_existing_position.txt not found!")
            print("🛑 System cannot continue without proper AI prompt templates")
            print("📁 Please ensure prompt_existing_position.txt exists in the project directory")
            raise SystemExit("Missing required prompt template file: prompt_existing_position.txt")

        pnl_status = "กำไร" if pnl > 0 else "ขาดทุน" if pnl < 0 else "เท่าทุน"
        position_type = "LONG" if current_position > 0 else "SHORT"
        
        prompt = template.format(
            symbol=symbol,
            current_price=f"{current_price:.2f}",
            ohlcv_data=ohlcv_data,
            position_type=position_type,
            position_size=f"{abs(current_position):.6f}",
            pnl=f"{pnl:.2f}",
            pnl_status=pnl_status
        )
    else:
        # CASE 2: ยังไม่มี position - ใช้ prompt_new_position.txt
        template = load_prompt_template("prompt_new_position.txt")
        if not template:
            # ถ้าไม่มี .txt ให้หยุดระบบ
            print("❌ CRITICAL ERROR: prompt_new_position.txt not found!")
            print("🛑 System cannot continue without proper AI prompt templates")
            print("📁 Please ensure prompt_new_position.txt exists in the project directory")
            raise SystemExit("Missing required prompt template file: prompt_new_position.txt")
        
        prompt = template.format(
            symbol=symbol,
            current_price=f"{current_price:.2f}",
            ohlcv_data=ohlcv_data
        )

    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
        print(f"🔗 Connecting to DeepSeek API...")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "คุณคือผู้เชี่ยวชาญด้านการเทรดคริปโตฯ ประสบการณ์มากกว่า 10 ปี วิเคราะห์ราคา แนวโน้ม และความเสี่ยง เพื่อให้คำแนะนำที่ชัดเจน ตอบในรูปแบบ JSON เท่านั้น"},
                {"role": "user", "content": prompt},
            ],
            stream=False,
            temperature=0.3,
            max_tokens=1000,  # เพิ่ม tokens เพื่อให้ AI ตอบได้ครบ
            top_p=0.8,
        )
        
        print(f"✅ DeepSeek Response received")

        print(f"\n{'='*60}")
        print(f"🤖 DEEPSEEK DETAILED ANALYSIS for {symbol}")
        print(f"{'='*60}")
        print(f"📤 PROMPT SENT TO AI (TH):")
        print(f"{prompt}")
        print(f"📥 AI RESPONSE:")

        content = ""
        reasoning_content = ""
        choices = getattr(response, "choices", [])
        if choices:
            message = getattr(choices[0], "message", None)
            if message:
                msg_content = getattr(message, "content", "") or ""
                reasoning_content = getattr(message, "reasoning_content", "") or ""
                
                # ใช้ msg_content หรือ reasoning_content ไหนก็ได้ที่มีเนื้อหา
                if msg_content.strip():
                    content = msg_content.strip()
                elif reasoning_content.strip():
                    content = reasoning_content.strip()
                    print("🔄 Using reasoning_content as main content")
                
                # แสดงทั้ง thinking และ response ตามข้อกำหนด
                if reasoning_content:
                    print("💭 AI THINKING/REASONING:")
                    print(f"{reasoning_content}")
                if msg_content:
                    print(f"\n📝 AI FINAL ANSWER:")
                    print(f"{msg_content}")
                elif content and content != reasoning_content:
                    print(f"\n📝 AI RESPONSE:")
                    print(f"{content}")
        
        # ตรวจสอบ response structure เพิ่มเติมถ้าไม่เจอ content
        if not content:
            print("🔍 DEBUG - Searching for content in alternative locations...")
            if hasattr(response, '__dict__'):
                available_attrs = [attr for attr in dir(response) if not attr.startswith('_')]
                print(f"🔍 Available attributes: {available_attrs}")
                
                # ลองดึงจาก attributes อื่นๆ
                for attr in ['text', 'content', 'data', 'result']:
                    if hasattr(response, attr):
                        alt_content = str(getattr(response, attr, '')).strip()
                        if alt_content:
                            content = alt_content
                            print(f"✅ Found content in response.{attr}")
                            break
                
        if not content:
            print("❌ No response content from DeepSeek - trying alternative extraction...")
            print(f"🔍 Response type: {type(response)}")
            print(f"🔍 Response: {str(response)[:300]}...")
            return (False, False, False)
        print(f"💲 Current Price: ${current_price:.4f}")
        if abs(current_position) > 1e-12:
            pos_type = "LONG" if current_position > 0 else "SHORT"
            print(f"🏦 Current Position: {pos_type} {abs(current_position):.6f}")

        final_action = "HOLD"
        # Try JSON first if AI returned JSON-like text
        try:
            # ลองหา JSON content ที่อาจจะถูกแต่งด้วย markdown หรือ text อื่น
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_content = content[json_start:json_end]
                parsed = json.loads(json_content)
                action = str(parsed.get("action", "")).upper()
                reasoning = parsed.get("reasoning", "")
                patterns = parsed.get("patterns", [])
                
                print(f"🎯 JSON Parsed Successfully:")
                print(f"   Action: {action}")
                print(f"   Reasoning: {reasoning}")
                print(f"   Patterns: {patterns}")
                
                if action in ("LONG", "SHORT", "HOLD", "CLOSE"):
                    final_action = action
            else:
                raise ValueError("No JSON found in response")
                
        except Exception as e:
            print(f"⚠️ JSON parsing failed: {e}")
            print("🔄 Falling back to text parsing...")
            # Fallback to text parsing with Enhanced Signal Detection
            text_lower = content.lower()
            scores = {"CLOSE": 0, "HOLD": 0, "LONG": 0, "SHORT": 0}

            # Enhanced Signal Detection Keywords (ตามข้อกำหนดใน command.md)
            keywords = {
                "LONG": ["long", "buy", "ซื้อ", "เปิดลอง", "bullish"],
                "SHORT": ["short", "sell", "ขาย", "เปิดช็อต", "bearish"],
                "HOLD": ["hold", "รอ", "ถือ", "คงสถานะ", "sideway"],
                "CLOSE": ["close", "ปิด", "exit", "ทำกำไร", "ตัดขาดทุน"]
            }

            # ให้คะแนน +2 สำหรับแต่ละคำที่พบ
            for action, terms in keywords.items():
                for term in terms:
                    if term in text_lower:
                        scores[action] += 2

            # เลือกสัญญาณที่ได้คะแนนสูงสุด
            max_score = max(scores.values())
            if max_score > 0:
                # หาคีย์ที่มีคะแนนสูงสุด
                for action, score in scores.items():
                    if score == max_score:
                        final_action = action
                        break
            else:
                final_action = "HOLD"  # ค่าเริ่มต้น

            # ปรับตรรกะสำหรับ position ที่มีอยู่
            if abs(current_position) > 1e-12:
                # มี position อยู่: เลือกระหว่าง CLOSE/HOLD
                if final_action == "CLOSE":
                    final_action = "CLOSE"
                else:
                    final_action = "HOLD"
            # ไม่มี position: ใช้ final_action ตามที่ AI แนะนำ

            print(f"🎯 Parsed Action: {final_action}")
            print(f"📊 Signal Scores: {scores}")
            print(f"{'='*60}\n")

        # Map action to signals
        if final_action == "HOLD" and abs(current_position) > 1e-12:
            return (False, False, True)
        if final_action == "CLOSE" and abs(current_position) > 1e-12:
            return (False, True, False) if current_position > 0 else (True, False, False)
        if final_action == "LONG":
            return (True, False, False)
        if final_action == "SHORT":
            return (False, True, False)
        return (False, False, False)

    except TimeoutError as e:
        print(f"⏰ DeepSeek API timeout: {e}")
        print("🔄 You may want to try again later or check your internet connection")
        return (False, False, False)
    except ConnectionError as e:
        print(f"🌐 DeepSeek connection error: {e}")
        print("🔄 Please check your internet connection and API endpoint")
        return (False, False, False)
    except Exception as e:
        print(f"❌ DeepSeek API error: {type(e).__name__}: {e}")
        print(f"🔍 Full error details: {str(e)}")
        return (False, False, False)


def floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    precision = max(0, int(round(-math.log10(step))))
    return math.floor(value / step) * step if precision == 0 else float(f"{math.floor(value / step) * step:.{precision}f}")


def round_qty_for_symbol(symbol: str, qty: float, filters: Dict[str, Dict[str, Any]]) -> Optional[float]:
    f = filters.get(symbol, {}) or {}
    lot = f.get("LOT_SIZE")
    if not isinstance(lot, dict):
        return qty
    step = float(lot.get("stepSize", 0.0001))
    min_qty = float(lot.get("minQty", 0))
    max_qty = float(lot.get("maxQty", 1e12))
    qty2 = max(min(floor_to_step(qty, step), max_qty), min_qty)
    if qty2 <= 0:
        return None
    return qty2


def meets_notional(symbol: str, qty: float, price: float, filters: Dict[str, Dict[str, Any]]) -> bool:
    f = filters.get(symbol, {}) or {}
    notional = f.get("NOTIONAL") or f.get("MIN_NOTIONAL")
    if not isinstance(notional, dict):
        return True
    min_notional = float(notional.get("notional", notional.get("minNotional", 0)))
    return (qty * price) >= min_notional


def current_position_amt(um: UMFutures, symbol: str) -> float:
    pos = retry_call(um.get_position_risk, symbol=symbol)
    # positionAmt string: positive for long, negative for short, 0 if flat
    try:
        if isinstance(pos, list):
            for p in pos:
                if p.get("symbol") == symbol:
                    return float(p.get("positionAmt", 0) or 0)
        elif isinstance(pos, dict):
            return float(pos.get("positionAmt", 0) or 0)
    except Exception:
        pass
    return 0.0


def get_position_pnl(um: UMFutures, symbol: str) -> float:
    """ดึงค่า unrealized PNL ของ position"""
    try:
        pos = retry_call(um.get_position_risk, symbol=symbol)
        if isinstance(pos, list):
            for p in pos:
                if p.get("symbol") == symbol:
                    return float(p.get("unRealizedProfit", 0) or 0)
        elif isinstance(pos, dict):
            return float(pos.get("unRealizedProfit", 0) or 0)
    except Exception as e:
        print(f"! Error getting PNL for {symbol}: {e}")
    return 0.0


def close_position_if_any(um: UMFutures, symbol: str, qty: float):
    amt = current_position_amt(um, symbol)
    if abs(amt) < 1e-12:
        return
    side = "SELL" if amt > 0 else "BUY"  # opposite side to close
    retry_call(
        um.new_order,
        symbol=symbol,
        side=side,
        type="MARKET",
        quantity=abs(amt),
        reduceOnly=True,
        newOrderRespType="RESULT",
    )
    print(f"- Closed existing position {symbol} amt={amt}")


def ensure_leverage(um: UMFutures, symbol: str, leverage: int):
    try:
        retry_call(um.change_leverage, symbol=symbol, leverage=leverage)
    except Exception as e:
        # Non-fatal if already set or restricted by bracket
        print(f"! change_leverage failed for {symbol}: {e}")


def ensure_isolated_margin(um: UMFutures, symbol: str):
    try:
        retry_call(um.change_margin_type, symbol=symbol, marginType="ISOLATED")
        print(f"- Set {symbol} to ISOLATED margin")
    except Exception as e:
        # Non-fatal if already set or not supported
        print(f"! change_margin_type failed for {symbol}: {e}")


def place_market_order(um: UMFutures, symbol: str, side: str, qty: float) -> Dict[str, Any]:
    res = retry_call(
        um.new_order,
        symbol=symbol,
        side=side,
        type="MARKET",
        quantity=qty,
        newOrderRespType="RESULT",
    )
    return res if isinstance(res, dict) else {}


# --- Main bot loop -----------------------------------------------------------

def run():
    cfg = load_config()
    um = UMFutures(key=cfg.api_key, secret=cfg.api_secret)

    print("Binance Futures bot started")
    print(json.dumps({
        "timeframe": cfg.timeframe,
        "min_balance_usdt": cfg.min_balance_usdt,
        "leverage": cfg.leverage,
        "margin_per_trade_usdt": cfg.margin_per_trade_usdt,
        "min_volume_usdt": cfg.min_volume_usdt,
        "dynamic_coin_discovery": True,
        "force_buy": cfg.force_buy,
        "force_sell": cfg.force_sell,
        "deepseek_enabled": bool(cfg.deepseek_api_key),
    }, indent=2))

    ensure_one_way_mode(um)
    filters = get_exchange_filters(um)
    
    first_run = True
    while True:
        try:
            # LOOP1: Time sync - align to hour (minute 0) if not first run
            if not first_run:
                now = datetime.now()
                if now.minute != 0:
                    print("Not at hour start (minute 0); sleeping 30s before LOOP1 checks…")
                    time.sleep(30)
                    continue
                    
            first_run = False

            # LOOP2: ดึง POSITION ที่เปิดอยู่ทั้งหมด และตัดสินใจปิดหรือถือไว้
            print("=== LOOP2: Checking existing positions ===")
            positions_to_close = []
            
            # ดึงรายการ positions ปัจจุบันจาก Binance
            try:
                all_positions = retry_call(um.get_position_risk)
                active_symbols = []
                
                if isinstance(all_positions, list):
                    for pos in all_positions:
                        if isinstance(pos, dict):
                            symbol = pos.get("symbol", "")
                            pos_amt = float(pos.get("positionAmt", 0) or 0)
                            if abs(pos_amt) > 1e-12:  # มี position อยู่
                                active_symbols.append(symbol)
                
                for symbol in active_symbols:
                    try:
                        current_pos = current_position_amt(um, symbol)
                        if abs(current_pos) > 1e-12:  # มี position อยู่
                            print(f"Found existing position: {symbol} amt={current_pos:.6f}")
                            
                            # คำนวณ PNL ปัจจุบัน
                            current_pnl = get_position_pnl(um, symbol)
                            
                            # ดึงข้อมูลย้อนหลัง 1h (144 bars)
                            data_1h = get_1h_data(um, symbol, limit=144)
                            
                            # ถาม AI ว่าควรปิดหรือถือไว้
                            if cfg.deepseek_api_key:
                                close_buy, close_sell, hold_sig = decide_signals_via_deepseek(symbol, data_1h, cfg.deepseek_api_key, current_pos, current_pnl)
                                
                                if close_buy or close_sell:
                                    print(f"- AI recommends CLOSING position {symbol} (PNL: {current_pnl:.2f})")
                                    positions_to_close.append((symbol, current_pos))
                                elif hold_sig:
                                    print(f"- AI recommends HOLDING position {symbol} (PNL: {current_pnl:.2f})")
                            else:
                                print(f"! No DeepSeek config - cannot analyze position {symbol}")
                                
                    except Exception as e:
                        print(f"! Error checking position {symbol}: {e}")
                        
            except Exception as e:
                print(f"! Error getting positions: {e}")
                    
            # ทำการปิด positions ตาม AI ที่แนะนำ
            for symbol, pos_amt in positions_to_close:
                try:
                    close_position_if_any(um, symbol, abs(pos_amt))
                    print(f"- Closed position {symbol} amt={pos_amt}")
                    time.sleep(1)
                except Exception as e:
                    print(f"! Error closing position {symbol}: {e}")

            # LOOP3: ตรวจสอบเหรียญที่ไม่มี position และตัดสินใจเปิดใหม่
            print("=== LOOP3: Checking coins for new positions ===")
            
            # ดึงยอดคงเหลือ
            avail = get_available_usdt(um)
            print(f"Available USDT: {avail:.2f}")
            if avail < cfg.min_balance_usdt:
                print("- Balance below threshold; waiting until next hour's first minute")
                
                # คำนวณเวลาที่ต้องรอให้ถึงนาทีแรกของชั่วโมงถัดไป
                now = time.time()
                current_time = time.localtime(now)
                
                # หาชั่วโมงถัดไป
                next_hour = (current_time.tm_hour + 1) % 24
                next_day = current_time.tm_mday
                next_month = current_time.tm_mon
                next_year = current_time.tm_year
                
                # ถ้าเป็น 23:xx จะเปลี่ยนเป็นวันถัดไป
                if current_time.tm_hour == 23:
                    import calendar
                    days_in_month = calendar.monthrange(next_year, next_month)[1]
                    if next_day == days_in_month:
                        next_day = 1
                        next_month += 1
                        if next_month > 12:
                            next_month = 1
                            next_year += 1
                    else:
                        next_day += 1
                
                # สร้างเวลาเป้าหมาย (นาทีแรกของชั่วโมงถัดไป)
                target_time = time.mktime((next_year, next_month, next_day, next_hour, 0, 0, 0, 0, -1))
                wait_seconds = target_time - now
                
                if wait_seconds > 0:
                    countdown_sleep(int(wait_seconds), next_hour, "💰 Insufficient balance")
                else:
                    print("⏰ Already past the target time, continuing immediately")
                    time.sleep(1)
                continue
            
            # 🔍 Dynamic Coin Discovery: ค้นหาเหรียญที่มี 24h volume > $1,000,000
            # 🎲 Random Shuffling: สับไพ่เหรียญที่ผ่านเกณฑ์เพื่อกระจายโอกาส
            dynamic_symbols = get_high_volume_symbols(um, min_volume_usdt=cfg.min_volume_usdt)
            
            for symbol in dynamic_symbols:
                symbol = "DOTUSDT"
                try:
                    # ดึงมาทีละ 1 เหรียญ ไม่เอาเหรียญที่มี POSITION อยู่
                    current_pos = current_position_amt(um, symbol)
                    if abs(current_pos) > 1e-12:
                        print(f"- Skipping {symbol} (has existing position)")
                        continue
                    
                    # ถาม AI ว่าควรเปิด POSITION ใหม่หรือไม่
                    if cfg.force_buy and cfg.force_sell:
                        buy_sig, sell_sig = True, True
                        print(f"{symbol} signals: buy={buy_sig} sell={sell_sig} (FORCED)")
                    elif cfg.force_buy:
                        buy_sig, sell_sig = True, False
                        print(f"{symbol} signals: buy={buy_sig} sell={sell_sig} (FORCED BUY)")
                    elif cfg.force_sell:
                        buy_sig, sell_sig = False, True
                        print(f"{symbol} signals: buy={buy_sig} sell={sell_sig} (FORCED SELL)")
                    else:
                        # ดึงข้อมูลย้อนหลัง 1h (288 bars) สำหรับการวิเคราะห์
                        data_1h = get_1h_data(um, symbol, limit=144)
                        
                        # 🔍 Technical Filter: เอาเฉพาะเหรียญที่ EMA เรียงกัน (7>25>99 หรือ 7<25<99) และแท่งเทียนทับ EMA25
                        if not is_candle_crossing_ema99(symbol, data_1h):
                            print(f"- Skipping {symbol} (EMA not aligned or candle doesn't cross EMA25)")
                            continue
                        
                        # ถาม AI สำหรับ position ใหม่ (เฉพาะเหรียญที่ผ่าน EMA alignment filter)
                        if cfg.deepseek_api_key:
                            buy_sig, sell_sig, _ = decide_signals_via_deepseek(symbol, data_1h, cfg.deepseek_api_key, 0.0, 0.0)
                            print(f"{symbol} new position signals: buy={buy_sig} sell={sell_sig} via DeepSeek")
                        else:
                            print(f"! No DeepSeek config found - no signals for {symbol}")
                            buy_sig, sell_sig = False, False

                    if not (buy_sig or sell_sig):
                        continue

                    # OPEN ORDER
                    mark = get_mark_price(um, symbol)
                    notional = cfg.margin_per_trade_usdt * cfg.leverage
                    raw_qty = notional / mark
                    qty = round_qty_for_symbol(symbol, raw_qty, filters)
                    
                    if qty is None or qty <= 0:
                        print(f"! Skipped {symbol}: qty invalid after rounding")
                        continue
                        
                    if not meets_notional(symbol, qty, mark, filters):
                        print(f"! Skipped {symbol}: below min notional (qty*price={qty*mark:.2f})")
                        continue

                    # Execute OPEN ORDER steps
                    close_position_if_any(um, symbol, qty)
                    ensure_isolated_margin(um, symbol)
                    ensure_leverage(um, symbol, cfg.leverage)

                    side = "BUY" if buy_sig else "SELL"
                    order = place_market_order(um, symbol, side, qty)
                    order_price = order.get("avgPrice", mark)
                    
                    print(f"- Placed {side} {symbol} qty={qty} -> status={order.get('status')} avg={order_price}")
                    print(json.dumps({
                        "symbol": symbol,
                        "side": "LONG" if side == "BUY" else "SHORT", 
                        "price": str(order_price)
                    }))

                    time.sleep(1)
                    
                except Exception as e:
                    print(f"! Error processing {symbol}: {e}")
                    time.sleep(1)
            
            print("=== Cycle complete - waiting until next hour's first minute ===")
            
            # คำนวณเวลาที่ต้องรอให้ถึงนาทีแรกของชั่วโมงถัดไป
            now = time.time()
            current_time = time.localtime(now)
            
            # หาชั่วโมงถัดไป
            next_hour = (current_time.tm_hour + 1) % 24
            next_day = current_time.tm_mday
            next_month = current_time.tm_mon
            next_year = current_time.tm_year
            
            # ถ้าเป็น 23:xx จะเปลี่ยนเป็นวันถัดไป
            if current_time.tm_hour == 23:
                import calendar
                days_in_month = calendar.monthrange(next_year, next_month)[1]
                if next_day == days_in_month:
                    next_day = 1
                    next_month += 1
                    if next_month > 12:
                        next_month = 1
                        next_year += 1
                else:
                    next_day += 1
            
            # สร้างเวลาเป้าหมาย (นาทีแรกของชั่วโมงถัดไป)
            target_time = time.mktime((next_year, next_month, next_day, next_hour, 0, 0, 0, 0, -1))
            wait_seconds = target_time - now
            
            if wait_seconds > 0:
                countdown_sleep(int(wait_seconds), next_hour, "⏰ Cycle complete")
            else:
                print("⏰ Already past the target time, continuing immediately")
                time.sleep(1)
            
        except Exception as e:
            print(f"! Main loop error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run()
