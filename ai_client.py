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

def format_ohlcv_data(data, symbol="SYMBOL", timestamps=None):
    """Format raw OHLCV data with timestamps for AI - Send all 500 timeframes (no technical analysis)"""
    opens = data.get("opens", [])
    highs = data.get("highs", [])
    lows = data.get("lows", [])
    closes = data.get("closes", [])
    volumes = data.get("volumes", [])
    timestamps = data.get("timestamps", timestamps or [])
    
    if not opens or not highs or not lows or not closes or not volumes:
        return "No OHLCV data available"
    
    # Send all available data (500 timeframes) with timestamps
    all_data = []
    for i in range(len(opens)):
        if i < len(timestamps) and timestamps[i]:
            # Convert timestamp to readable format (Unix timestamp to datetime)
            try:
                from datetime import datetime
                timestamp = int(timestamps[i]) / 1000  # Convert from milliseconds
                dt = datetime.fromtimestamp(timestamp)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
                all_data.append(f"{time_str},{opens[i]:.4f},{highs[i]:.4f},{lows[i]:.4f},{closes[i]:.4f},{volumes[i]:.0f}")
            except:
                # Fallback without timestamp if conversion fails
                all_data.append(f"{opens[i]:.4f},{highs[i]:.4f},{lows[i]:.4f},{closes[i]:.4f},{volumes[i]:.0f}")
        else:
            # No timestamp available
            all_data.append(f"{opens[i]:.4f},{highs[i]:.4f},{lows[i]:.4f},{closes[i]:.4f},{volumes[i]:.0f}")
    
    ohlcv_text = "\n".join(all_data)
    
    # Return OHLCV data with timestamps - let AI do its own analysis
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
                         current_position: float = 0.0, pnl: float = 0.0, entry_price: float = 0.0, highest_24h: float = 0.0) -> Optional[Dict]:
    """
    🤖 Analyze trading opportunity using DeepSeek AI
    Returns parsed AI decision or None if error
    """
    if not api_cfg or not api_cfg.has_deepseek_credentials:
        print("! DeepSeek API key not configured")
        return None
    
    # Format OHLCV data
    ohlcv_data = format_ohlcv_data(data, symbol)
    
    # Use only prompt_new_position.txt template - no existing position analysis
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
        ohlcv_data=ohlcv_data
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
        print(f"📤 PROMPT SENT TO AI:")
        print(f"{user_prompt}")
        print(f"{'='*60}")
        
        print(f"🔗 Connecting to DeepSeek API (45s timeout)...")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a professional cryptocurrency futures trading expert specializing in swing trading and fast profit generation on 1-hour timeframe. Analyze price movements, trends, and risks to provide clear recommendations. You excel at identifying multi-day swing opportunities, optimal entry/exit points, and quick profit-taking strategies using 1h candle data. Focus on high-probability setups that can generate profits quickly within the 1-hour trading context. Respond only in JSON format."},
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
        print(f"   Symbol: {ai_data.get('symbol', 'N/A')}")
        print(f"   Action: {ai_data.get('action', 'UNKNOWN')}")
        print(f"   Reasoning: {ai_data.get('reasoning', 'N/A')}")
        
        # Show stop loss and take profit if provided
        stop_loss = ai_data.get('stop_loss', ai_data.get('sl', 0.0))
        take_profit = ai_data.get('take_profit', ai_data.get('tp', 0.0))
        
        if stop_loss and stop_loss != "N/A" and stop_loss > 0:
            print(f"   Stop Loss: ${stop_loss}")
        if take_profit and take_profit != "N/A" and take_profit > 0:
            print(f"   Take Profit: ${take_profit}")
        
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
            'patterns': ai_data.get('patterns', []),
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'buy_signal': buy_signal,
            'sell_signal': sell_signal
        }
        
    except json.JSONDecodeError as e:
        print(f"! JSON parse error for {symbol}: {str(e)}")
        print(f"! Error position: {e.pos if hasattr(e, 'pos') else 'unknown'}")
        print(f"! Attempted to parse JSON: {json_str[:100]}...")
        
        # Try to extract just the object without any surrounding text
        # Look for a more complete JSON pattern
        import re
        json_pattern = r'(\{[^}]*"action"[^}]*\})'
        match = re.search(json_pattern, content, re.DOTALL)
        if match:
            try:
                fallback_json = match.group(1)
                print(f"! Trying fallback JSON extraction: {fallback_json[:100]}...")
                ai_data = json.loads(fallback_json)
                action = ai_data.get('action', '').upper()
                print(f"✅ Fallback JSON parsing successful for {symbol}")
                return {
                    'action': action,
                    'reasoning': ai_data.get('reasoning', 'Fallback parsing'),
                    'patterns': ai_data.get('patterns', []),
                    'stop_loss': ai_data.get('stop_loss', ai_data.get('sl', 0.0)),
                    'take_profit': ai_data.get('take_profit', ai_data.get('tp', 0.0)),
                    'buy_signal': action == 'LONG',
                    'sell_signal': action == 'SHORT'
                }
            except:
                pass
        
        return None
    except Exception as e:
        print(f"! Error parsing AI response for {symbol}: {e}")
        return None


