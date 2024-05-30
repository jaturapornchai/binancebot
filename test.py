import gate_api
from gate_api.exceptions import ApiException, GateApiException

# กำหนดค่า API key และ secret
api_key = "c64a07643c277d2dbd07892bd9804425"
api_secret = "4ef7ba483b69ffcb9735e1e28ec41799ef85950e5b48783ccc47f2e21336f9a5"
configuration = gate_api.Configuration(
    key=api_key,
    secret=api_secret,
)
api_client = gate_api.ApiClient(configuration)
spot_api = gate_api.SpotApi(api_client)

def fetch_spot_positions():
    try:
        # ดึงข้อมูล spot positions
        positions = spot_api.list_spot_accounts()
        return positions
    except GateApiException as e:
        print(f"Gate API exception occurred: {e}")
        return None
    except ApiException as e:
        print(f"Exception occurred: {e}")
        return None

def fetch_trade_history(symbol, limit=100):
    try:
        # ดึงข้อมูลการซื้อขายล่าสุด
        trades = spot_api.list_my_trades(currency_pair=symbol, limit=limit)
        return trades
    except GateApiException as e:
        print(f"Gate API exception occurred: {e}")
        return None
    except ApiException as e:
        print(f"Exception occurred: {e}")
        return None

def fetch_latest_price(symbol):
    try:
        # ดึงข้อมูลราคาล่าสุด
        ticker = spot_api.list_tickers(currency_pair=symbol)
        return float(ticker[0].last)
    except GateApiException as e:
        print(f"Gate API exception occurred: {e}")
        return None
    except ApiException as e:
        print(f"Exception occurred: {e}")
        return None

def calculate_average_cost(trades):
    total_cost = 0
    total_amount = 0
    for trade in trades:
        if trade.side == 'buy':
            total_cost += float(trade.price) * float(trade.amount)
            total_amount += float(trade.amount)
        elif trade.side == 'sell':
            break
    if total_amount == 0:
        return 0
    return total_cost / total_amount

def print_colored(text, color):
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "reset": "\033[0m"
    }
    print(f"{colors[color]}{text}{colors['reset']}")

# ตัวอย่างการใช้งาน
positions = fetch_spot_positions()

if positions:
    for position in positions:
        available_balance = float(position.available)
        if available_balance > 0:
            symbol = position.currency + '_USDT'  # สมมติว่าต้องการคู่สกุลเงินที่ซื้อขายกับ USDT
            trades = fetch_trade_history(symbol)
            if trades:
                average_cost = calculate_average_cost(trades)
                latest_price = fetch_latest_price(symbol)
                if latest_price is not None:
                    balance_value = latest_price * available_balance
                    if balance_value > 20:  # ตรวจสอบว่ายอดคงเหลือมากกว่า 20 ดอลลาร์
                        profit_loss = (latest_price - average_cost) * available_balance
                        profit_loss_percent = ((latest_price - average_cost) / average_cost) * 100
                        result_text = (f"Symbol: {symbol}, Average Cost: {average_cost}, Latest Price: {latest_price}, "
                                       f"Available: {available_balance}, Balance Value: {balance_value:.2f}, "
                                       f"P/L: {profit_loss:.2f}, P/L%: {profit_loss_percent:.2f}%")
                        if profit_loss >= 0:
                            print_colored(result_text, "green")
                        else:
                            print_colored(result_text, "red")
else:
    print("ไม่สามารถดึงข้อมูลได้")
