import json
import urllib.request

# List of vehicle IDs  (For the Team - Data Foundry)
vehicle_ids = [4523, 18724300]

# API base URL
base_url = "https://busdata.cs.pdx.edu/api/getBreadCrumbs"

vehicle_info = []

for vid in vehicle_ids:
    url = f"{base_url}?vehicle_id={vid}"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            vehicle_info.extend(data)  
        print(f"Data for Vehicle ID {vid} fetched successfully and saved")
    except Exception as e:
        print(f"Couldn't fetch data for Vehicle ID {vid}: {e}")

with open("bcsample.json", 'w') as f:
    json.dump(vehicle_info, f, indent=2)

print("The vehicle data has been saved in 'bcsample.json'")
