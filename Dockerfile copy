FROM python:3.11.9

RUN apt-get update && apt-get install -y build-essential

WORKDIR /app

COPY requirements.txt requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

ENV OMP_NUM_THREADS=1

COPY . .

CMD ["python", "./app.py"]
