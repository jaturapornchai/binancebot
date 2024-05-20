import time
import requests
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from datetime import datetime
import numpy as np
import requests
from scipy.stats import linregress
from binance.client import Client
import time
from scipy.stats import linregress
from bs4 import BeautifulSoup
import traceback
import concurrent.futures
import datetime
import random
import time
import ccxt
from binance.client import Client
from binance.enums import *
import requests
import pandas as pd
import requests
import talib
import ta
import numpy as np
import pandas_datareader as pdr
import datetime

api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
client = Client(api_key, api_secret)

# get spot symbol condition not in future and save to text file
def fetch_spot_symbols():
    info = client.get_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol'] and item['status'] == 'TRADING']
    symbols.sort()
    return symbols

def fetch_future_symbols():
    info = client.futures_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol'] and item['status'] == 'TRADING']
    symbols.sort()
    return symbols

# not in future
def fetch_spot_symbols_not_in_future():
    spot_symbols = fetch_spot_symbols()
    future_symbols = fetch_future_symbols()
    symbols = [symbol for symbol in spot_symbols if symbol not in future_symbols]
    return symbols

spot_symbols = fetch_spot_symbols_not_in_future()
for symbol in spot_symbols:
    print(symbol)
# save to text file
with open('spot_symbols.txt', 'w') as f:
    for symbol in spot_symbols:
        f.write(symbol + '\n')
        