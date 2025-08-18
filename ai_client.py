"""
🤖 DeepSeek AI Client for Trading Analysis
Handles AI trading analysis and decision making
"""

import json
import os
from typing import Dict, Optional, Tuple

from openai import OpenAI
from ema_analysis import get_ema_analysis_text, format_ohlcv_data

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


def analyze_with_deepseek(symbol: str, data_1h: Dict, current_price: float, 
                         current_position: float = 0.0, pnl: float = 0.0) -> Optional[Dict]:
    """
    🤖 Analyze trading opportunity using DeepSeek AI
    Returns parsed AI decision or None if error
    """
    if not api_cfg or not api_cfg.has_deepseek_credentials:
        print("! DeepSeek API key not configured")
        return None
    
    # Generate EMA analysis text
    ema_color_info = get_ema_analysis_text(symbol, data_1h, current_price)
    
    # Format OHLCV data
    ohlcv_data = format_ohlcv_data(data_1h)
    
    # เลือก prompt template ตามสถานการณ์
    if abs(current_position) > 1e-12:
        # CASE 1: มี position อยู่แล้ว - ไม่ใช้แล้วตาม user request
        print(f"! Position exists for {symbol} but prompt_existing_position.txt was removed per user request")
        return None
    else:
        # CASE 2: ยังไม่มี position - ใช้ prompt_new_position.txt
        template = load_prompt_template("prompt_new_position.txt")
        if not template:
            print("❌ CRITICAL ERROR: prompt_new_position.txt not found!")
            print("🛑 System cannot continue without proper AI prompt templates")
            print("📁 Please ensure prompt_new_position.txt exists in the project directory")
            return None
        
        prompt = template.format(
            symbol=symbol,
            current_price=f"{current_price:.2f}",
            ema_color_info=ema_color_info,
            ohlcv_data=ohlcv_data
        )

    try:
        client = OpenAI(api_key=api_cfg.deepseek_api_key, base_url="https://api.deepseek.com/v1")
        print(f"🔗 Connecting to DeepSeek API...")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "คุณคือผู้เชี่ยวชาญด้านการเทรดคริปโตฯ ประสบการณ์มากกว่า 10 ปี วิเคราะห์ราคา แนวโน้ม และความเสี่ยง เพื่อให้คำแนะนำที่ชัดเจน ตอบในรูปแบบ JSON เท่านั้น"},
                {"role": "user", "content": prompt},
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

    except Exception as e:
        print(f"! DeepSeek API error for {symbol}: {e}")
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
        
        # Parse stop loss and take profit
        stop_loss = ai_data.get('stop_loss')
        take_profit = ai_data.get('take_profit')
        
        if stop_loss:
            try:
                stop_loss = float(stop_loss)
                print(f"   Stop Loss: ${stop_loss:.6f}")
            except (ValueError, TypeError):
                print(f"   Stop Loss: Invalid value - {stop_loss}")
                stop_loss = None
        
        if take_profit:
            try:
                take_profit = float(take_profit)
                print(f"   Take Profit: ${take_profit:.6f}")
            except (ValueError, TypeError):
                print(f"   Take Profit: Invalid value - {take_profit}")
                take_profit = None
        
        patterns = ai_data.get('patterns', [])
        if patterns:
            print(f"   Patterns: {patterns}")
        
        # Determine buy/sell signals
        action = ai_data.get('action', '').upper()
        buy_signal = action == 'LONG'
        sell_signal = action == 'SHORT'
        
        print(f"🤖 {symbol} AI decision: buy={buy_signal} sell={sell_signal}")
        
        return {
            'action': action,
            'reasoning': ai_data.get('reasoning', ''),
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'patterns': patterns,
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
