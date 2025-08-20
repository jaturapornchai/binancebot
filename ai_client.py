"""
🤖 DeepSeek AI Client for Trading Analysis
Handles AI trading decision making with pure OHLCV data analysis
"""

import json
import os
from typing import Dict, Optional, Tuple

from openai import OpenAI
import openai

from config import cfg

def format_ohlcv_data(data, symbol="SYMBOL"):
    """Format raw OHLCV data for AI - Send all 288 timeframes (no technical analysis)"""
    opens = data.get("opens", [])
    highs = data.get("highs", [])
    lows = data.get("lows", [])
    closes = data.get("closes", [])
    volumes = data.get("volumes", [])
    
    if not opens or not highs or not lows or not closes or not volumes:
        return "No OHLCV data available"
    
    # Send all available data (288 timeframes) - Raw data only
    all_data = []
    for i in range(len(opens)):
        all_data.append(f"{opens[i]:.4f},{highs[i]:.4f},{lows[i]:.4f},{closes[i]:.4f},{volumes[i]:.0f}")
    
    ohlcv_text = "\n".join(all_data)
    
    # Return raw OHLCV data only - let AI do its own analysis
    return ohlcv_text

# Global API config - will be set by main
api_cfg = None

def set_api_config(config):
    """Set API configuration from main"""
    global api_cfg
    api_cfg = config


