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
        """Initialize the scanner with API credentials from .env file."""
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
        self.settle = 'usdt'

    def get_futures_contracts(self) -> list:
        """Fetch a list of valid futures contracts with sufficient trading volume."""
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
            np.random.shuffle(valid_contracts)
            return valid_contracts
        except Exception as e:
            print(f"Error fetching contracts: {str(e)}", flush=True)
            return []

    def get_candlesticks(self, contract: str, limit: int = 100) -> pd.DataFrame:
        """Retrieve 15-minute candlestick data for a given contract."""
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

    def calculate_heikin_ashi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Heikin Ashi candlestick values from regular OHLC data."""
        ha_df = df.copy()
        ha_df['HA_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
        
        ha_df['HA_open'] = df['open'].copy()
        
        for i in range(1, len(df)):
            ha_df.loc[ha_df.index[i], 'HA_open'] = (
                ha_df.loc[ha_df.index[i-1], 'HA_open'] + ha_df.loc[ha_df.index[i-1], 'HA_close']
            ) / 2
        
        ha_df['HA_high'] = ha_df[['high', 'HA_open', 'HA_close']].max(axis=1)
        ha_df['HA_low'] = ha_df[['low', 'HA_open', 'HA_close']].min(axis=1)
        
        return ha_df

    def check_trading_signal(self, ha_df: pd.DataFrame) -> str:
        """Determine the trading signal based on the latest Heikin Ashi candles."""
        if len(ha_df) < 2:
            return None
         
        latest = ha_df.iloc[-1]  # T1
        previous = ha_df.iloc[-2]  # T0
     
        if latest['HA_close'] > latest['HA_open'] and previous['HA_close'] < previous['HA_open']:
            return "LONG"
        elif latest['HA_close'] < latest['HA_open'] and previous['HA_close'] > previous['HA_open']:
            return "SHORT"
         
        return None

    def check_close_position(self, ha_df: pd.DataFrame, position: dict) -> bool:
        """Check if an existing position should be closed based on Heikin Ashi reversal."""
        if ha_df.empty:
            return False
         
        latest = ha_df.iloc[-1]
        pos_type = "LONG" if float(position['size']) > 0 else "SHORT"
     
        if pos_type == "LONG" and latest['HA_close'] < latest['HA_open']:
            return True
        if pos_type == "SHORT" and latest['HA_close'] > latest['HA_open']:
            return True
         
        return False

    def set_leverage(self, contract: str) -> bool:
        """Set the leverage for a specific contract."""
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
        """Get the latest price for a given contract."""
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
        """Create a new futures order (LONG or SHORT)."""
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
            position_type = "LONG" if is_long else "SHORT"
            print(f"Opened {position_type} position for {contract}", flush=True)
            return order
        except Exception as e:
            print(f"Error creating order: {str(e)}", flush=True)
            return None

    def scan_positions(self):
        """Scan and manage existing positions based on Heikin Ashi signals."""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            for pos in positions:
                contract = pos['contract']
                print(f"Scanning position for {contract}...", flush=True)
                df = self.get_candlesticks(contract)
                if not df.empty:
                    ha_df = self.calculate_heikin_ashi(df)
                    if self.check_close_position(ha_df, pos):
                        self.close_position(contract, pos)
        except Exception as e:
            print(f"Error scanning positions: {str(e)}", flush=True)

    def get_futures_balance(self) -> dict:
        """Retrieve the futures account balance."""
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
        """Main loop to scan the market and execute trades every 15 minutes."""
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
                            ha_df = self.calculate_heikin_ashi(df)
                            signal = self.check_trading_signal(ha_df)
                             
                            existing = self.check_existing_position(contract)
                            if signal == "LONG":
                                if existing and float(existing['size']) < 0:  # Has SHORT position
                                    self.close_position(contract, existing)
                                    time.sleep(2)
                                if not existing or float(existing['size']) == 0:
                                    self.create_order(contract, self.order_amount, True)
                            elif signal == "SHORT":
                                if existing and float(existing['size']) > 0:  # Has LONG position
                                    self.close_position(contract, existing)
                                    time.sleep(2)
                                if not existing or float(existing['size']) == 0:
                                    self.create_order(contract, self.order_amount, False)
                             
                            latest = ha_df.iloc[-1]
                            print(f"{contract} | HA_Close: {latest['HA_close']} | "
                                  f"HA_Open: {latest['HA_open']} | Signal: {signal or 'None'}", flush=True)
                    time.sleep(60)
                else:
                    time.sleep(10)
             
            except Exception as e:
                print(f"Error in scan loop: {str(e)}", flush=True)
                time.sleep(60)

def main():
    """Entry point to start the scanner."""
    scanner = GateIOLRC15mScanner()
    print("Starting 15m Heikin Ashi futures scanner...", flush=True)
    scanner.scan_market()

if __name__ == "__main__":
    main()