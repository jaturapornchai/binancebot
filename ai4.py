import clickhouse_connect
import tzlocal

# แก้ไขการใช้ get_localzone_name เป็น get_localzone
def normalize_timezone(tz):
    if isinstance(tz, str):
        local_name = tz
    else:
        local_name = tzlocal.get_localzone().zone
    return local_name, tzlocal.get_localzone()

# สร้างการเชื่อมต่อ
client = clickhouse_connect.get_client(
    host='143.198.203.119',
    port=18123,
    username='smlchdb',
    password='heiR5XpDMyn4',
    database='dedebi'
)

# สร้างคำสั่ง SQL สำหรับดึงข้อมูล
query = 'SELECT * FROM docdetail'

# ดึงข้อมูล
result = client.query(query)

# แสดงผลข้อมูล
for row in result.result_rows:
    print(row)
