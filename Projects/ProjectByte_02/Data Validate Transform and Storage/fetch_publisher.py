import os
import json
import time
import urllib.request
import datetime
from google.cloud import pubsub_v1
from concurrent.futures import wait

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/kthaniko/pub_sub_key.json"

project_id = "parabolic-grid-456118-u8"
topic_id = "datatransporttopic"
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(project_id, topic_id)

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


today = datetime.datetime.now().strftime('%Y-%m-%d')
parent_dir = f"vehicle_data_{today}"
os.makedirs(parent_dir, exist_ok=True) 

base_url = "https://busdata.cs.pdx.edu/api/getBreadCrumbs"

success_count = 0
msg_count = 0
futures = []
start_time = time.time()

print("\nStarting Data Collection and Publishing...\n")

for vid in vehicle_ids:
    url = f"{base_url}?vehicle_id={vid}"
    try:
        with urllib.request.urlopen(url) as response:
            if response.getcode() == 200:
                data = json.loads(response.read().decode())

                filename = os.path.join(parent_dir, f"vehicle_{vid}_{today}.json")
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=2)

                print(f" Saved: {filename} - Publishing {len(data)} breadcrumbs...")

                for record in data:
                    message = json.dumps(record).encode("utf-8")
                    future = publisher.publish(topic_path, data=message)
                    futures.append(future)
                    msg_count += 1

                success_count += 1
                time.sleep(0.1)

    except Exception as e:
        pass

wait(futures)
end_time = time.time()

with open(os.path.join(parent_dir, "count.txt"), 'w') as f:
    f.write(f"Total Success Files: {success_count}\n")

print("\nData Collection and Publishing Complete:")
print(f"   Success files: {success_count}")
print(f"   Breadcrumbs published: {msg_count}")
print(f"   Total time: {end_time - start_time:.2f} seconds")
print(f"   Files organized under: {parent_dir}")
