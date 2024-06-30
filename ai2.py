#openai.api_key = "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"
#openai.organization = "org-11xo74V3OJfKvqVSZddRJhET"

import openai
import os

# ตั้งค่า API Key และ Organization ID
openai.api_key = "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"
openai.organization = "org-11xo74V3OJfKvqVSZddRJhET"

def setup_api_key():
    os.environ["OPENAI_API_KEY"] = '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'

def ask_question(client, model, question):
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": question}]
    )
    return response.choices[0].message.content

if __name__ == '__main__':
    setup_api_key()
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    fine_tuned_model = "ft:gpt-3.5-turbo-0125:personal::9faIiecG:ckpt-step-80"  # ใช้ ID ของโมเดลที่ปรับแต่งแล้วที่ต้องการ

    # ตั้งค่าตัวแปรคำถาม
    questions = [
        "ประเทศไทย เริ่มต้นสร้างเมือง จากจังหวัดใด",
    ]

    # ใช้โมเดลที่ปรับแต่งแล้วเพื่อถามคำถาม
    for question in questions:
        answer = ask_question(client, fine_tuned_model, question)
        print(f"Q: {question}")
        print(f"A: {answer}\n")
