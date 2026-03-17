from google.cloud import pubsub_v1
import os
import time
import threading
from datetime import datetime
import json

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/kthaniko/pub_sub_key.json"



project_id = "parabolic-grid-456118-u8"
subscription_id = "datatransporttopic-sub"

subscription_path = pubsub_v1.SubscriberClient().subscription_path(project_id, subscription_id)

timeout = 800.0
idle_timeout = 30.0
msg_count = 0
shutdown_event = threading.Event()
last_message_time = time.time()

today_str = datetime.now().strftime('%Y-%m-%d')
output_filename = f"data_{today_str}.json"

subscriber = pubsub_v1.SubscriberClient()
output_file = open(output_filename, 'a')

def callback(message: pubsub_v1.subscriber.message.Message) -> None:
    global msg_count, last_message_time
    try:
        message_data = message.data.decode('utf-8')
        json_data = json.loads(message_data)
        output_file.write(json.dumps(json_data) + '\n')
        output_file.flush()
        msg_count += 1
        last_message_time = time.time()
        message.ack()
    except Exception as e:
        print(f"Error processing message: {e}")

def monitor_inactivity(stream_future):
    while not shutdown_event.is_set():
        if time.time() - last_message_time > idle_timeout:
            print("No messages received for 30 seconds. Exiting...")
            shutdown_event.set()
            stream_future.cancel()
            break
        time.sleep(5)

print(f"\nListening for messages on {subscription_path}...\n")
start = time.time()
streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)

monitor_thread = threading.Thread(target=monitor_inactivity, args=(streaming_pull_future,))
monitor_thread.start()

with subscriber:
    try:
        streaming_pull_future.result(timeout=timeout)
    except Exception:
        pass

shutdown_event.set()
monitor_thread.join()
output_file.close()
end = time.time()

file_size_bytes = os.path.getsize(output_filename)
file_size_kb = file_size_bytes / 1024

print(f"\nTotal messages received: {msg_count} in {end - start:.2f} seconds\n")
print( f"Breadcrumbs written to -> {output_filename}\n")
print(f"File size: {file_size_kb:.2f} KB\n")
