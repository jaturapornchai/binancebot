FROM python:3.11.9

RUN apt-get update && apt-get install -y build-essential wget

WORKDIR /app

COPY requirements.txt requirements.txt

# ติดตั้ง NumPy ก่อน
RUN pip install --no-cache-dir numpy==1.23.5

# ติดตั้ง TA-Lib
# RUN pip install --no-cache-dir TA-Lib

# ติดตั้งแพ็คเกจที่เหลือ
RUN pip install --no-cache-dir -r requirements.txt

ENV OMP_NUM_THREADS=1

COPY . .

CMD ["python", "./app.py"]