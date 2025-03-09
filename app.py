import os
import time
import re
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from datetime import datetime, timezone

class GateIOLinearRegressionChannelScanner:
    def __init__(self):
        """Initialize the scanner with API credentials and default settings."""
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
        self.len = 100
        self.devlen = 2.0
        self.settle = 'usdt'

    def get_futures_contracts(self) -> list:
        """Retrieve a list of valid futures contracts with sufficient volume."""
        try:
            tickers = self.futures_api.list_futures_tickers(settle='usdt')
            valid_contracts = []
            pattern = re.compile(r'^\D+_USDT$')
            ignore_contracts = ['DOGS_USDT', 'USDC_USDT', 'HEI_USDT']
            
            for ticker in tickers:
                contract = ticker.contract
                if (pattern.match(contract) and
                    contract not in ignore_contracts and
                    float(ticker.volume_24h) * float(ticker.last) > 1000000):
                    valid_contracts.append(contract)
            np.random.shuffle(valid_contracts)
            return valid_contracts
        except Exception as e:
            print(f"Error fetching contracts: {str(e)}", flush=True)
            return []

    def get_candlesticks(self, contract: str, limit: int = 100) -> pd.DataFrame:
        """Fetch candlestick data for a given contract."""
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

    def get_linear_regression_channel(self, df: pd.DataFrame) -> dict:
        """Calculate the Linear Regression Channel for the given data."""
        if len(df) < self.len:
            return None
        
        src = df['close'].tail(self.len).values
        x = np.arange(self.len)
        slope, intercept = np.polyfit(x, src, 1)
        endy = intercept + slope * (self.len - 1)
        residuals = src - (slope * x + intercept)
        dev = np.std(residuals)
        
        T = endy + dev * self.devlen
        B = endy - dev * self.devlen
        
        return {'T': T, 'B': B, 'slope': slope}

    def set_leverage(self, contract: str) -> bool:
        """Set leverage for a specific contract."""
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
        """Get the latest price for a contract."""
        try:
            ticker = self.futures_api.list_futures_tickers(settle='usdt')
            return float(next(t.last for t in ticker if t.contract == contract))
        except Exception:
            return None

    def check_existing_position(self, contract: str) -> dict:
        """Check if there is an existing position for a contract."""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            return next((p for p in positions if p['contract'] == contract), None)
        except Exception as e:
            print(f"Error checking position: {str(e)}", flush=True)
            return None

    def close_position(self, contract: str, position: dict) -> bool:
        """Close an existing position for a contract."""
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
        """Create a new futures order."""
        try:
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
            print(f"Opened {'LONG' if is_long else 'SHORT'} position for {contract}", flush=True)
            return order
        except Exception as e:
            print(f"Error creating order: {str(e)}", flush=True)
            return None

    def scan_positions(self):
        """Scan and manage existing positions based on channel conditions."""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            # sort
            positions = sorted(positions, key=lambda x: x['contract'])
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                if not df.empty and len(df) >= self.len:
                    channel = self.get_linear_regression_channel(df)
                    if channel:
                        latest_price = self.get_latest_price(contract)
                        pos_size = float(pos['size'])
                        lowest_close_14 = df['close'].tail(28).min()
                        highest_close_14 = df['close'].tail(28).max()
                        latest_close = df['close'].iloc[-1]
                        print(f"{contract}... Latest Close: {latest_close:.4f} | Lowest Close 14: {lowest_close_14:.4f} | "
                              f"Highest Close 14: {highest_close_14:.4f}", flush=True)

                        if pos_size > 0:  # Long position
                            if latest_price < channel['B'] or latest_close < lowest_close_14:
                                print(f"Closing LONG position for {contract}: "
                                      f"Price {latest_price:.4f} < B {channel['B']:.4f} or "
                                      f"Close {latest_close:.4f} < Lowest Close 14 {lowest_close_14:.4f}", flush=True)
                                self.close_position(contract, pos)
                        elif pos_size < 0:  # Short position
                            if latest_price > channel['T'] or latest_close > highest_close_14:
                                print(f"Closing SHORT position for {contract}: "
                                      f"Price {latest_price:.4f} > T {channel['T']:.4f} or "
                                      f"Close {latest_close:.4f} > Highest Close 14 {highest_close_14:.4f}", flush=True)
                                self.close_position(contract, pos)
        except Exception as e:
            print(f"Error scanning positions: {str(e)}", flush=True)

        print("Position scan completed", flush=True)
        # new line
        print("", flush=True)
        

    def get_futures_balance(self) -> dict:
        """Retrieve the current futures account balance."""
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
        """Main loop to scan the market and execute trades."""
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
                    self.order_amount = balance_info['total'] / 100
                    print(f"Order amount: {self.order_amount}", flush=True)
                    
                    contracts = self.get_futures_contracts()
                    
                    for contract in contracts:
                        df = self.get_candlesticks(contract)
                        if not df.empty and len(df) >= self.len:
                            channel = self.get_linear_regression_channel(df)
                            if channel:
                                latest = df.iloc[-1]
                                latest_price = self.get_latest_price(contract)
                                is_green = latest['close'] > latest['open']
                                is_red = latest['close'] < latest['open']
                                high_touches_T = latest['high'] >= channel['T']
                                low_touches_B = latest['low'] <= channel['B']
                                
                                signal = None
                                if high_touches_T and is_green and latest_price > channel['T']:
                                    signal = "LONG"
                                elif low_touches_B and is_red and latest_price < channel['B']:
                                    signal = "SHORT"
                                
                                if signal:
                                    existing = self.check_existing_position(contract)
                                    if existing:
                                        pos_size = float(existing['size'])
                                        if (signal == "LONG" and pos_size < 0) or (signal == "SHORT" and pos_size > 0):
                                            self.close_position(contract, existing)
                                            time.sleep(2)
                                    
                                    if (signal == "LONG" and (not existing or pos_size <= 0)) or \
                                       (signal == "SHORT" and (not existing or pos_size >= 0)):
                                        is_long = signal == "LONG"
                                        self.create_order(contract, self.order_amount, is_long)
                                
                                print(f"{contract} | T: {channel['T']:.4f} | B: {channel['B']:.4f} | "
                                      f"Latest Price: {latest_price:.4f} | Signal: {signal or 'None'}", flush=True)
                    time.sleep(60)
                if now.minute % 3 == 0:
                    if now.minute % 15 == 0:
                        first_run = True
                    else:
                        self.scan_positions()
                        time.sleep(60)

                time.sleep(10)
            except Exception as e:
                print(f"Error in scan loop: {str(e)}", flush=True)
                time.sleep(60)

def main():
    """Entry point to start the scanner."""
    scanner = GateIOLinearRegressionChannelScanner()
    print("Starting 15m Linear Regression Channel futures scanner...", flush=True)
    scanner.scan_market()

if __name__ == "__main__":
    main()