#openai.api_key = "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"
#openai.organization = "org-11xo74V3OJfKvqVSZddRJhET"

import openai
import os
import time
import csv
import jsonlines

# ตั้งค่า API Key และ Organization ID
openai.api_key = "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"
openai.organization = "org-11xo74V3OJfKvqVSZddRJhET"

model = "gpt-3.5-turbo" # ใช้โมเดลที่รองรับการปรับแต่ง

def setup_api_key():
    os.environ["OPENAI_API_KEY"] = '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'

def create_fine_tuning_file(file_path):
    print("Processing fine tuning file " + file_path)
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    file = client.files.create(
        file=open(file_path, "rb"),
        purpose='fine-tune'
    )

    # Get the file ID
    file_id = file.id

    # Check the file's status
    status = file.status

    while status != 'processed':
        print(f"File status: {status}. Waiting for the file to be processed...")
        time.sleep(10)  # Wait for 10 seconds
        file_response = client.files.retrieve(file_id)
        status = file_response.status
        print(file_response)
    
    fine_tuning_response = client.fine_tuning.jobs.create(training_file=file_id, model=model)
    print(fine_tuning_response)
    return fine_tuning_response

def fine_tune_model(fine_tuning_file):
    print("Starting fine tuning job with ID: " + fine_tuning_file.id)
    if fine_tuning_file.status == 'processed':
        client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        fine_tuning_response = client.fine_tuning.jobs.create(
            training_file=fine_tuning_file.id,
            model=model
        )
        print(fine_tuning_response.id)

def load_csv_finetuning(csv_file, output_path):
    # Open the CSV file for reading
    with open(csv_file, 'r', encoding='utf-8', newline='') as csv_file:
        csv_reader = csv.reader(csv_file)

        # Open the JSONL file for writing
        with jsonlines.open(output_path, mode='w') as jsonl_file:
            for row in csv_reader:
                system = row[0]
                values = [{"role": "system", "content": system}]
                odd = True
                for value in row[1:]:
                    if odd:
                        if len(value) > 0:
                            values.append({"role": "user", "content": value})
                        odd = False
                    else:
                        if len(value) > 0:
                            values.append({"role": "assistant", "content": value})
                        odd = True
                if values[-1]["role"] != "assistant":
                    values.append({"role": "assistant", "content": "ข้อความจากผู้ช่วยที่ถูกต้อง"})
                json_data = {"messages": values}
                jsonl_file.write(json_data)

def wait_for_fine_tuning_completion(job_id):
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    while True:
        job_status = client.fine_tuning.jobs.retrieve(job_id)
        status = job_status.status
        if status in ["succeeded", "failed"]:
            break
        print(f"Job status: {status}. Waiting...")
        time.sleep(60)  # Wait for 1 minute before checking again
    return job_status

if __name__ == '__main__':
    setup_api_key()
    fine_tuning_data = "docdetail_data.jsonl"
    load_csv_finetuning("docdetail_data.csv", fine_tuning_data)
    fine_tuning_file = create_fine_tuning_file(fine_tuning_data)
    job_status = wait_for_fine_tuning_completion(fine_tuning_file.id)
    print(job_status)

    if job_status.status == "succeeded":
        fine_tuned_model = job_status.fine_tuned_model
        print(f"Fine-tuned model: {fine_tuned_model}")
        client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        # ใช้โมเดลที่ปรับแต่งแล้ว
        response = client.chat.completions.create(
            model=fine_tuned_model,
            messages=[{"role": "user", "content": "ตัวอย่างข้อความเพื่อทดสอบโมเดล"}]
        )
        print(response.choices[0].message.content)
    else:
        print(f"Fine-tuning failed with status: {job_status.status}")
