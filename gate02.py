from gate_api import ApiClient, Configuration, Order, SpotApi
from gate_api.exceptions import ApiException, GateApiException
import time

# API credentials
api_key = "c84d3616806f44e5651912c198094a1b"
api_secret = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"

def place_market_order(symbol, amount_usdt=10):
    try:
        # Initialize API client
        config = Configuration(
            key=api_key,
            secret=api_secret
        )
        client = ApiClient(config)
        spot_api = SpotApi(client)
        
        # Get current price
        tickers = spot_api.list_tickers(currency_pair=symbol)
        if not tickers or not tickers[0].last:
            print(f"Could not get price for {symbol}")
            return
        
        current_price = float(tickers[0].last)
        quantity = amount_usdt / current_price
        
        print(f"\nCurrent price: {current_price}")
        print(f"Quantity to buy: {quantity:.8f}")
        
        # Create market buy order
        order = Order(
            currency_pair=symbol,
            side='buy',
            amount=str(round(quantity, 8)),
            type='market',
            time_in_force='ioc'  # Immediate or Cancel for market orders
        )
        
        # Place order
        result = spot_api.create_order(order)
        
        print("\n✅ Market Buy Order Placed Successfully:")
        print(f"Order ID: {result.id}")
        print(f"Status: {result.status}")
        print(f"Amount: {quantity:.8f} {symbol.split('_')[0]}")
        print(f"Total: {amount_usdt} USDT")
        
    except GateApiException as ex:
        print(f"\n❌ Gate.io API Error:")
        print(f"Label: {ex.label}")
        print(f"Message: {ex.message}")
    except ApiException as e:
        print(f"\n❌ API Error: {str(e)}")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")

if __name__ == "__main__":
    symbol = input("Enter trading pair (e.g., BTC_USDT): ")
    amount = float(input("Enter USDT amount to buy: "))
    place_market_order(symbol, amount)