import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict
from google.cloud import pubsub_v1
import psycopg2
import pandas as pd
from io import StringIO
from threading import Lock

# Set up a log file to record events and errors during pipeline execution
log_file = "batched_pipeline.log"
logging.basicConfig(filename=log_file, level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Set up GCP credentials and define the Pub/Sub subscription path
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/kthaniko/pub_sub_key.json"
project_id = "parabolic-grid-456118-u8"
subscription_id = "datatransporttopic-sub"
subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(project_id, subscription_id)

# PostgreSQL database connection settings
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "postgres",
    "user": "postgres",
    "password": "DataEngineering"
}

# Global variables to help with batching, timing, and tracking stats
first_operation_date = None
buffer_lock = Lock()
message_buffer = []
BATCH_SIZE = 1000
idle_timeout = 60  # seconds to wait with no new messages before exiting
start_time = time.time()
total_received = 0
total_loaded = 0
last_message_time = datetime.now()

# Class to validate each incoming GPS record and compute speed
class TriMetRecordCleaner:
    def __init__(self):
        self.processed_combinations = set()

    def process_and_validate(self, records: List[Dict]) -> pd.DataFrame:
        cleaned_data = []
        unique_entries = set()

        for record in records:
            record_key = (record.get("EVENT_NO_TRIP"), record.get("ACT_TIME"))
            if record_key in unique_entries:
                continue  # Skip duplicates
            unique_entries.add(record_key)

            try:
                if not self.is_valid_record(record):
                    continue
            except AssertionError as e:
                logging.warning(f"Validation failed for record: {record.get('EVENT_NO_TRIP')}, Reason: {e}")
                continue

            # Create a combined timestamp from OPD_DATE and ACT_TIME
            trip_id = record["EVENT_NO_TRIP"]
            timestamp = datetime.strptime(record["OPD_DATE"].split(":")[0], "%d%b%Y") + timedelta(seconds=record["ACT_TIME"])

            cleaned_data.append({
                "timestamp": timestamp,
                "latitude": record["GPS_LATITUDE"],
                "longitude": record["GPS_LONGITUDE"],
                "trip_id": trip_id,
                "METERS": record["METERS"],
            })

        df = pd.DataFrame(cleaned_data)
        if df.empty:
            return df

        # Sort and compute speed using METERS and time difference
        df.sort_values(by=["trip_id", "timestamp"], inplace=True)
        df['dMETERS'] = df.groupby('trip_id')['METERS'].diff()
        df['dTIMESTAMP'] = df.groupby('trip_id')['timestamp'].diff()
        df['SPEED'] = df.apply(
            lambda r: r['dMETERS'] / r['dTIMESTAMP'].total_seconds()
            if pd.notnull(r['dTIMESTAMP']) and r['dTIMESTAMP'].total_seconds() > 0 else None, axis=1)
        df['SPEED'] = df['SPEED'].bfill()  # Fill missing speed values

        return df[['timestamp', 'latitude', 'longitude', 'SPEED', 'trip_id']]

    def is_valid_record(self, record: Dict) -> bool:
        global first_operation_date

        # assertion-1: Ensure all required fields are present in the input record
        required_fields = ['EVENT_NO_TRIP', 'OPD_DATE', 'ACT_TIME', 'EVENT_NO_STOP', 'VEHICLE_ID',
                           'GPS_LATITUDE', 'GPS_LONGITUDE', 'METERS']

        for field in required_fields:
            if field not in record:
                raise AssertionError(f"Missing required field '{field}'")

        # assertion-2: Check if ACT_TIME is available or not
        if record.get('ACT_TIME') is None:
            raise AssertionError(f"ACT_TIME is missing for record: {record.get('EVENT_NO_TRIP')}")

        # assertion-3: Validate OPD_DATE is in correct format 
        try:
            datetime.strptime(record['OPD_DATE'].split(":")[0], "%d%b%Y")
        except Exception:
            raise AssertionError(f"Invalid OPD_DATE format: {record.get('OPD_DATE')}")

        # assertion-4: Check latitude is a float and is within expected Portland GPS boundary
        lat = record.get('GPS_LATITUDE')
        if lat is None or not isinstance(lat, float) or not (45.2 <= lat <= 45.7):
            raise AssertionError(f"Latitude {lat} is missing or out of range")

        # assertion-5: Check longitude is a float and is within Portland region
        lon = record.get('GPS_LONGITUDE')
        if lon is None or not isinstance(lon, float) or not (-124.0 <= lon <= -122.0):
            raise AssertionError(f"Longitude {lon} is missing or out of range")

        # assertion-6: Vehicle ID must be a valid positive integer
        if not isinstance(record['VEHICLE_ID'], int) or record['VEHICLE_ID'] <= 0:
            raise AssertionError(f"Invalid VEHICLE_ID: {record['VEHICLE_ID']}")

        # assertion-7: METERS value should not be negative
        if record.get('METERS', 0) < 0:
            raise AssertionError(f"Negative METERS value: {record['METERS']}")

        # assertion-8: If GPS_SATELLITES exists it must be a number between 0 and 12
        if 'GPS_SATELLITES' in record:
            sats = record['GPS_SATELLITES']
            if not isinstance(sats, (int, float)) or not (0 <= sats <= 12):
                raise AssertionError(f"GPS_SATELLITES {sats} out of range (0–12)")

        # assertion-9: Prevent duplicate records by checking unique key combination
        unique_key = (record['VEHICLE_ID'], record['EVENT_NO_TRIP'], record['EVENT_NO_STOP'],
                      record['ACT_TIME'], record['METERS'])
        if unique_key in self.processed_combinations:
            raise AssertionError(f"Duplicate record detected with key: {unique_key}")
        self.processed_combinations.add(unique_key)

        # assertion-10: All records processed in one batch should have same OPD_DATE
        if first_operation_date is None:
            first_operation_date = record['OPD_DATE']
        elif record['OPD_DATE'] != first_operation_date:
            raise AssertionError(f"Inconsistent OPD_DATE: {record['OPD_DATE']} (expected {first_operation_date})")

        return True

