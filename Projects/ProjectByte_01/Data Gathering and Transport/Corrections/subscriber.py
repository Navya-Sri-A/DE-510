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
output_file = open(output_filename, 'a')

subscriber = pubsub_v1.SubscriberClient()

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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error processing message: {e}")

def monitor_inactivity(stream_future):
    global last_message_time
    while not shutdown_event.is_set():
        if time.time() - last_message_time > idle_timeout:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No messages received for {idle_timeout} seconds. Exiting...")
            shutdown_event.set()
            stream_future.cancel()
            break
        time.sleep(5)

def main():
    global streaming_pull_future, monitor_thread, output_file, msg_count, last_message_time
    start_time = time.time()

    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Loop active: subscribing again...")
        shutdown_event.clear()
        last_message_time = time.time()

        streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
        monitor_thread = threading.Thread(target=monitor_inactivity, args=(streaming_pull_future,))
        monitor_thread.start()

        with subscriber:
            try:
                streaming_pull_future.result(timeout=timeout)
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Streaming pull future exception: {e}")
            finally:
                streaming_pull_future.cancel()
                monitor_thread.join()

                if shutdown_event.is_set():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Shutdown triggered. Exiting main loop.")
                    break

    output_file.close()
    end_time = time.time()
    file_size_bytes = os.path.getsize(output_filename)
    file_size_kb = file_size_bytes / 1024

    print(f"\nTotal messages received: {msg_count} in {end_time - start_time:.2f} seconds")
    print(f"Breadcrumbs written to -> {output_filename}")
    print(f"File size: {file_size_kb:.2f} KB\n")

if __name__ == "__main__":
    try:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Listening for messages on {subscription_path}...\n")
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Shutting down gracefully...")
        shutdown_event.set()
        output_file.close()
