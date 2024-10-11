from binance.client import Client
from binance.exceptions import BinanceAPIException
import time

# ไม่แสดง API key และ secret ในโค้ด
api_key = 'wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN'
api_secret = '8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU'

client = Client(api_key, api_secret)

def get_server_time():
    for _ in range(10):  # ลองหลายครั้งเพื่อลดผลกระทบจาก network latency
        server_time = client.futures_time()['serverTime']
        local_time = int(time.time() * 1000)
        time_offset = server_time - local_time
        return time_offset
    raise Exception("ไม่สามารถซิงโครไนซ์เวลากับเซิร์ฟเวอร์ได้")

def get_open_orders(recv_window):
    try:
        time_offset = get_server_time()
        timestamp = int(time.time() * 1000 + time_offset)

        orders = client.futures_get_open_orders(
            timestamp=timestamp,
            recvWindow=recv_window
        )
        return orders
    except BinanceAPIException as e:
        print(f"เกิดข้อผิดพลาด Binance API: {e.status_code} - {e.message}")
        if e.status_code == 400 and "recvWindow" in e.message:
            print("ลองเพิ่มค่า recvWindow และลองอีกครั้ง")
        return None
    except Exception as e:
        print(f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")
        return None

# ทดสอบการเรียกใช้ฟังก์ชัน
for recv_window in [20000]:
    print(f"\nกำลังลองใช้ recvWindow = {recv_window}")
    open_orders = get_open_orders(recv_window)
    if open_orders is not None:
        if len(open_orders) > 0:
            print("คำสั่งที่เปิดอยู่:")
            for order in open_orders:
                print(f"Symbol: {order['symbol']}, Side: {order['side']}, Quantity: {order['origQty']}, Price: {order['price']}")
        else:
            print("ไม่มีคำสั่งที่เปิดอยู่")
        break  # ออกจากลูปถ้าสำเร็จ
    else:
        print(f"ไม่สามารถดึงข้อมูลคำสั่งที่เปิดอยู่ได้ด้วย recvWindow = {recv_window}")

if open_orders is None:
    print("\nไม่สามารถดึงข้อมูลคำสั่งที่เปิดอยู่ได้หลังจากลองทุกค่า recvWindow")