# Class to extract trip-level metadata like service type, route and direction
class TripDetails:
    def __init__(self):
        self.trip_details = {}

    def build_trip_details(self, records: List[Dict]) -> pd.DataFrame:
        for record in records:
            trip_id = record.get("EVENT_NO_TRIP")
            vehicle_id = record.get("VEHICLE_ID")
            route_id = record.get("ROUTE_ID", 0)

            try:
                day_of_week = datetime.strptime(record["OPD_DATE"].split(":")[0], "%d%b%Y").strftime("%A")
                service_key = "Weekday" if day_of_week not in ["Saturday", "Sunday"] else day_of_week
            except Exception:
                service_key = "Weekday"

            if trip_id not in self.trip_details:
                self.trip_details[trip_id] = {
                    "trip_id": trip_id,
                    "route_id": route_id,
                    "vehicle_id": vehicle_id,
                    "service_key": service_key,
                    "direction": "Out"
                }

        return pd.DataFrame(self.trip_details.values())

# Class that coordinates data processing and loading to DB
class TriMetPipelineHandler:
    def __init__(self):
        self.cleaner = TriMetRecordCleaner()
        self.metadata_extractor = TripDetails()

    def process_data(self, records: List[Dict]) -> pd.DataFrame:
        validated_data = self.cleaner.process_and_validate(records)
        trip_metadata = self.metadata_extractor.build_trip_details(records)
        return validated_data, trip_metadata

    def save_to_postgres(self, validated_df: pd.DataFrame, trip_metadata_df: pd.DataFrame, db_config: Dict):
        global total_loaded
        try:
            connection = psycopg2.connect(**db_config)
            cursor = connection.cursor()

            validated_df["tstamp"] = validated_df["timestamp"].apply(lambda ts: ts.strftime('%Y-%m-%d %H:%M:%S'))
            validated_df.drop(columns=["timestamp"], inplace=True)
            validated_df = validated_df[["tstamp", "latitude", "longitude", "SPEED", "trip_id"]]

            # Insert trip metadata, avoiding duplicates
            for _, row in trip_metadata_df.iterrows():
                cursor.execute(
                    "INSERT INTO trip (trip_id, route_id, vehicle_id, service_key, direction) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (trip_id) DO NOTHING",
                    (row['trip_id'], row['route_id'], row['vehicle_id'], row['service_key'], row['direction'])
                )

            # Bulk insert the GPS records
            if not validated_df.empty:
                for i in range(0, len(validated_df), 10000):
                    batch = validated_df.iloc[i:i + 10000]
                    buffer = StringIO()
                    batch.to_csv(buffer, index=False, header=False, sep='\t')
                    buffer.seek(0)
                    cursor.copy_from(buffer, 'breadcrumb', null="", columns=(
                        'tstamp', 'latitude', 'longitude', 'speed', 'trip_id'))

            connection.commit()
            total_loaded += len(validated_df)
            logging.info("Data successfully saved to PostgreSQL.")
        except Exception as e:
            logging.error(f"Error saving data to PostgreSQL: {e}")
        finally:
            if connection:
                cursor.close()
                connection.close()

# Callback for each Pub/Sub message
# Parses, batches, validates, and loads into DB

def callback(message: pubsub_v1.subscriber.message.Message):
    global message_buffer, total_received, last_message_time
    try:
        data = json.loads(message.data.decode("utf-8"))
        total_received += 1
        last_message_time = datetime.now()

        batch = None
        with buffer_lock:
            message_buffer.append(data)
            if len(message_buffer) >= BATCH_SIZE:
                batch = message_buffer[:]
                message_buffer.clear()

        if batch:
            validated_df, trip_metadata_df = handler.process_data(batch)
            handler.save_to_postgres(validated_df, trip_metadata_df, DB_CONFIG)

        message.ack()
    except Exception as e:
        logging.error(f"Callback error: {e}")

# Create the main pipeline handler
handler = TriMetPipelineHandler()

# Helper: Log and print together
def log_and_print(message: str):
    print(message)
    logging.info(message)

# Keep receiving messages until idle timeout is reached
if __name__ == "__main__":
    try:
        while True:
            log_and_print(f"[{datetime.now().strftime('%H:%M:%S')}] Subscribing to {subscription_path}...")
            streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
            with subscriber:
                try:
                    while True:
                        if (datetime.now() - last_message_time).total_seconds() > idle_timeout:
                            streaming_pull_future.cancel()
                            break
                        time.sleep(5)
                    break
                except Exception as e:
                    logging.error(f"Subscriber crashed: {e}. Restarting...")
                    streaming_pull_future.cancel()
                    continue
                except KeyboardInterrupt:
                    streaming_pull_future.cancel()
                    break
    finally:
        elapsed = time.time() - start_time
        log_and_print(f"Total messages received: {total_received}")
        log_and_print(f"Total records loaded into DB: {total_loaded}")
        log_and_print(f"Elapsed time: {elapsed:.2f} seconds")
        if os.path.exists(log_file):
            size_kb = os.path.getsize(log_file) / 1024
            log_and_print(f"Log file size: {size_kb:.2f} KB")

