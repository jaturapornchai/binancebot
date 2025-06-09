#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging, sys
from rich.console import Console
from get_scanner import AltcoinMomentumScanner

# ตั้งค่า logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', 
                    handlers=[logging.FileHandler("altcoin_scanner.log", encoding='utf-8'), 
                              logging.StreamHandler(stream=sys.stdout)])
logger = logging.getLogger("AltcoinMomentumScanner")
console = Console()

def main():
    try:
        # แสดงหัวข้อโปรแกรม
        console.print("\n[bold blue]===== เครื่องมือวิเคราะห์โมเมนตัม Altcoin =====")
        console.print("[bold blue]===== แสดงเหรียญที่น่าสนใจสำหรับการเทรด =====\n")
        
        # สร้าง scanner
        scanner = AltcoinMomentumScanner()
        
        # แสดงข้อมูลกำลังทำงาน
        console.print("[yellow]กำลังวิเคราะห์ตลาด...[/yellow]")
        
        # วิเคราะห์ BTC ก่อน
        scanner.analyze_btc_trend()
        
        # สแกนหาเหรียญที่น่าสนใจ
        results = scanner.scan_for_momentum()
        
        # แสดงรายละเอียดเหรียญน่าสนใจ
        scanner.display_interesting_coins(results)
        
    except KeyboardInterrupt: 
        console.print("\n[red]โปรแกรมถูกหยุดโดยผู้ใช้[/red]")
    except Exception as e:
        console.print(f"[red]เกิดข้อผิดพลาด: {str(e)}[/red]")
        logger.error(f"เกิดข้อผิดพลาด: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__": 
    sys.exit(main())