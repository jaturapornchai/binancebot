from gate_api import SpotApi, ApiClient, Configuration, ApiException

# ตั้งค่า API key และ secret
api_key = "c64a07643c277d2dbd07892bd9804425"
api_secret = "4ef7ba483b69ffcb9735e1e28ec41799ef85950e5b48783ccc47f2e21336f9a5"

# สร้างการตั้งค่า Configuration
configuration = Configuration(
    key=api_key,
    secret=api_secret,
)

# สร้าง ApiClient ด้วยการตั้งค่าที่เตรียมไว้
api_client = ApiClient(configuration)

# สร้าง instance ของ SpotApi
spot_api = SpotApi(api_client)

# ฟังก์ชันสำหรับดึงข้อมูลตำแหน่งการซื้อขายที่มีอยู่
def get_positions():
    try:
        # ดึงข้อมูลตำแหน่งการซื้อขาย
        positions = spot_api.list_spot_accounts()
        return positions
    except ApiException as e:
        print(f"Exception when calling SpotApi->list_spot_accounts: {e}")
        return None

# ดึงข้อมูลตำแหน่งการซื้อขายที่มีอยู่
positions = get_positions()

# แสดงผลตำแหน่งการซื้อขายและต้นทุนเฉลี่ย
if positions:
    for position in positions:
        print(position)
else:
    print("No positions found or there was an error retrieving the data.")
