from google.cloud import pubsub_v1
from concurrent.futures import TimeoutError
import os

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/kthaniko/pub_sub_key.json"


project_id = "parabolic-grid-456118-u8"
subscription_id = "datatransporttopic-sub"


subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(project_id, subscription_id)


discarded_count = 0

def callback(message: pubsub_v1.subscriber.message.Message) -> None:
    global discarded_count
    print(f"Discarded message ID: {message.message_id}")
    message.ack()
    discarded_count += 1

def main():
    print(f" Listening on {subscription_path} to discard messages...\n")
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)

    with subscriber:
        try:
            streaming_pull_future.result(timeout=300)
        except TimeoutError:
            streaming_pull_future.cancel()
            streaming_pull_future.result()

    print(f"\n Finished discarding. Total messages discarded: {discarded_count}")

if __name__ == "__main__":
    main()
