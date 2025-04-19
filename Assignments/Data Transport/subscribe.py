import os
import json
from datetime import datetime
from google.cloud import pubsub_v1

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/navyasra/DataEngg/service_account.json"

project_id = "data-engineering-456118"
subscription_id = "my-topic-sub"

timeout = 50.0
idle_timeout = 10

subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(project_id, subscription_id)

total_msg = 0

def callback(message: pubsub_v1.subscriber.message.Message) -> None:
    global total_msg
    try:
        data = message.data.decode("utf-8")
        print(f"Received message: {message.data.decode('utf-8')} with {message.attributes}")
        total_msg += 1

        message.ack()

    except Exception as e:
        print(f"Error processing message: {e}")
        message.ack()

streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
print(f"Listening messages on {subscription_path}...\n")

begin_time = time.time()

with subscriber:
    try:
        streaming_pull_future.result(timeout=timeout)
    except TimeoutError:
        streaming_pull_future.cancel()
        streaming_pull_future.result()
      
end_time = time.time()
total_time_taken = end_time - begin_time

print(f"\nTotal number of messages received: {total_msg}")
print(f"Time taken to subscribe to all the messages: {total_time_taken:.2f} seconds\n")
