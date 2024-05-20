import requests
import pandas as pd
import matplotlib.pyplot as plt

# Fetch data
symbol = 'AIUSDT'
interval = '15m'
limit = 144  # Number of 15 minute intervals
url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'

response = requests.get(url)
data = response.json()

# Create DataFrame
df = pd.DataFrame(data, columns=['Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote asset volume', 'Number of trades', 'Taker buy base asset volume', 'Taker buy quote asset volume', 'Ignore'])
df['Close'] = df['Close'].astype(float)
df['Low'] = df['Low'].astype(float)

# Find two lowest points
lowest_points = df.nsmallest(2, 'Low')

# Plotting
plt.figure(figsize=(12, 6))
plt.plot(df['Close'], label='Close Price', color='blue')
plt.scatter(lowest_points.index, lowest_points['Low'], color='red', label='Lowest Points')  # Mark lowest points
plt.title('AIUSDT Price Chart')
plt.xlabel('Time Frame (15m intervals)')
plt.ylabel('Price')
plt.legend()
plt.show()
