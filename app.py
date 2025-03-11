import os
import time
import re
from typing import List, Dict
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from gate_api import ApiClient, Configuration, FuturesApi

class GateIOShortScanner:
    def __init__(self):
        """Initialize the scanner with API credentials and trading parameters."""
        load_dotenv()
        self.api_key = os.getenv('GATEIO_API_KEY')
        self.secret_key = os.getenv('GATEIO_SECRET_KEY')
        if not self.api_key or not self.secret_key:
            raise ValueError("API keys missing")
        config = Configuration(key=self.api_key, secret=self.secret_key, host="https://api.gateio.ws/api/v4")
        self.client = ApiClient(config)
        self.futures_api = FuturesApi(self.client)
        self.leverage = 5  # Leverage for trades
        self.order_amount = 20  # Base order amount in USD
        self.lookback_period = 100  # Period for linear regression calculation

    def get_futures_contracts(self) -> List[str]:
        """Fetch a list of valid USDT-settled futures contracts with sufficient volume."""
        ticket = self.futures_api.list_futures_tickers(settle='usdt')
        valid_contracts = []
        pattern = re.compile(r'^\D+_USDT$')  # Match contracts like BTC_USDT
        for contract in ticket:
            if pattern.match(contract.contract) and contract.contract not in ['USDC_USDT', 'DOGS_USDT']:
                json_data = contract.to_dict()
                if float(json_data['volume_24h']) * float(json_data['last']) > 1000000:  # Volume filter
                    valid_contracts.append(contract.contract)
        print(f"Found {len(valid_contracts)} valid contracts", flush=True)
        return valid_contracts

    def get_candlesticks(self, contract: str) -> pd.DataFrame:
        """Fetch 15-minute candlestick data for a given contract."""
        candles = self.futures_api.list_futures_candlesticks(settle='usdt', contract=contract, interval='15m', limit=500)
        if not candles:
            return pd.DataFrame()
        data = [{'timestamp': float(c.t), 'open': float(c.o), 'high': float(c.h), 
                 'low': float(c.l), 'close': float(c.c), 'volume': float(c.v)} for c in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        return df.sort_values('timestamp')

    def calculate_linear_regression(self, contract: str, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate linear regression channels (middle, upper, lower lines) for the given dataframe."""
        if len(df) < self.lookback_period:
            return df
        def calc_lr(values):
            x = np.arange(len(values))
            slope, intercept = np.polyfit(x, values, 1)
            return slope * (self.lookback_period - 1) + intercept
        df['middle_line'] = df['close'].rolling(window=self.lookback_period).apply(calc_lr, raw=True)
        df['dev'] = df['close'].rolling(window=self.lookback_period).std() * 2
        df['upper_line'] = df['middle_line'] + df['dev']
        df['lower_line'] = df['middle_line'] - df['dev']
        df['center'] = df['middle_line']
        print(f"Calculated LR for {contract}: Middle={df['middle_line'].iloc[-1]:.4f}, "
              f"Upper={df['upper_line'].iloc[-1]:.4f}, Lower={df['lower_line'].iloc[-1]:.4f}", flush=True)
        return df.dropna()

    def check_trading_signal(self, df: pd.DataFrame) -> str:
        """Check for BUY or SELL signals based on price crossing regression lines."""
        if len(df) < 2:
            return None
        current = df.iloc[-1]
        previous = df.iloc[-2]
        if previous['high'] >= previous['upper_line'] and current['close'] > current['upper_line']:
            print(f"BUY signal detected: Close={current['close']:.4f}, Upper={current['upper_line']:.4f}", flush=True)
            return "BUY"
        if previous['low'] <= previous['lower_line'] and current['close'] < current['lower_line']:
            print(f"SELL signal detected: Close={current['close']:.4f}, Lower={current['lower_line']:.4f}", flush=True)
            return "SELL"
        return None

    def set_leverage(self, contract: str) -> bool:
        """Set the leverage for a specific contract."""
        try:
            self.futures_api.update_position_leverage(contract=contract, settle='usdt', leverage=str(self.leverage))
            print(f"Set leverage {self.leverage}x for {contract}", flush=True)
            return True
        except Exception as e:
            print(f"Failed to set leverage for {contract}: {str(e)}", flush=True)
            return False

    def get_latest_price(self, contract: str) -> float:
        """Fetch the latest price for a given contract."""
        ticker = self.futures_api.list_futures_tickers(settle='usdt')
        for t in ticker:
            if t.contract == contract:
                return float(t.last)
        print(f"No price found for {contract}", flush=True)
        return None

    def check_existing_position(self, contract: str) -> Dict:
        """Check if there’s an existing position for the contract."""
        positions = self.futures_api.list_positions(settle='usdt', holding=True)
        for p in positions:
            if p.contract == contract:
                print(f"Found existing position for {contract}: Size={p.size}", flush=True)
                return p.to_dict()
        return None

    def close_position(self, contract: str, position: Dict) -> bool:
        """Close an existing position for the contract."""
        try:
            size = float(position['size'])
            if size != 0:
                direction = abs(size) if size < 0 else -size
                self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': direction, 
                                                              'price': 0, 'tif': 'ioc', 'reduce_only': True})
                print(f"Closed position for {contract}: Size={abs(size)}", flush=True)
                return True
            return False
        except Exception as e:
            print(f"Failed to close position for {contract}: {str(e)}", flush=True)
            return False

    def create_long_order(self, contract: str) -> Dict:
        """Create a long order for the contract."""
        try:
            if not self.set_leverage(contract):
                return None
            price = self.get_latest_price(contract)
            if not price:
                return None
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': size, 
                                                                  'price': 0, 'tif': 'ioc', 'reduce_only': False})
            print(f"Opened LONG position: {contract} Size={size}", flush=True)
            return order
        except Exception as e:
            print(f"Failed to open LONG for {contract}: {str(e)}", flush=True)
            return None

    def create_short_order(self, contract: str) -> Dict:
        """Create a short order for the contract."""
        try:
            if not self.set_leverage(contract):
                return None
            price = self.get_latest_price(contract)
            if not price:
                return None
            contract_info = self.futures_api.get_futures_contract(contract=contract, settle='usdt')
            multiplier = float(contract_info.to_dict()['quanto_multiplier'])
            min_size = float(contract_info.to_dict()['order_size_min'])
            usd_value = self.order_amount * self.leverage
            size = max(min_size, round(usd_value / (price * multiplier)))
            order = self.futures_api.create_futures_order('usdt', {'contract': contract, 'size': -size, 
                                                                  'price': 0, 'tif': 'ioc', 'reduce_only': False})
            print(f"Opened SHORT position: {contract} Size={size}", flush=True)
            return order
        except Exception as e:
            print(f"Failed to open SHORT for {contract}: {str(e)}", flush=True)
            return None

    def scan_positions(self):
        """Scan and manage existing positions based on price vs. center line."""
        try:
            positions = [p.to_dict() for p in self.futures_api.list_positions(settle='usdt', holding=True)]
            print(f"Scanning {len(positions)} open positions", flush=True)
            for pos in positions:
                contract = pos['contract']
                df = self.get_candlesticks(contract)
                if not df.empty:
                    df = self.calculate_linear_regression(contract, df)
                    if 'center' not in df.columns:
                        continue
                    current_price = self.get_latest_price(contract)
                    if current_price is None:
                        continue
                    center = df['center'].iloc[-1]
                    size = float(pos['size'])
                    if size > 0 and current_price < center:
                        print(f"Closing LONG position for {contract}: Price={current_price:.4f} < Center={center:.4f}", flush=True)
                        self.close_position(contract, pos)
                    elif size < 0 and current_price > center:
                        print(f"Closing SHORT position for {contract}: Price={current_price:.4f} > Center={center:.4f}", flush=True)
                        self.close_position(contract, pos)
        except Exception as e:
            print(f"Error scanning positions: {str(e)}", flush=True)

    def scan_market(self):
        """Continuously scan the market for trading opportunities."""
        first_run = True
        while True:
            current_time = pd.Timestamp.now(tz='Asia/Bangkok')
            if current_time.minute % 15 == 0 or first_run:
                print(f"Starting market scan at {current_time}", flush=True)
                first_run = False
                self.scan_positions()
                contracts = self.get_futures_contracts()
                for contract in contracts:
                    existing_pos = self.check_existing_position(contract)
                    df = self.get_candlesticks(contract)
                    if not df.empty:
                        df = self.calculate_linear_regression(contract, df)
                        if 'upper_line' not in df.columns or 'lower_line' not in df.columns:
                            continue
                        signal = self.check_trading_signal(df)
                        if signal == "BUY":
                            if existing_pos and float(existing_pos['size']) < 0:
                                print(f"Closing existing SHORT position for {contract} before opening LONG", flush=True)
                                self.close_position(contract, existing_pos)
                            if not self.check_existing_position(contract):
                                self.create_long_order(contract)
                        elif signal == "SELL":
                            if existing_pos and float(existing_pos['size']) > 0:
                                print(f"Closing existing LONG position for {contract} before opening SHORT", flush=True)
                                self.close_position(contract, existing_pos)
                            if not self.check_existing_position(contract):
                                self.create_short_order(contract)
                time.sleep(30)
            if current_time.minute % 2 == 0:
                if current_time.minute % 15 == 0:
                    first_run = True
                else:
                    self.scan_positions()
                    time.sleep(60)
            
            time.sleep(10)

def main():
    """Entry point to start the scanner."""
    scanner = GateIOShortScanner()
    print("Starting Futures market scanner...", flush=True)
    scanner.scan_market()

if __name__ == "__main__":
    main()