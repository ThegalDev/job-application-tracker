import urllib.request
import json
import time

print("Waiting for server to start...")
time.sleep(2) 

url = "http://localhost:8000/log"
data = {
    "company": "Test Corp",
    "role": "Test Role",
    "url": "http://example.com",
    "date": "2025-11-20",
    "status": "Applied"
}

headers = {'Content-Type': 'application/json'}
req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers)

try:
    print(f"Sending POST to {url}...")
    with urllib.request.urlopen(req) as response:
        print(f"Status: {response.getcode()}")
        print(f"Response: {response.read().decode('utf-8')}")
except Exception as e:
    print(f"Error: {e}")
