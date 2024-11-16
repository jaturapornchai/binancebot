from gate_api import ApiClient, Configuration, Order, SpotApi
from gate_api.exceptions import ApiException, GateApiException
import time
import logging
from decimal import Decimal
from typing import List, Optional, Dict

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingClient:
    def __init__(self, api_key: str, api_secret: str):
        self.config = Configuration(
            key=api_key,
            secret=api_secret
        )
        self.client = ApiClient(self.config)
        self.spot_api = SpotApi(self.client)
    
    def get_ticker_price(self, currency_pair: str) -> Optional[Decimal]:
        """Get current ticker price for a currency pair."""
        try:
            ticker = self.spot_api.list_tickers(currency_pair=currency_pair)
            if ticker and ticker[0].last:
                return Decimal(str(ticker[0].last))
            return None
        except (GateApiException, ApiException) as e:
            logger.error(f"Error fetching ticker price for {currency_pair}: {str(e)}")
            return None

    def get_non_zero_balances(self) -> List[Dict]:
        """Get all non-zero balances excluding USDT with USD value."""
        try:
            balances = self.spot_api.list_spot_accounts()
            non_zero_balances = []
            
            for balance in balances:
                if float(balance.available) > 0 and balance.currency != 'USDT':
                    amount = Decimal(str(balance.available))
                    currency = balance.currency
                    
                    # Get current price in USDT
                    price = self.get_ticker_price(f"{currency}_USDT")
                    if price is None:
                        logger.warning(f"Could not get price for {currency}, skipping")
                        continue
                    
                    usd_value = amount * price
                    
                    non_zero_balances.append({
                        'currency': currency,
                        'available': amount,
                        'usd_value': usd_value
                    })
            
            return non_zero_balances
        except (GateApiException, ApiException) as e:
            logger.error(f"Error fetching balances: {str(e)}")
            raise

    def execute_market_sell(self, currency: str, amount: Decimal) -> bool:
        """Execute a market sell order with proper error handling."""
        currency_pair = f"{currency}_USDT"
        try:
            if amount <= Decimal('0'):
                logger.warning(f"Skipping {currency}: Amount too small")
                return False

            order = Order(
                currency_pair=currency_pair,
                side='sell',
                amount=str(amount),
                type='market',
                time_in_force='ioc'  # Immediate-or-Cancel
            )
            
            result = self.spot_api.create_order(order)
            logger.info(f"Successfully sold {amount} {currency}: Order ID {result.id}")
            return True
            
        except GateApiException as ex:
            logger.error(f"Gate.io API Error selling {currency}:")
            logger.error(f"Label: {ex.label}, Message: {ex.message}")
            return False
        except ApiException as e:
            logger.error(f"Error selling {currency}: {str(e)}")
            return False

def sell_all_coins(api_key: str, api_secret: str):
    """Main function to sell all coins in the portfolio."""
    trading_client = None
    try:
        trading_client = TradingClient(api_key, api_secret)
        
        # Get non-zero balances
        balances = trading_client.get_non_zero_balances()
        if not balances:
            logger.info("No available balances to sell.")
            return
        
        # Display all balances
        logger.info("\nFound the following coins to sell:")
        for balance in balances:
            logger.info(f"{balance['currency']}: {balance['available']} (${balance['usd_value']:.2f})")
        
        # Ask for confirmation
        confirm = input("\nคุณต้องการที่จะขายเหรียญทั้งหมดหรือไม่? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("ยกเลิกการทำงาน")
            return
        
        # Execute sells for all coins
        for balance in balances:
            currency = balance['currency']
            amount = balance['available']
            usd_value = balance['usd_value']
            
            logger.info(f"\nกำลังขาย {amount} {currency} (${usd_value:.2f})")
            success = trading_client.execute_market_sell(currency, amount)
            
            if success:
                time.sleep(1)  # Rate limiting
            else:
                logger.warning(f"ข้ามไปเหรียญถัดไปหลังจากล้มเหลวในการขาย {currency}")
                
    except Exception as e:
        logger.error(f"เกิดข้อผิดพลาด: {str(e)}")
    finally:
        if trading_client and trading_client.client:
            trading_client.client.close()

if __name__ == "__main__":
    # Use environment variables or secure configuration for these in production
    API_KEY = "c84d3616806f44e5651912c198094a1b"
    API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"
    
    sell_all_coins(API_KEY, API_SECRET)