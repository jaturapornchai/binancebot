# ตั้งค่า API Key และ Organization ID
#openai.api_key = "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"
#openai.organization = "org-11xo74V3OJfKvqVSZddRJhET"

from openai import OpenAI
import pandas as pd
import json

client = OpenAI(api_key="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")

# 1. Prepare Your Data
# Create a JSONL file containing your Binance trading data
# Each line is a JSON object with relevant info:
"""
{"prompt": "BTC/USDT price on 2023-11-15?", "completion": "18500.25 USD"}
{"prompt": "What is the highest volume pair on Binance in Q4 2023?", "completion": "ETH/USDT"}
{"prompt": "Analyse the trend of DOGE/USDT in the past month.", "completion": "The price of DOGE/USDT has been steadily increasing over the past month, with a notable surge in trading volume."}
"""

# 2. Fine-tune your Model (Only do this once)
# Replace 'sales_data.jsonl' with your JSONL file path

def fine_tune_model(filename):
    with open(filename, "rb") as file:
        file_upload_response = client.files.create(file=file, purpose="fine-tune")
        file_id = file_upload_response.id
    
    # Create a fine-tuning job
    fine_tune_response = client.fine_tuning.create(training_file=file_id, model="gpt-3.5-turbo")
    job_id = fine_tune_response.id

    print(f"Fine-tuning job created: {job_id}")
    # Check completion
    while True:
        job_status = client.fine_tuning.retrieve(id=job_id)
        if job_status.status in ["succeeded", "failed", "cancelled"]:
            break

# fine_tune_model("sales_data.jsonl")

# 3. Retrieve your Fine-tuned Model

fine_tuned_model = "ft:gpt-3.5-turbo-2023-06-26-08-12-20"  # Replace with your actual fine-tuned model name

# 4. Ask Questions

def ask_openai(prompt, model=fine_tuned_model):
    """Asks a question to the OpenAI model."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant providing insights on Binance trading data."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except openai.OpenAIError as e:
        print(f"OpenAI Error: {e}")

questions = [
    "รายการขายสินค้ามีอะไรบ้าง?",  # Replace with relevant Binance questions
    "สินค้าตัวไหนขายดีที่สุด?",
    "ยอดขายรวมเป็นเท่าไหร่?"
]

for question in questions:
    answer = ask_openai(question)
    print(f"Q: {question}")
    print(f"A: {answer}\n")
