import os
import time
import re
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from datetime import datetime, timezone

class GateIOLRC15mScanner:
    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key:
            raise ValueError("Please set GATEIO_API_KEY and GATEIO_SECRET_KEY in .env file")
       
        self.client = ApiClient(Configuration(
            key=self.api_key,
            secret=self.secret_key,
            host="https://api.gateio.ws/api/v4"
        ))
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5
        self.order_amount = 40
        self.lrc_length = 100
        self.dev_multiplier = 2.0
        self.settle = 'usdt'

    def get_futures_contracts(self) -> list:
        try:
            tickers = self.futures_api.list_futures_tickers(settle='usdt')
            valid_contracts = []
            pattern = re.compile(r'^\D+_USDT$')
            ignore_contracts = ['DOGS_USDT', 'USDC_USDT', 'HEI_USDT']
           
            for ticker in tickers:
                contract = ticker.contract
                if (pattern.match(contract) and
                    contract not in ignore_contracts and
                    float(ticker.volume_24h) * float(ticker.last) > 2000000):
                    valid_contracts.append(contract)
            return valid_contracts
        except Exception as e:
            print(f"Error fetching contracts: {str(e)}", flush=True)
            return []

    def get_candlesticks(self, contract: str, limit: int = 100) -> pd.DataFrame:
        try:
            candles = self.futures_api.list_futures_candlesticks(
                settle='usdt',
                contract=contract,
                interval='15m',
                limit=limit
            )
            if not candles:
                return pd.DataFrame()
               
            df = pd.DataFrame([{
                'timestamp': float(c.t),
                'open': float(c.o),
                'high': float(c.h),
                'low': float(c.l),
                'close': float(c.c),
                'volume': float(c.v)
            } for c in candles])
           
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            return df.sort_values('timestamp')
        except Exception as e:
            print(f"Error fetching candlesticks for {contract}: {str(e)}", flush=True)
            return pd.DataFrame()

    def calculate_lrc(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.lrc_length:
            return df
           
        prices = df['close'].values
        x = np.arange(len(prices))
       
        A = np.vstack([x, np.ones(len(x))]).T
        slope, intercept = np.linalg.lstsq(A, prices, rcond=None)[0]
       
        mid_line = intercept + slope * x
        deviations = prices - mid_line
        std_dev = np.std(deviations) * self.dev_multiplier
       
        df['lrc_upper'] = mid_line + std_dev
        df['lrc_lower'] = mid_line - std_dev
        df['lrc_mid'] = mid_line
       
        return df.tail(1)

    def check_trading_signal(self, df: pd.DataFrame, current_price: float) -> str:
        if df.empty:
            return None
            
        latest = df.iloc[-1]
        
        # LONG signal: latest candle crosses upper band, current price above upper band
        if (latest['high'] >= latest['lrc_upper'] and
            current_price > latest['lrc_upper']):
            return "LONGX"
           
        # SHORT signal: latest candle crosses lower band, current price below lower band
        if (latest['low'] <= latest['lrc_lower'] and
            current_price < latest['lrc_lower']):
            return "SHORT"
           
        return None

    def check_close_position(self, df: pd.DataFrame, position_type: str, current_price: float, position: dict) -> bool:
        if df.empty:
            return False
            
        latest = df.iloc[-1]
        
        if position_type == "LONG" and current_price < latest['lrc_mid']:
            return True
        if position_type == "SHORT" and current_price > latest['lrc_mid']:
            return True
            
        return False

    def set_leverage(self, contract: str) -> bool:
        try:
            self.futures_api.update_position_leverage(
                contract=contract,
                settle='usdt',
                leverage=str(self.leverage)
            )
            return True
        except Exception as e:
            print(f"Error setting leverage: {str(e)}", flush=True)
            return False

    def get_latest_price(self, contract: str) -> float:
        try:
            ticker = self.futures_api.list_futures_tickers(settle='usdt')
            return float(next(t.last for t in ticker if t.contract == contract))
        except Exception:
            return None

    def check_existing_position(self, contract: str) -> dict:
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            return next((p for p in positions if p['contract'] == contract), None)
        except Exception as e:
            print(f"Error checking position: {str(e)}", flush=True)
            return None

    def close_position(self, contract: str, position: dict) -> bool:
        try:
            if not position:
                return False
               
            size = float(position['size'])
            if size != 0:
                self.futures_api.create_futures_order('usdt', {
                    'contract': contract,
                    'size': -size,
                    'price': 0,
                    'tif': 'ioc',
                    'reduce_only': True
                })
                print(f"Closed position for {contract} (size: {abs(size)})", flush=True)
                return True
            return False
        except Exception as e:
            print(f"Error closing position: {str(e)}", flush=True)
            return False

    def create_order(self, contract: str, size: float, is_long: bool) -> dict:
        try:
            existing = self.check_existing_position(contract)
            position_type = "LONG" if is_long else "SHORT"
           
            if existing:
                current_size = float(existing['size'])
                if (is_long and current_size < 0) or (not is_long and current_size > 0):
                    self.close_position(contract, existing)
                    time.sleep(2)
                elif (is_long and current_size > 0) or (not is_long and current_size < 0):
                    return None

            if not self.set_leverage(contract):
                return None
               
            price = self.get_latest_price(contract)
            contract_info = self.futures_api.get_futures_contract(
                contract=contract,
                settle='usdt'
            )
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
           
            usd_value = size * self.leverage
            contract_size = max(min_size, round(usd_value / (price * multiplier)))
           

            order = self.futures_api.create_futures_order('usdt', {
                'contract': contract,
                'size': contract_size if is_long else -contract_size,
                'price': 0,
                'tif': 'ioc',
                'reduce_only': False
            })
            print(f"Opened {position_type} position for {contract}", flush=True)
            return order
        except Exception as e:
            print(f"Error creating order: {str(e)}", flush=True)
            return None

    def scan_positions(self):
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            for pos in positions:
                contract = pos['contract']
                print(f"Scanning position for {contract}...", flush=True)
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df['contract'] = contract
                    df = self.calculate_lrc(df)
                    current_price = self.get_latest_price(contract)
                    
                    if current_price:
                        pos_type = "LONG" if float(pos['size']) > 0 else "SHORT"
                        if self.check_close_position(df, pos_type, current_price, pos):
                            self.close_position(contract, pos)
        except Exception as e:
            print(f"Error scanning positions: {str(e)}", flush=True)
                                  
    def get_futures_balance(self) -> dict:
        try:
            account = self.futures_api.list_futures_accounts(settle=self.settle)
            if not account:
                raise ValueError("No futures account found")
            balance_info = {
                'total': float(account.total or 0),
                'available': float(account.available or 0),
                'unrealized_pnl': float(account.unrealised_pnl or 0),
                'currency': account.currency or self.settle,
            }
            return balance_info
        except Exception as e:
            print(f"Error fetching futures balance: {str(e)}", flush=True)
            return None
        
    def scan_market(self):
        first_run = True
        while True:
            try:
                now = datetime.now(timezone.utc)
                if now.minute % 15 == 0 or first_run:                    
                    first_run = False
                    self.scan_positions()
                    balance_info = self.get_futures_balance()
                    print(f"Balance: {balance_info['total']} {balance_info['currency']} | "
                          f"Available: {balance_info['available']} {balance_info['currency']} | "
                          f"Unrealized PNL: {balance_info['unrealized_pnl']} {balance_info['currency']}", flush=True)
                    self.order_amount = balance_info['total'] / 75
                    print(f"Order amount: {self.order_amount}", flush=True)
                    
                    contracts = self.get_futures_contracts()
                   
                    for contract in contracts:
                        df = self.get_candlesticks(contract)
                        if not df.empty:
                            df = self.calculate_lrc(df)
                            current_price = self.get_latest_price(contract)
                            signal = self.check_trading_signal(df, current_price)
                           
                            if signal == "LONG":
                                self.create_order(contract, self.order_amount, True)
                            elif signal == "SHORT":
                                self.create_order(contract, self.order_amount, False)
                           
                            latest = df.iloc[-1]
                            print(f"{contract} | Close: {latest['close']} | "
                                  f"Upper: {latest['lrc_upper']} | "
                                  f"Lower: {latest['lrc_lower']} | "
                                  f"Mid: {latest['lrc_mid']} | "
                                  f"Signal: {signal or 'None'}", flush=True)
                    time.sleep(60)
                else:
                    if now.minute % 3 == 0:
                        if now.minute % 15 == 0:
                            first_run = True
                        else:
                            self.scan_positions()
                time.sleep(10)
               
            except Exception as e:
                print(f"Error in scan loop: {str(e)}", flush=True)
                time.sleep(60)

def main():
    scanner = GateIOLRC15mScanner()
    print("Starting 15m LRC futures scanner...", flush=True)
    scanner.scan_market()

if __name__ == "__main__":
    main()