def get_position_protection_from_ai(symbol: str, side: str, entry_price: float, 
                                  current_price: float, position_size: float, 
                                  pnl: float, pnl_percent: float, data: Dict) -> Optional[Dict]:
    """
    Get Stop Loss and Take Profit levels from AI for existing position
    """
    if not api_cfg or not api_cfg.deepseek_api_key:
        print("! DeepSeek API key not configured")
        return None
    
    try:
        # Load prompt template
        prompt_path = "prompt_position_protection.txt"
        if not os.path.exists(prompt_path):
            print(f"! Prompt file not found: {prompt_path}")
            return None
            
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
        
        # Format OHLCV data
        formatted_ohlcv = format_ohlcv_data(data, symbol)
        
        # Create user prompt
        user_prompt = prompt_template.format(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            current_price=current_price,
            position_size=position_size,
            pnl=pnl,
            pnl_percent=pnl_percent,
            ohlcv_data=formatted_ohlcv
        )
        
        client = OpenAI(
            api_key=api_cfg.deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
            timeout=30.0
        )
        
        print(f"🛡️ Requesting SL/TP from AI for {symbol} {side} position...")
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a professional risk management expert specializing in setting optimal Stop Loss and Take Profit levels for cryptocurrency futures positions. Respond only in JSON format."},
                {"role": "user", "content": user_prompt}
            ],
            stream=False,
            temperature=0.2,
            max_tokens=500,
            top_p=0.8
        )
        
        content = ""
        choices = getattr(response, "choices", [])
        if choices:
            message = getattr(choices[0], "message", None)
            if message:
                content = getattr(message, "content", "") or ""
        
        if not content:
            print(f"❌ No content in AI response for {symbol}")
            return None
        
        # Parse JSON response
        try:
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                print(f"❌ No JSON found in AI response for {symbol}")
                return None
            
            json_str = content[json_start:json_end]
            ai_data = json.loads(json_str)
            
            stop_loss = float(ai_data.get('stop_loss', 0))
            take_profit = float(ai_data.get('take_profit', 0))
            reasoning = ai_data.get('reasoning', '')
            
            if stop_loss <= 0 or take_profit <= 0:
                print(f"❌ Invalid SL/TP from AI for {symbol}: SL={stop_loss}, TP={take_profit}")
                return None
            
            print(f"✅ AI Protection for {symbol}: SL=${stop_loss:.6f}, TP=${take_profit:.6f}")
            print(f"💡 Reasoning: {reasoning[:100]}...")  # Truncate long reasoning
            
            return {
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'reasoning': reasoning
            }
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"❌ Error parsing protection response for {symbol}: {e}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting protection from AI for {symbol}: {e}")
        return None


