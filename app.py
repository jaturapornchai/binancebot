import os
import time
import re
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi
from datetime import datetime, timezone


class GateIOSmoothedHeikenAshi15mScanner:
    def __init__(self):
        # Load API credentials from .env file
        load_dotenv()
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key:
            raise ValueError("Please set GATEIO_API_KEY and GATEIO_SECRET_KEY in .env file")
        
        # Initialize Gate.io API client
        self.client = ApiClient(Configuration(
            key=self.api_key,
            secret=self.secret_key,
            host="https://api.gateio.ws/api/v4"
        ))
        self.futures_api = FuturesApi(self.client)
        
        # Trading parameters
        self.leverage = 5
        self.order_amount = 40  # Initial order size in USD
        self.len = 10   # Length for first EMA smoothing
        self.len2 = 10  # Length for second EMA smoothing
        self.settle = 'usdt'  # Settlement currency

    def get_futures_contracts(self) -> list:
        """Fetch a list of valid USDT-settled futures contracts."""
        try:
            tickers = self.futures_api.list_futures_tickers(settle='usdt')
            valid_contracts = []
            pattern = re.compile(r'^\D+_USDT$')
            ignore_contracts = ['DOGS_USDT', 'USDC_USDT', 'HEI_USDT']
            
            for ticker in tickers:
                contract = ticker.contract
                if (pattern.match(contract) and
                    contract not in ignore_contracts and
                    float(ticker.volume_24h) * float(ticker.last) > 5000000):
                    valid_contracts.append(contract)
            np.random.shuffle(valid_contracts)  # Randomize for variety
            return valid_contracts
        except Exception as e:
            print(f"Error fetching contracts: {str(e)}", flush=True)
            return []

    def get_candlesticks(self, contract: str, limit: int = 100) -> pd.DataFrame:
        """Fetch 15-minute candlestick data for a given contract."""
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

    def calculate_smoothed_heiken_ashi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Smoothed Heiken Ashi candles with double EMA smoothing."""
        if len(df) < self.len or len(df) < self.len2:
            return pd.DataFrame()
        
        # First EMA smoothing
        df['o_smooth'] = df['open'].ewm(span=self.len, adjust=False).mean()
        df['h_smooth'] = df['high'].ewm(span=self.len, adjust=False).mean()
        df['l_smooth'] = df['low'].ewm(span=self.len, adjust=False).mean()
        df['c_smooth'] = df['close'].ewm(span=self.len, adjust=False).mean()
        
        # Calculate Heiken Ashi
        df['ha_close'] = (df['o_smooth'] + df['h_smooth'] + df['l_smooth'] + df['c_smooth']) / 4
        df['ha_open'] = np.nan
        df.loc[df.index[0], 'ha_open'] = (df['o_smooth'].iloc[0] + df['c_smooth'].iloc[0]) / 2
        for i in range(1, len(df)):
            df.loc[df.index[i], 'ha_open'] = (df['ha_open'].iloc[i-1] + df['ha_close'].iloc[i-1]) / 2
        df['ha_high'] = df[['h_smooth', 'ha_open', 'ha_close']].max(axis=1)
        df['ha_low'] = df[['l_smooth', 'ha_open', 'ha_close']].min(axis=1)
        
        # Second EMA smoothing
        df['o2'] = df['ha_open'].ewm(span=self.len2, adjust=False).mean()
        df['h2'] = df['ha_high'].ewm(span=self.len2, adjust=False).mean()
        df['l2'] = df['ha_low'].ewm(span=self.len2, adjust=False).mean()
        df['c2'] = df['ha_close'].ewm(span=self.len2, adjust=False).mean()
        
        # Determine candle color
        df['color'] = np.where(df['o2'] > df['c2'], 'red', 'green')
        
        return df

    def get_signal(self, df: pd.DataFrame) -> str:
        """Generate trading signal based on candle colors."""
        if len(df) < 2:
            return None
        
        T1_color = df['color'].iloc[-1]  # Current candle
        T0_color = df['color'].iloc[-2]  # Previous candle
        
        if T1_color == 'green' and T0_color != 'green':
            return 'LONGX'
        elif T1_color == 'red' and T0_color != 'red':
            return 'SHORT'
        return None

    def check_close_position(self, df: pd.DataFrame, position_type: str) -> bool:
        """Check if an existing position should be closed."""
        if df.empty or len(df) < 15:  # Need at least 15 candles for 14-period lookback
            return False
        
        T1_color = df['color'].iloc[-1]
        current_price = df['close'].iloc[-1]
        
        if position_type == 'LONG':
            lowest_low = df['low'].iloc[-15:-1].min()
            return T1_color != 'green' or current_price < lowest_low
        elif position_type == 'SHORT':
            highest_high = df['high'].iloc[-15:-1].max()
            return T1_color != 'red' or current_price > highest_high
        return False

    def set_leverage(self, contract: str) -> bool:
        """Set leverage for a contract."""
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
        """Fetch the latest price for a contract."""
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
        """Close an existing position."""
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
            existing = self.check_existing_position(contract)
            position_type = "LONG" if is_long else "SHORT"
            
            # Handle existing positions
            if existing:
                current_size = float(existing['size'])
                if (is_long and current_size < 0) or (not is_long and current_size > 0):
                    # Close opposite position
                    self.close_position(contract, existing)
                    time.sleep(2)  # Wait to ensure position is closed
                elif (is_long and current_size > 0) or (not is_long and current_size < 0):
                    # Position already exists in the same direction
                    return None
            
            if not self.set_leverage(contract):
                return None
            
            # Calculate order size
            price = self.get_latest_price(contract)
            contract_info = self.futures_api.get_futures_contract(
                contract=contract,
                settle='usdt'
            )
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            
            usd_value = size * self.leverage
            contract_size = max(min_size, round(usd_value / (price * multiplier)))
            
            # Place order
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
        """Scan and manage existing positions."""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            for pos in positions:
                contract = pos['contract']
                print(f"Scanning position for {contract}...", flush=True)
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df = self.calculate_smoothed_heiken_ashi(df)
                    if not df.empty:
                        pos_type = "LONG" if float(pos['size']) > 0 else "SHORT"
                        if self.check_close_position(df, pos_type):
                            self.close_position(contract, pos)
        except Exception as e:
            print(f"Error scanning positions: {str(e)}", flush=True)

    def get_futures_balance(self) -> dict:
        """Fetch futures account balance."""
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
                    self.order_amount = balance_info['total'] / 75  # Adjust order size dynamically
                    print(f"Order amount: {self.order_amount}", flush=True)
                    
                    contracts = self.get_futures_contracts()
                    
                    for contract in contracts:
                        df = self.get_candlesticks(contract)
                        if not df.empty:
                            df = self.calculate_smoothed_heiken_ashi(df)
                            if len(df) >= 2:
                                signal = self.get_signal(df)
                                if signal == "LONG":
                                    self.create_order(contract, self.order_amount, True)
                                elif signal == "SHORT":
                                    self.create_order(contract, self.order_amount, False)
                                
                                latest = df.iloc[-1]
                                previous = df.iloc[-2]
                                print(f"{contract} | T1 Color: {latest['color']} | T0 Color: {previous['color']} | Signal: {signal or 'None'}", flush=True)
                    time.sleep(60)  # Wait after completing a scan
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                print(f"Error in scan loop: {str(e)}", flush=True)
                time.sleep(60)


def main():
    """Entry point for the trading system."""
    scanner = GateIOSmoothedHeikenAshi15mScanner()
    print("Starting 15m Smoothed Heiken Ashi futures scanner...", flush=True)
    scanner.scan_market()


if __name__ == "__main__":
    main()