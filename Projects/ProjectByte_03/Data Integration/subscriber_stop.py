import os
import json
import logging
import time
from datetime import datetime
from typing import List, Dict
from google.cloud import pubsub_v1
import psycopg2
import pandas as pd
from io import StringIO
from threading import Lock
from dotenv import load_dotenv


load_dotenv(".env")


log_file = "stop_event_pipeline_batched.log"
logging.basicConfig(
    filename=log_file,
    filemode='a',
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_PATH")
project_id = "parabolic-grid-456118-u8"
subscription_id = "datatransporttopic-sub"
subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(project_id, subscription_id)


DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}


buffer_lock = Lock()
total_received = 0
total_loaded = 0
total_skipped = 0
total_invalid = 0
last_message_time = datetime.now()
loaded_trip_ids = set()

class StopEventCleaner:
    def __init__(self):
        self.processed_combinations = set()

    def process_and_validate(self, record: Dict) -> pd.DataFrame:
        global total_invalid
      
        if not self.is_valid_record(record):
            total_invalid += 1
            return pd.DataFrame() 

        direction = 'Out' if str(record.get("direction")) == '0' else 'Back'
        service_key_map = {'W': 'Weekday', 'S': 'Saturday', 'U': 'Sunday'}
        service_key = service_key_map.get(record.get("service_key", "W"), 'Weekday')

        try:
            cleaned_record = {
                "trip_id": int(record["trip_id"]),
                "route_id": int(record.get("route_number", 0)),
                "vehicle_id": int(record["vehicle_id"]),
                "service_key": service_key,
                "direction": direction
            }
            return pd.DataFrame([cleaned_record])
        except Exception as e:
            logging.warning(f"Failed to convert record {record.get('trip_id')} to valid types: {e}")
            total_invalid += 1
            return pd.DataFrame()

    def is_valid_record(self, record: Dict) -> bool:
        required_fields = ["trip_id", "route_number", "vehicle_id", "service_key", "direction"]
        for field in required_fields:
            if field not in record or record[field] is None:
                logging.warning(f"Missing or null field '{field}' in record: {record}")
                return False

        try:
            trip_id = int(record.get("trip_id"))
            if trip_id <= 0:
                logging.warning(f"Invalid trip_id (non-positive): {trip_id} in {record}")
                return False
        except:
            logging.warning(f"Invalid trip_id (non-numeric): {record.get('trip_id')} in {record}")
            return False

        try:
            int(record.get("vehicle_id"))
        except:
            logging.warning(f"Invalid vehicle_id (non-numeric): {record.get('vehicle_id')} in {record}")
            return False

        return True

class StopEventPipelineHandler:
    def __init__(self):
        self.cleaner = StopEventCleaner()

    def process_data(self, record: Dict) -> pd.DataFrame:
        return self.cleaner.process_and_validate(record)

    def save_to_postgres(self, trip_metadata_df: pd.DataFrame, db_config: Dict):
        global total_loaded, total_skipped, loaded_trip_ids
        connection = None
        try:
            if trip_metadata_df.empty:
                logging.info("No valid records to insert (DataFrame is empty).")
                return

    
            trip_id = trip_metadata_df.iloc[0]["trip_id"]
            if trip_id in loaded_trip_ids:
                total_skipped += 1
                logging.info(f"Skipped trip_id already in memory: {trip_id}")
                return

            connection = psycopg2.connect(**db_config)
            cursor = connection.cursor()

            buffer = StringIO()
            trip_metadata_df.to_csv(buffer, index=False, header=False, sep='\t')
            buffer.seek(0)

            cursor.copy_from(
                file=buffer,
                table="trip",
                null="",
                sep='\t',
                columns=("trip_id", "route_id", "vehicle_id", "service_key", "direction")
            )

            connection.commit()
            loaded_trip_ids.add(trip_id)
            total_loaded += 1
            logging.info(f"1 new record inserted into PostgreSQL for trip_id {trip_id}.")

        except Exception as e:
            logging.error(f"Error saving trip data to PostgreSQL: {e}")
        finally:
            if connection:
                cursor.close()
                connection.close()

handler = StopEventPipelineHandler()

def callback(message: pubsub_v1.subscriber.message.Message):
    global total_received, last_message_time
    try:
        data = json.loads(message.data.decode("utf-8"))
        total_received += 1
        last_message_time = datetime.now()

    
        trip_metadata_df = handler.process_data(data)
        handler.save_to_postgres(trip_metadata_df, DB_CONFIG)

        message.ack()
    except Exception as e:
        logging.error(f"Callback error: {e}")

def log_and_print(message: str):
    print(message)
    logging.info(message)

if __name__ == "__main__":
    start_time = time.time()
    log_and_print(f"[{datetime.now().strftime('%H:%M:%S')}] Subscribing to {subscription_path}...")
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    with subscriber:
        try:
            while True:
                if (datetime.now() - last_message_time).total_seconds() > 60:  
                    streaming_pull_future.cancel()
                    break
                time.sleep(5)
        except Exception as e:
            logging.error(f"Subscriber crashed: {e}. Restarting...")
            streaming_pull_future.cancel()

    elapsed = time.time() - start_time
    log_and_print(f"Total messages received: {total_received}")
    log_and_print(f"Total records loaded into DB: {total_loaded}")
    log_and_print(f"Total records skipped (duplicates): {total_skipped}")
    log_and_print(f"Total records failed validation: {total_invalid}")
    log_and_print(f"Elapsed time: {elapsed:.2f} seconds")

    if os.path.exists(log_file):
        size_kb = os.path.getsize(log_file) / 1024
        log_and_print(f"Log file size: {size_kb:.2f} KB")