def load_prompt_template(filename: str) -> Optional[str]:
    """Load AI prompt template from file"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"! Prompt template {filename} not found")
        return None
    except Exception as e:
        print(f"! Error loading {filename}: {e}")
        return None


def analyze_with_deepseek(symbol: str, data: Dict, current_price: float, 
                         current_position: float = 0.0, pnl: float = 0.0, entry_price: float = 0.0) -> Optional[Dict]:
    """
    🤖 Analyze trading opportunity using DeepSeek AI
    Returns parsed AI decision or None if error
    """
    if not api_cfg or not api_cfg.has_deepseek_credentials:
        print("! DeepSeek API key not configured")
        return None
    
    # Format OHLCV data
    ohlcv_data = format_ohlcv_data(data, symbol)
    
    # เลือก prompt template ตามสถานการณ์
    if abs(current_position) > 1e-12:
        # CASE 1: มี position อยู่แล้ว - ใช้ prompt_existing_position.txt
        template = load_prompt_template("prompt_existing_position.txt")
        if not template:
            print(f"❌ CRITICAL ERROR: prompt_existing_position.txt not found!")
            print("🛑 Cannot analyze existing position without proper template")
            return None
        
        print(f"📄 Using prompt_existing_position.txt template for {symbol}")
            
        # Use the passed PNL or calculate if entry_price is provided
        calculated_pnl = pnl
        if entry_price and abs(entry_price) > 1e-12 and pnl == 0.0:
            calculated_pnl = (current_price - entry_price) * abs(current_position)
            
        pnl_percent = (calculated_pnl / (abs(current_position) * entry_price) * 100) if entry_price and abs(current_position * entry_price) > 1e-12 else 0
        side = "LONG" if current_position > 0 else "SHORT"
        
        user_prompt = template.format(
            symbol=symbol,
            side=side,
            entry_price=f"{entry_price:.6f}",
            current_price=f"{current_price:.6f}",
            pnl=calculated_pnl,
            pnl_percent=pnl_percent,
            ohlcv_data=ohlcv_data,
            timeframe=cfg.timeframe
        )
    else:
        # CASE 2: ยังไม่มี position - ใช้ prompt_new_position.txt
        template = load_prompt_template("prompt_new_position.txt")
        if not template:
            print("❌ CRITICAL ERROR: prompt_new_position.txt not found!")
            print("🛑 System cannot continue without proper AI prompt templates")
            print("📁 Please ensure prompt_new_position.txt exists in the project directory")
            return None
        
        print(f"📄 Using prompt_new_position.txt template for {symbol}")
        
        user_prompt = template.format(
            symbol=symbol,
            current_price=f"{current_price:.2f}",
            ohlcv_data=ohlcv_data,
            timeframe=cfg.timeframe
        )

    try:
        client = OpenAI(
            api_key=api_cfg.deepseek_api_key, 
            base_url="https://api.deepseek.com/v1",
            timeout=45.0  # 45 second timeout
        )
        
        # แสดง prompt ก่อนส่ง AI
        print(f"\n{'='*60}")
        print(f"🤖 SENDING PROMPT TO AI for {symbol}")
        print(f"{'='*60}")
        print(f"📤 PROMPT SENT TO AI (TH):")
        print(f"{user_prompt}")
        print(f"{'='*60}")
        
        print(f"🔗 Connecting to DeepSeek API (45s timeout)...")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "คุณคือผู้เชี่ยวชาญด้านการเทรดคริปโตฯ ตลาดฟิวเจอร์ วิเคราะห์ราคา แนวโน้ม และความเสี่ยง เพื่อให้คำแนะนำที่ชัดเจน ตอบในรูปแบบ JSON เท่านั้น"},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            temperature=0.3,
            max_tokens=1000,
            top_p=0.8,
        )
        
        print(f"✅ DeepSeek Response received")

        print(f"\n{'='*60}")
        print(f"🤖 DEEPSEEK DETAILED ANALYSIS for {symbol}")
        print(f"{'='*60}")
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
                    content = msg_content
                elif reasoning_content.strip():
                    content = reasoning_content
                    
                if reasoning_content.strip():
                    print(f"\n📝 AI REASONING:")
                    print(f"{reasoning_content}")

        if not content:
            print("! No content in DeepSeek response")
            return None

        print(f"\n📝 AI FINAL ANSWER:")
        print(f"{content}")

        # Parse JSON from AI response
        parsed_decision = parse_ai_response(content, current_price, symbol)
        return parsed_decision

    except openai.APITimeoutError as e:
        print(f"⏰ DeepSeek API timeout for {symbol}: {e}")
        print(f"🔄 API call took longer than 45 seconds")
        return None
    except openai.APIConnectionError as e:
        print(f"🌐 DeepSeek API connection error for {symbol}: {e}")
        print(f"🔄 Please check network connectivity")
        return None
    except openai.RateLimitError as e:
        print(f"⚠️ DeepSeek API rate limit for {symbol}: {e}")
        print(f"🔄 Please wait before making another request")
        return None
    except openai.APIError as e:
        print(f"🔥 DeepSeek API error for {symbol}: {e}")
        print(f"🔄 API returned an error")
        return None
    except TimeoutError as e:
        print(f"⏰ Network timeout for {symbol}: {e}")
        return None
    except ConnectionError as e:
        print(f"🌐 Network connection error for {symbol}: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error for {symbol}: {e}")
        print(f"🔄 Error type: {type(e).__name__}")
        return None


def parse_ai_response(content: str, current_price: float, symbol: str = "UNKNOWN") -> Optional[Dict]:
    """
    Parse AI response and extract trading decision
    Returns parsed decision dictionary or None if parsing fails
    """
    try:
        # Extract JSON from response
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        
        if json_start == -1 or json_end == 0:
            print("! No JSON found in AI response")
            return None
        
        json_str = content[json_start:json_end]
        ai_data = json.loads(json_str)
        
        print(f"💲 Current Price: ${current_price:.4f}")
        print(f"🎯 JSON Parsed Successfully:")
        print(f"   Action: {ai_data.get('action', 'UNKNOWN')}")
        print(f"   Reasoning: {ai_data.get('reasoning', 'N/A')}")
        print(f"   Confidence: {ai_data.get('confidence', 'N/A')}")
        
        patterns = ai_data.get('patterns', [])
        if patterns:
            print(f"   Patterns: {patterns}")
        
        market_condition = ai_data.get('market_condition')
        if market_condition:
            print(f"   Market Condition: {market_condition}")
        
        # Determine buy/sell signals
        action = ai_data.get('action', '').upper()
        buy_signal = action == 'LONG'
        sell_signal = action == 'SHORT'
        
        print(f"🤖 {symbol} AI decision: buy={buy_signal} sell={sell_signal}")
        
        return {
            'action': action,
            'reasoning': ai_data.get('reasoning', ''),
            'confidence': ai_data.get('confidence', 'N/A'),
            'patterns': patterns,
            'market_condition': market_condition,
            'buy_signal': buy_signal,
            'sell_signal': sell_signal
        }
        
    except json.JSONDecodeError as e:
        print(f"! JSON parse error: {e}")
        print(f"! Raw content: {content[:200]}...")
        return None
    except Exception as e:
        print(f"! Error parsing AI response: {e}")
        return None
