from gate_api import ApiClient, Configuration, Order, SpotApi
from gate_api.exceptions import ApiException, GateApiException
import time

def sell_all_coins():
    # API configuration
    config = Configuration(
        key="c84d3616806f44e5651912c198094a1b",
        secret="32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"
    )
    
    # Create API client
    client = ApiClient(config)
    spot_api = SpotApi(client)
    
    try:
        # Get all spot balances
        balances = spot_api.list_spot_accounts()
        
        # Filter non-zero balances (excluding USDT)
        non_zero_balances = [
            balance for balance in balances 
            if float(balance.available) > 0 and balance.currency != 'USDT'
        ]
        
        if not non_zero_balances:
            print("No available balances to sell.")
            return
        
        print("\nFound the following non-zero balances:")
        for balance in non_zero_balances:
            print(f"{balance.currency}: {balance.available}")
        
        # Ask for confirmation
        confirm = input("\nDo you want to proceed with selling all these currencies? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Operation cancelled.")
            return
        
        # Sell each currency
        for balance in non_zero_balances:
            currency = balance.currency
            available = float(balance.available)
            currency_pair = f"{currency}_USDT"
            
            try:
                # Create market sell order
                order = Order(
                    currency_pair=currency_pair,
                    side='sell',
                    amount=str(available),
                    type='market',
                    time_in_force='ioc'
                )
                
                print(f"\nAttempting to sell {available} {currency}")
                result = spot_api.create_order(order)
                print(f"Successfully created sell order for {currency}: Order ID {result.id}")
                
                # Add small delay between orders
                time.sleep(1)
                
            except GateApiException as ex:
                print(f"Gate.io API Error selling {currency}:")
                print(f"Label: {ex.label}, Message: {ex.message}")
                continue
            except ApiException as e:
                print(f"Error selling {currency}: {str(e)}")
                continue
                
    except GateApiException as ex:
        print(f"Gate.io API Error:")
        print(f"Label: {ex.label}, Message: {ex.message}")
    except ApiException as e:
        print(f"Error accessing API: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    sell_all_coins()