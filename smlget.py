from sqlalchemy import create_engine, text
import csv

def connect_and_query():
    try:
        # Create SQLAlchemy engine with the correct database name and password
        engine = create_engine("postgresql://postgres:19682511@localhost:5432/data03")
        
        print('Connecting to the PostgreSQL database...')
        
        # SQL query
        sql = """
        SELECT cust_code,
               (SELECT name_1 FROM ar_customer WHERE code=cust_code) AS customer_name,
               doc_date,
               total_amount
        FROM ic_trans
        WHERE cust_code <> '' AND trans_flag=44
        """
        
        with engine.connect() as connection:
            result = connection.execute(text(sql))
            
            # Write to CSV
            with open('output.csv', 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Write header
                writer.writerow(['cust_code', 'customer_name', 'doc_date', 'total_amount'])
                # Write data
                writer.writerows(result)
        
        print("Data has been written to output.csv")
       
    except Exception as error:
        print(f"An error occurred: {error}")

if __name__ == '__main__':
    connect_and_query()