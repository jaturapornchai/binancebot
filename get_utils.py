#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import logging

class DataUtils:
    def __init__(self):
        self.logger = logging.getLogger("AltcoinMomentumScanner")
    
    def ensure_dataframe(self, data):
        """แปลงข้อมูลให้อยู่ในรูปแบบ DataFrame"""
        if data is None: 
            return pd.DataFrame()
        if isinstance(data, pd.DataFrame): 
            return data
        
        try:
            if isinstance(data, (list, np.ndarray)):
                if not data: 
                    return pd.DataFrame()
                
                if isinstance(data[0], (list, np.ndarray)):
                    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                            'close_time', 'quote_volume', 'trades', 'taker_buy_volume', 
                            'taker_buy_quote_volume', 'ignore']
                    
                    if len(data[0]) < len(cols): 
                        cols = cols[:len(data[0])]
                    
                    return pd.DataFrame(data, columns=cols)
                else: 
                    return pd.DataFrame([data])
            else: 
                return pd.DataFrame([data])
        except Exception as e:
            self.logger.error(f"ไม่สามารถแปลงข้อมูลเป็น DataFrame: {str(e)}")
            return pd.DataFrame()
    
    def prepare_dataframe(self, klines):
        """เตรียมข้อมูลแท่งเทียนในรูปแบบ DataFrame"""
        try:
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 
                'close_time', 'quote_volume', 'trades', 'taker_buy_volume', 
                'taker_buy_quote_volume', 'ignore'
            ])
            
            # แปลงคอลัมน์ตัวเลขเป็น numeric
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_volume', 
                            'taker_buy_volume', 'taker_buy_quote_volume']
            
            for col in numeric_cols: 
                df[col] = pd.to_numeric(df[col])
            
            # แปลงคอลัมน์เวลาเป็น datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            
            # แปลงคอลัมน์ trades เป็น int
            df['trades'] = df['trades'].astype(int)
            
            return df
        except Exception as e:
            self.logger.error(f"เกิดข้อผิดพลาดในการจัดเตรียม DataFrame: {str(e)}")
            return pd.DataFrame()