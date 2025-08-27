"""
Volume Analysis System
Detects high volume spikes (500% above average) for trading signals
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class VolumeSignal:
    """Volume analysis signal"""
    timestamp: int
    symbol: str
    current_volume: float
    average_volume: float
    volume_spike_ratio: float  # Current volume / Average volume
    price: float
    signal_strength: str  # "HIGH", "MEDIUM", "LOW"
    is_breakout_candidate: bool

class VolumeAnalyzer:
    """
    Advanced Volume Analysis for detecting significant volume spikes
    """
    
    def __init__(self, lookback_periods: int = 200, spike_threshold: float = 5.0):
        """
        Initialize Volume Analyzer
        
        Args:
            lookback_periods: Number of periods to calculate average volume
            spike_threshold: Volume spike threshold (5.0 = 500% increase)
        """
        self.lookback_periods = lookback_periods
        self.spike_threshold = spike_threshold
        
    def analyze_volume_spike(self, klines: List[List]) -> Optional[VolumeSignal]:
        """
        Analyze volume data for significant spikes
        
        Args:
            klines: List of klines data [timestamp, open, high, low, close, volume, ...]
            
        Returns:
            VolumeSignal if significant spike detected, None otherwise
        """
        try:
            if len(klines) < self.lookback_periods:
                logger.warning(f"Insufficient data for volume analysis. Need {self.lookback_periods}, got {len(klines)}")
                return None
                
            # Extract volume data
            volumes = [float(kline[5]) for kline in klines]
            prices = [float(kline[4]) for kline in klines]  # Close prices
            timestamps = [int(kline[0]) for kline in klines]
            
            # Calculate average volume (excluding current candle)
            historical_volumes = volumes[:-1]  # Exclude current candle
            average_volume = np.mean(historical_volumes[-self.lookback_periods:])
            
            # Current volume and price
            current_volume = volumes[-1]
            current_price = prices[-1]
            current_timestamp = timestamps[-1]
            
            # Calculate volume spike ratio
            volume_spike_ratio = current_volume / average_volume if average_volume > 0 else 0
            
            logger.info(f"Volume Analysis - Current: {current_volume:.2f}, Average: {average_volume:.2f}, Ratio: {volume_spike_ratio:.2f}x")
            
            # Check if volume spike meets threshold
            if volume_spike_ratio >= self.spike_threshold:
                signal_strength = self._determine_signal_strength(volume_spike_ratio)
                
                signal = VolumeSignal(
                    timestamp=current_timestamp,
                    symbol="",  # Will be set by caller
                    current_volume=current_volume,
                    average_volume=average_volume,
                    volume_spike_ratio=volume_spike_ratio,
                    price=current_price,
                    signal_strength=signal_strength,
                    is_breakout_candidate=True
                )
                
                logger.info(f"🔥 VOLUME SPIKE DETECTED! {volume_spike_ratio:.2f}x average volume ({signal_strength} strength)")
                return signal
            else:
                logger.info(f"Volume normal: {volume_spike_ratio:.2f}x (threshold: {self.spike_threshold}x)")
                return None
                
        except Exception as e:
            logger.error(f"Error in volume analysis: {e}")
            return None
    
    def _determine_signal_strength(self, volume_ratio: float) -> str:
        """
        Determine signal strength based on volume ratio
        
        Args:
            volume_ratio: Current volume / Average volume
            
        Returns:
            Signal strength: "HIGH", "MEDIUM", or "LOW"
        """
        if volume_ratio >= 10.0:  # 1000% increase
            return "HIGH"
        elif volume_ratio >= 7.0:  # 700% increase
            return "MEDIUM"
        else:  # 500-699% increase
            return "LOW"
    
    def get_volume_statistics(self, klines: List[List]) -> Dict:
        """
        Get volume statistics for analysis
        
        Args:
            klines: List of klines data
            
        Returns:
            Dictionary with volume statistics
        """
        try:
            if len(klines) < self.lookback_periods:
                return {}
                
            volumes = [float(kline[5]) for kline in klines]
            
            # Calculate statistics
            recent_volumes = volumes[-self.lookback_periods:]
            current_volume = volumes[-1]
            
            stats = {
                'current_volume': current_volume,
                'average_volume': np.mean(recent_volumes),
                'median_volume': np.median(recent_volumes),
                'max_volume': np.max(recent_volumes),
                'min_volume': np.min(recent_volumes),
                'volume_std': np.std(recent_volumes),
                'volume_spike_ratio': current_volume / np.mean(recent_volumes[:-1]) if len(recent_volumes) > 1 else 0
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating volume statistics: {e}")
            return {}
    
    def detect_volume_breakout(self, klines: List[List]) -> bool:
        """
        Simple method to detect if current volume indicates a breakout
        
        Args:
            klines: List of klines data
            
        Returns:
            True if volume breakout detected
        """
        signal = self.analyze_volume_spike(klines)
        return signal is not None and signal.is_breakout_candidate