def get_ai_decision_triangle_pattern(symbol: str, triangle_data: Dict) -> Optional[Dict]:
    """
    🔺 Get AI decision based on Triangle Pattern analysis
    Uses Bualuang Securities triangle pattern methodology
    """
    if not api_cfg or not api_cfg.has_deepseek_credentials:
        print("! DeepSeek API key not configured")
        return None
        
    try:
        client = OpenAI(
            api_key=api_cfg.deepseek_api_key, 
            base_url="https://api.deepseek.com/v1",
            timeout=45.0  # 45 second timeout
        )
        
        # Load triangle pattern analysis prompt
        triangle_prompt_path = os.path.join(os.path.dirname(__file__), "prompt_triangle_analysis.txt")
        with open(triangle_prompt_path, 'r', encoding='utf-8') as f:
            triangle_prompt = f.read()
        
        # Format triangle analysis data for AI
        triangle_analysis = json.dumps(triangle_data, ensure_ascii=False, indent=2)
        
        # Create complete prompt with triangle data
        complete_prompt = triangle_prompt.replace('{triangle_analysis}', triangle_analysis)
        
        print(f"🔺 Getting AI decision for {symbol} triangle patterns...")
        
        response = client.chat.completions.create(
            model=cfg.ai_model,
            messages=[
                {"role": "system", "content": complete_prompt},
                {"role": "user", "content": f"Analyze these triangle patterns for {symbol} and provide trading decision in JSON format"}
            ],
            temperature=0.3,
            max_tokens=800,
            timeout=30
        )
        
        response_content = response.choices[0].message.content.strip()
        print(f"🤖 AI Triangle Response for {symbol}:")
        print(response_content)
        
        # Extract JSON from response
        try:
            # Try to find JSON in the response
            json_start = response_content.find('{')
            json_end = response_content.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_content[json_start:json_end]
                ai_decision = json.loads(json_str)
                
                # Validate required fields
                required_fields = ['position', 'confidence', 'reasoning']
                if all(field in ai_decision for field in required_fields):
                    print(f"✅ Valid AI triangle decision for {symbol}: {ai_decision.get('position')} ({ai_decision.get('confidence')}%)")
                    return ai_decision
                else:
                    print(f"❌ Missing required fields in AI response for {symbol}")
                    return None
            else:
                print(f"❌ No JSON found in AI response for {symbol}")
                return None
                
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing AI JSON response for {symbol}: {e}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting AI triangle decision for {symbol}: {e}")
        return None


def get_ai_decision_channel_pattern(symbol: str, channel_data: Dict) -> Optional[Dict]:
    """
    Get AI trading decision based on Linear Regression Channel analysis
    Uses Linear Regression Channel breakout methodology
    """
    if not api_cfg or not api_cfg.has_deepseek_credentials:
        print("! DeepSeek API key not configured")
        return None
        
    try:
        client = OpenAI(
            api_key=api_cfg.deepseek_api_key, 
            base_url="https://api.deepseek.com/v1",
            timeout=45.0  # 45 second timeout
        )
        
        # Load channel pattern analysis prompt
        channel_prompt_path = os.path.join(os.path.dirname(__file__), "prompt_channel_analysis.txt")
        with open(channel_prompt_path, 'r', encoding='utf-8') as f:
            channel_prompt = f.read()
        
        # Format channel analysis data for AI
        channel_analysis = json.dumps(channel_data, ensure_ascii=False, indent=2)
        
        # Create complete prompt with channel data
        complete_prompt = channel_prompt.replace('{channel_analysis}', channel_analysis)
        
        print(f"📊 Getting AI decision for {symbol} channel patterns...")
        
        response = client.chat.completions.create(
            model=cfg.ai_model,
            messages=[
                {"role": "system", "content": complete_prompt},
                {"role": "user", "content": f"Analyze these linear regression channels for {symbol} and provide trading decision in JSON format"}
            ],
            temperature=0.3,
            max_tokens=800,
            timeout=30
        )
        
        response_content = response.choices[0].message.content.strip()
        print(f"🤖 AI Channel Response for {symbol}:")
        print(response_content)
        
        # Extract JSON from response
        try:
            # Try to find JSON in the response
            json_start = response_content.find('{')
            json_end = response_content.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_content[json_start:json_end]
                ai_decision = json.loads(json_str)
                
                # Validate required fields
                required_fields = ['position', 'confidence', 'reasoning']
                if all(field in ai_decision for field in required_fields):
                    print(f"✅ Valid AI channel decision for {symbol}: {ai_decision.get('position')} ({ai_decision.get('confidence')}%)")
                    return ai_decision
                else:
                    print(f"❌ Missing required fields in AI response for {symbol}")
                    return None
            else:
                print(f"❌ No JSON found in AI response for {symbol}")
                return None
                
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing AI JSON response for {symbol}: {e}")
            return None
            
    except Exception as e:
        print(f"❌ Error getting AI channel decision for {symbol}: {e}")
        return None
