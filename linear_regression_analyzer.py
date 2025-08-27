"""
📈 Linear Regression Channel Analyzer
Based on Linear Regression Channel Pine Script by LonesomeTheBlue
Replaces Triangle Pattern Analysis system

Detects:
1. Channel breakouts (above/below regression bands)  
2. Trend changes (slope direction changes)
3. Channel strength and reliability
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum

class ChannelBreakout(Enum):
    NONE = "none"
    UPWARD = "upward"     # Price breaks above upper channel
    DOWNWARD = "downward" # Price breaks below lower channel

class TrendDirection(Enum):
    UP = "up"
    DOWN = "down" 
    SIDEWAYS = "sideways"

@dataclass
class LinearRegressionChannel:
    """Linear regression channel data"""
    intercept: float
    end_value: float
    deviation: float
    slope: float
    upper_channel: float
    lower_channel: float
    middle_line: float
    trend_direction: TrendDirection
    breakout_type: ChannelBreakout
    confidence: float

class LinearRegressionChannelAnalyzer:
    """Analyzes Linear Regression Channels for trading signals"""
    
    def __init__(self, length: int = 100, deviation_multiplier: float = 2.0):
        self.length = length
        self.deviation_multiplier = deviation_multiplier
        self.min_data_points = max(20, length)
        self.breakout_lookback = 12  # Look back 12 timeframes for breakout confirmation
        
    def analyze_channels(self, data: Dict) -> List[LinearRegressionChannel]:
        """Analyze price data for linear regression channels using only 100-period channel"""
        
        if not data or "closes" not in data or len(data["closes"]) < self.min_data_points:
            return []
            
        closes = np.array(data["closes"])
        volumes = np.array(data.get("volumes", [1] * len(closes)))
        highs = np.array(data.get("highs", closes))
        lows = np.array(data.get("lows", closes))
        
        channels = []
        
        # Use only 100-period channel
        if len(closes) >= 100:
            channel = self._calculate_channel(closes, highs, lows, volumes, 100)
            if channel:
                channels.append(channel)
                    
        return channels
    
    def _calculate_channel(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, volumes: np.ndarray, length: int) -> Optional[LinearRegressionChannel]:
        """Calculate linear regression channel for given period with simple breakout detection (no retest required)"""
        
        if len(closes) < length + self.breakout_lookback:
            return None
            
        # Get most recent data
        recent_closes = closes[-length:]
        recent_highs = highs[-length-self.breakout_lookback:]
        recent_lows = lows[-length-self.breakout_lookback:]
        recent_volumes = volumes[-length:] if len(volumes) >= length else np.ones(length)
        current_price = closes[-1]
        
        try:
            # Calculate linear regression
            x = np.arange(length)
            y = recent_closes
            
            # Calculate slope and intercept using least squares
            slope, intercept = np.polyfit(x, y, 1)
            
            # Calculate middle line values
            mid_start = intercept
            mid_end = intercept + slope * (length - 1)
            
            # Calculate standard deviation of residuals
            predicted = slope * x + intercept  
            residuals = y - predicted
            deviation = np.std(residuals)
            
            # Current position values
            current_middle = intercept + slope * (length - 1)
            upper_channel = current_middle + (deviation * self.deviation_multiplier)
            lower_channel = current_middle - (deviation * self.deviation_multiplier)
            
            # Determine trend direction
            trend_direction = self._get_trend_direction(slope)
            
            # Check for channel breakout with simple detection (no retest required)
            breakout_type = self._check_simple_breakout(
                recent_highs, recent_lows, current_price, 
                upper_channel, lower_channel, trend_direction
            )
            
            # Calculate confidence based on R-squared and volume
            confidence = self._calculate_confidence(y, predicted, recent_volumes)
            
            return LinearRegressionChannel(
                intercept=float(intercept),
                end_value=float(mid_end),
                deviation=float(deviation),
                slope=float(slope),
                upper_channel=float(upper_channel),
                lower_channel=float(lower_channel),
                middle_line=float(current_middle),
                trend_direction=trend_direction,
                breakout_type=breakout_type,
                confidence=float(confidence)
            )
            
        except Exception as e:
            print(f"❌ Error calculating channel: {e}")
            return None
    
    def _get_trend_direction(self, slope: float) -> TrendDirection:
        """Determine trend direction from slope"""
        if slope > 0.0001:  # Positive slope threshold
            return TrendDirection.UP
        elif slope < -0.0001:  # Negative slope threshold
            return TrendDirection.DOWN
        else:
            return TrendDirection.SIDEWAYS
    
    def _check_simple_breakout(self, highs: np.ndarray, lows: np.ndarray, current_price: float,
                              upper_channel: float, lower_channel: float, trend: TrendDirection) -> ChannelBreakout:
        """Check if price has broken out of the channel with simple detection (no retest required)"""
        
        # Get the last 12 timeframes for breakout analysis
        lookback_highs = highs[-self.breakout_lookback:] if len(highs) >= self.breakout_lookback else highs
        lookback_lows = lows[-self.breakout_lookback:] if len(lows) >= self.breakout_lookback else lows
        
        # Check for upward breakout - any high above upper channel in last 12 periods
        upward_breakout = any(high > upper_channel for high in lookback_highs)
        
        # Check for downward breakout - any low below lower channel in last 12 periods  
        downward_breakout = any(low < lower_channel for low in lookback_lows)
        
        # Determine final breakout type based on current price position
        if upward_breakout and current_price >= upper_channel * 0.995:
            return ChannelBreakout.UPWARD
        elif downward_breakout and current_price <= lower_channel * 1.005:
            return ChannelBreakout.DOWNWARD
        else:
            return ChannelBreakout.NONE
    
    def _calculate_confidence(self, actual: np.ndarray, predicted: np.ndarray, volumes: np.ndarray) -> float:
        """Calculate confidence based on R-squared and volume confirmation"""
        
        # R-squared calculation
        ss_res = np.sum((actual - predicted) ** 2)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        
        if ss_tot == 0:
            r_squared = 0.0
        else:
            r_squared = 1 - (ss_res / ss_tot)
        
        # Volume confirmation (simple average comparison)
        recent_vol_avg = np.mean(volumes[-10:]) if len(volumes) >= 10 else np.mean(volumes)
        older_vol_avg = np.mean(volumes[:-10]) if len(volumes) >= 20 else recent_vol_avg
        
        volume_factor = min(recent_vol_avg / (older_vol_avg + 1e-10), 2.0)  # Cap at 2x
        
        # Combine factors
        confidence = (r_squared * 0.7) + (min(volume_factor - 1, 1) * 0.3)
        return max(0.0, min(1.0, confidence))
    
    def get_trading_signals(self, channels: List[LinearRegressionChannel]) -> Dict:
        """Convert channels to trading signals"""
        
        if not channels:
            return {
                'signal': 'HOLD',
                'confidence': 0.0,
                'reason': 'No linear regression channels detected',
                'channels': []
            }
        
        # Find the best channel based on confidence and recent breakout
        best_channel = max(channels, key=lambda c: c.confidence)
        
        # Generate trading signal
        signal = 'HOLD'
        reason = 'No clear breakout signal'
        
        if best_channel.breakout_type == ChannelBreakout.UPWARD:
            if best_channel.trend_direction in [TrendDirection.UP, TrendDirection.SIDEWAYS]:
                signal = 'LONG'
                reason = f'Upward breakout from {best_channel.trend_direction.value} trending channel'
            else:
                signal = 'HOLD'
                reason = 'Upward breakout but in downtrend - conflicting signals'
                
        elif best_channel.breakout_type == ChannelBreakout.DOWNWARD:
            if best_channel.trend_direction in [TrendDirection.DOWN, TrendDirection.SIDEWAYS]:
                signal = 'SHORT'
                reason = f'Downward breakout from {best_channel.trend_direction.value} trending channel'
            else:
                signal = 'HOLD'
                reason = 'Downward breakout but in uptrend - conflicting signals'
        
        return {
            'signal': signal,
            'confidence': float(best_channel.confidence),
            'reason': reason,
            'target_price': self._calculate_target_price(best_channel),
            'stop_loss_price': self._calculate_stop_loss(best_channel),
            'channels': [self._channel_to_dict(c) for c in channels]
        }
    
    def _calculate_target_price(self, channel: LinearRegressionChannel) -> Optional[float]:
        """Calculate target price based on channel width and trend"""
        
        channel_width = channel.upper_channel - channel.lower_channel
        
        if channel.breakout_type == ChannelBreakout.UPWARD:
            # Target is one channel width above upper band
            return channel.upper_channel + channel_width
        elif channel.breakout_type == ChannelBreakout.DOWNWARD:
            # Target is one channel width below lower band  
            return channel.lower_channel - channel_width
        else:
            return None
    
    def _calculate_stop_loss(self, channel: LinearRegressionChannel) -> Optional[float]:
        """Calculate stop loss based on channel structure"""
        
        if channel.breakout_type == ChannelBreakout.UPWARD:
            # Stop loss below the middle line
            return channel.middle_line * 0.98  # 2% below middle line
        elif channel.breakout_type == ChannelBreakout.DOWNWARD:
            # Stop loss above the middle line
            return channel.middle_line * 1.02  # 2% above middle line
        else:
            return None
    
    def _channel_to_dict(self, channel: LinearRegressionChannel) -> Dict:
        """Convert channel to dictionary for JSON serialization"""
        return {
            'slope': channel.slope,
            'trend_direction': channel.trend_direction.value,
            'breakout_type': channel.breakout_type.value,
            'confidence': channel.confidence,
            'upper_channel': channel.upper_channel,
            'lower_channel': channel.lower_channel,
            'middle_line': channel.middle_line,
            'deviation': channel.deviation
        }
    
    def generate_summary(self, channels: List[LinearRegressionChannel]) -> str:
        """Generate human readable summary of channel analysis"""
        
        if not channels:
            return "📊 No regression channels detected"
        
        summary = f"📊 Detected {len(channels)} regression channel(s):\n\n"
        
        for i, channel in enumerate(channels, 1):
            breakout_emoji = {
                ChannelBreakout.UPWARD: "📈",
                ChannelBreakout.DOWNWARD: "📉", 
                ChannelBreakout.NONE: "⏸️"
            }
            
            trend_emoji = {
                TrendDirection.UP: "↗️",
                TrendDirection.DOWN: "↘️",
                TrendDirection.SIDEWAYS: "➡️"
            }
            
            summary += f"Channel {i}: {trend_emoji[channel.trend_direction]} {channel.trend_direction.value.upper()}\n"
            summary += f"└─ {breakout_emoji[channel.breakout_type]} {channel.breakout_type.value.upper()} BREAKOUT\n" if channel.breakout_type != ChannelBreakout.NONE else f"└─ ⏳ NO BREAKOUT\n"
            summary += f"└─ Confidence: {channel.confidence:.1%}\n"
            summary += f"└─ Range: ${channel.lower_channel:.6f} - ${channel.upper_channel:.6f}\n"
            
        return summary.strip()
