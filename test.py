from binance.client import Client

api_key = 'wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN'
api_secret = '8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU'

client = Client(api_key, api_secret)

# ดึงข้อมูลยอดทรัพย์สินใน futures
def get_futures_balance():
    try:
        balance = client.futures_account_balance(recvWindow=5000)
        return balance
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")
        return None

# เรียกใช้งานฟังก์ชันและพิมพ์ผลลัพธ์
futures_balance = get_futures_balance()
print(futures_balance)
