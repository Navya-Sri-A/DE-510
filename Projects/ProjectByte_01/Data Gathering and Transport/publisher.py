import os
import json
import time
from google.cloud import pubsub_v1
from datetime import datetime
from concurrent.futures import wait

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/kthaniko/pub_sub_key.json"

project_id = "parabolic-grid-456118-u8"
topic_id = "datatransporttopic"
topic_path = pubsub_v1.PublisherClient().topic_path(project_id, topic_id)

today = datetime.now().strftime("%Y-%m-%d")
success_dir = f"vehicle_data_{today}/success"

publisher = pubsub_v1.PublisherClient()

msg_count = 0
start_time = time.time()
futures = []
processed_file_count = 0

print(f"\nStarting to publish breadcrumb data from folder: {success_dir}\n")

for filename in os.listdir(success_dir):
    if filename.endswith(".json"):
        filepath = os.path.join(success_dir, filename)
        try:
            with open(filepath, 'r') as file:
                data = json.load(file)
            print(f" {filename} is a plain list with {len(data)} breadcrumbs")

            for record in data:
                message = json.dumps(record).encode("utf-8")
                future = publisher.publish(topic_path, data=message)
                futures.append(future)
                msg_count += 1

            processed_file_count += 1

        except Exception as e:
            print(f" Error processing {filename}: {e}")

wait(futures)

end_time = time.time()


print(f"\nPublishing Complete:")
print(f"Total files processed: {processed_file_count}")
print(f"Total breadcrumbs published: {msg_count}")
print(f"Time taken: {end_time - start_time:.2f} seconds\n")
