import requests
from bs4 import BeautifulSoup
import re

def find_emails(url, visited=set()):
    """
    Recursively finds emails on the given URL and all linked pages within the same domain.
    """
    # ตรวจสอบว่า URL ถูกเยี่ยมชมแล้วหรือไม่
    if url in visited:
        return set()
    
    print(f"Visiting: {url}")
    visited.add(url)
    emails_found = set()

    try:
        # ขอเนื้อหาของหน้าเว็บ
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        # หาอีเมลในหน้านี้
        emails_found.update(set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", soup.text, re.I)))

        # หาลิงค์ทั้งหมดในหน้านี้และเรียกฟังก์ชั่นนี้เองสำหรับลิงค์ที่อยู่ภายในโดเมนเดียวกัน
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('/'):  # ลิงค์ภายใน
                new_url = f"{requests.utils.urlparse(url).scheme}://{requests.utils.urlparse(url).netloc}{href}"
                if new_url not in visited:
                    email = find_emails(new_url, visited)
                    emails_found.update(email)
                    print(email)

    except Exception as e:
        print(f"Error visiting {url}: {e}")

    return emails_found

# ตั้งค่า URL เริ่มต้น
start_url = 'https://www.prosoft.co.th' 

# รวบรวมอีเมล
emails = find_emails(start_url)

# บันทึกอีเมลลงในไฟล์
with open('email.txt', 'w') as file:
    for email in emails:
        file.write(email + '\n')

print("Saved emails to email.txt")
