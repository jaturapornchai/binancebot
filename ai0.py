import csv
import json
import random

# รายการอาหารอีสาน
isan_foods = [
    "ส้มตำ", "ไก่ย่าง", "ลาบหมู", "น้ำตกหมู", "ข้าวเหนียว", 
    "ปลาร้าบอง", "แจ่วบอง", "หมูยอ", "แหนม", "แกงอ่อม",
    "ตำแตง", "ตำปู", "ตำไทย", "ก้อยปลา", "ซุปหน่อไม้", 
    "ต้มแซ่บ", "ปลาดุกย่าง", "หมกหน่อไม้", "ข้าวจี่", "ไส้กรอกอีสาน"
]

# สุ่มข้อมูลการขาย
sales_data = []
for _ in range(10000):
    food = random.choice(isan_foods)
    quantity = random.randint(1, 5)
    price = random.randint(30, 150)
    amount = quantity * price
    sales_data.append({"prompt": f"อาหาร: {food}, จำนวน: {quantity}, ราคา: {price}\n", "completion": f" มูลค่า: {amount}"})

# เขียนข้อมูลลงไฟล์ JSONL
file_path = "sales_data.jsonl"
with open(file_path, mode='w', encoding='utf-8') as file:
    for item in sales_data:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")

print(f"ข้อมูลการขายถูกบันทึกลงในไฟล์ {file_path} เรียบร้อยแล้ว")
