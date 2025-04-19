import os
import json
import time
from google.cloud import pubsub_v1
from concurrent.futures import wait

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/navyasra/DataEngg/service_account.json"

project_id = "data-engineering-456118"
topic_id = "my-topic"

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(project_id, topic_id)

with open("bcsample.json", "r") as file:
    buses = json.load(file)

futures = []
total_msg = 0

begin_time = time.time()

for b in buses:
        data = json.dumps(b).encode("utf-8")
        future = publisher.publish(topic_path, data)
        futures.append(future)
        total_msg += 1

wait(futures)

end_time = time.time()
total_time_taken = end_time - begin_time

print(f"\nPublishing has been completed")
print(f" Published {total_msg} messages to {topic_path}")
print(f" Time taken for all the messages to be published : {total_time_taken:.2f} seconds")
