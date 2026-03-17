import os
import time
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from concurrent.futures import wait


class StopEventFetcher:
    def __init__(self, base_url):
        self.base_url = base_url

    def fetch_all_trips_for_vehicle(self, vehicle_id):
        url = f'{self.base_url}{vehicle_id}'
        records = []
        processed_trips = set()

        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            h2_tags = soup.find_all('h2')

            for h2 in h2_tags:
                trip_id = h2.text.strip().split()[-1]
                if trip_id in processed_trips:
                    continue

                table = h2.find_next_sibling('table')
                if not table:
                    continue

                rows = table.find_all('tr')
                if len(rows) < 2:
                    continue

                headers = [cell.text.strip() for cell in rows[0].find_all(['th', 'td'])]
                cells = rows[1].find_all(['th', 'td'])

                if len(cells) != len(headers):
                    continue

                record = {'vehicle_id': vehicle_id, 'trip_id': trip_id}
                for i, cell in enumerate(cells):
                    record[headers[i]] = cell.text.strip()

                records.append(record)
                processed_trips.add(trip_id)

        except Exception as e:
            pass
        return records


class StopEventPublisher:
    def __init__(self, topic_id, project_id, credentials_path, output_folder):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        self.publisher = pubsub_v1.PublisherClient()
        self.topic_path = self.publisher.topic_path(project_id, topic_id)
        self.output_folder = output_folder
        os.makedirs(output_folder, exist_ok=True)

        self.success_count = 0
        self.publish_success = 0
        self.publish_failures = 0
        self.futures = []

    def publish_record(self, record):
        try:
            message_data = json.dumps(record).encode("utf-8")
            future = self.publisher.publish(self.topic_path, message_data)
            self.futures.append(future)
            self.publish_success += 1
            return True
        except Exception as e:
            print(f"Failed to publish the data: {e}")
            self.publish_failures += 1
            return False

    def publish_and_save(self, vehicle_id, records, today):
        filename = os.path.join(self.output_folder, f"stop_{vehicle_id}_{today}.json")
        with open(filename, 'w') as f:
            json.dump(records, f, indent=2)

        print(f"Saved: {filename} ({len(records)} records)")
        self.success_count += 1

        for record in records:
            self.publish_record(record)

    def finalize(self, start_time, log_file="stop_events.txt"):
        wait(self.futures)
        elapsed = time.time() - start_time

        with open(log_file, 'a') as f:
            f.write(f"Total Success Files: {self.success_count}\n")
            f.write(f"Total Records Published: {self.publish_success}\n")
            f.write(f"Publish Failures: {self.publish_failures}\n")
            f.write(f"Folder created: {self.output_folder}\n")
            f.write(f"Elapsed time: {elapsed:.2f} seconds\n")

        print("\nData fetch and Publish Completed:")
        print(f"   Total files saved: {self.success_count}")
        print(f"   Successful trips published: {self.publish_success}")
        print(f"   Trips failed to publish: {self.publish_failures}")
        print(f"   Folder created: {self.output_folder}")
        print(f"   Elapsed time: {elapsed:.2f} seconds")
        print(f"   Log File created: {log_file}")


def main():
    base_url = "https://busdata.cs.pdx.edu/api/getStopEvents?vehicle_num="
    credentials_path = "/home/kthaniko/pub_sub_key.json"
    project_id = "parabolic-grid-456118-u8"
    topic_id = "datatransporttopic"
    today = datetime.now().strftime("%Y-%m-%d")
    output_folder = f"stop_event_data_{today}"

    vehicle_ids = [
        2902, 2904, 2911, 2916, 2930, 2933, 2938, 3002, 3013, 3023, 3027, 3032, 3036, 3037,
        3041, 3044, 3046, 3052, 3053, 3055, 3056, 3057, 3101, 3103, 3109, 3113, 3116, 3119,
        3120, 3124, 3129, 3130, 3139, 3141, 3143, 3145, 3160, 3167, 3201, 3204, 3207, 3209,
        3212, 3213, 3214, 3219, 3221, 3222, 3223, 3224, 3228, 3229, 3230, 3232, 3234, 3236,
        3237, 3238, 3241, 3243, 3245, 3247, 3253, 3258, 3261, 3264, 3267, 3302, 3310, 3314,
        3315, 3316, 3321, 3322, 3323, 3325, 3330, 3402, 3404, 3409, 3418, 3419, 3503, 3506,
        3510, 3513, 3514, 3517, 3522, 3529, 3534, 3537, 3545, 3547, 3556, 3559, 3564, 3567,
        3568, 3575, 3576, 3601, 3604, 3608, 3609, 3620, 3625, 3629, 3630, 3631, 3645, 3649,
        3701, 3706, 3708, 3712, 3713, 3714, 3717, 3719, 3721, 3722, 3725, 3726, 3727, 3729,
        3731, 3733, 3746, 3747, 3748, 3750, 3753, 3804, 3902, 3908, 3909, 3917, 3922, 3927,
        3928, 3929, 3930, 3936, 3938, 3939, 3943, 3951, 3952, 3953, 3957, 3962, 3964, 4002,
        4005, 4007, 4010, 4011, 4021, 4022, 4023, 4028, 4029, 4034, 4037, 4039, 4042, 4045,
        4047, 4050, 4057, 4058, 4064, 4066, 4067, 4068, 4069, 4070, 4201, 4202, 4205, 4207,
        4212, 4214, 4218, 4222, 4229, 4233, 4236, 4237, 4238, 4305, 4502, 4510, 4515, 4516,
        4522, 4523, 4526, 18724300
    ]

    fetcher = StopEventFetcher(base_url)
    publisher = StopEventPublisher(topic_id, project_id, credentials_path, output_folder)

    print("\nStarting Stop Event Data Fetch, Save, and Pub/Sub Publish...\n")
    start_time = time.time()

    for vid in vehicle_ids:
        records = fetcher.fetch_all_trips_for_vehicle(vid)
        if records:
            publisher.publish_and_save(vid, records, today)
            time.sleep(0.1)
        else:
            print(f"Error: No data found for vehicle {vid}")

    publisher.finalize(start_time)


if __name__ == "__main__":
    main()
