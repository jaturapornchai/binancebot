FROM python:3.11.9

RUN apt-get update && apt-get install -y build-essential wget

# ติดตั้ง TA-Lib
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib-0.4.0-src.tar.gz ta-lib

WORKDIR /app

COPY requirements.txt requirements.txt

# ติดตั้ง NumPy ก่อน
RUN pip install --no-cache-dir numpy==1.23.5

# ติดตั้ง TA-Lib
RUN pip install --no-cache-dir TA-Lib

# ติดตั้งแพ็คเกจที่เหลือ
RUN pip install --no-cache-dir -r requirements.txt

ENV OMP_NUM_THREADS=1

COPY . .

CMD ["python", "./app.py"]