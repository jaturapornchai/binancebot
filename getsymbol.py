from binance.client import Client

def get_tradable_usdt_futures_symbols():
    # สร้าง Binance client (ไม่จำเป็นต้องใช้ API key สำหรับข้อมูลสาธารณะ)
    client = Client()

    # ดึงข้อมูลสัญลักษณ์ทั้งหมดในตลาด Futures
    futures_exchange_info = client.futures_exchange_info()

    # กรองเฉพาะเหรียญที่สามารถเทรดได้และลงท้ายด้วย USDT
    tradable_symbols = [
        symbol_info['symbol']
        for symbol_info in futures_exchange_info['symbols']
        if symbol_info['status'] == 'TRADING' and symbol_info['symbol'].endswith('USDT')
    ]

    return tradable_symbols

def save_symbols_for_tradingview(symbols, filename='binance_futures_usdt_symbols.txt'):
    # บันทึกรายชื่อเหรียญลงไฟล์ text
    with open(filename, 'w') as f:
        for symbol in symbols:
            # เปลี่ยนรูปแบบให้เป็น BINANCE:SYMBOLUSDT            
            tradingview_symbol = f"BINANCE:{symbol}.P\n"            
            f.write(tradingview_symbol)
    print(f"บันทึกรายชื่อเหรียญลงในไฟล์ {filename} เรียบร้อยแล้ว")

# ดึงรายชื่อเหรียญที่เทรดได้และลงท้ายด้วย USDT
tradable_usdt_symbols = get_tradable_usdt_futures_symbols()

# บันทึกลงไฟล์
save_symbols_for_tradingview(tradable_usdt_symbols)

# แสดงตัวอย่างรายชื่อเหรียญ (5 รายการแรก)
print("\nตัวอย่างรายชื่อเหรียญ USDT Futures (5 รายการแรก):")
for symbol in tradable_usdt_symbols[:5]:
    print(f"BINANCE:{symbol}")

# แสดงจำนวนคู่เทรดทั้งหมด
print(f"\nจำนวนคู่เทรด USDT Futures ทั้งหมด: {len(tradable_usdt_symbols)}")