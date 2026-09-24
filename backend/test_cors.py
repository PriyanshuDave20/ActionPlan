import urllib.request
import json

url = "https://z6z9bqmchb.execute-api.us-east-2.amazonaws.com/health"

# Test GET with full header inspection
req = urllib.request.Request(url, headers={"Origin": "https://test.amplifyapp.com"})
try:
    resp = urllib.request.urlopen(req)
    print("=== GET /health (all headers) ===")
    print(f"Status: {resp.status}")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"GET Error: {e}")

# Also test with localhost origin
req2 = urllib.request.Request(url, headers={"Origin": "http://localhost:5173"})
try:
    resp2 = urllib.request.urlopen(req2)
    print("\n=== GET /health (localhost origin) ===")
    for k, v in resp2.headers.items():
        if 'access' in k.lower() or 'cors' in k.lower() or 'origin' in k.lower():
            print(f"  {k}: {v}")
except Exception as e:
    print(f"Error: {e}")

# Test /docs
print("\n=== GET /docs ===")
try:
    resp3 = urllib.request.urlopen("https://z6z9bqmchb.execute-api.us-east-2.amazonaws.com/docs")
    print(f"Status: {resp3.status}")
except Exception as e:
    print(f"Error: {e}")

# Test /openapi.json
print("\n=== GET /openapi.json ===")
try:
    resp4 = urllib.request.urlopen("https://z6z9bqmchb.execute-api.us-east-2.amazonaws.com/openapi.json")
    data = json.loads(resp4.read().decode())
    print(f"Status: {resp4.status}")
    print(f"OpenAPI has routes: {len(data.get('paths', {}))} paths")
    for path in data.get('paths', {}):
        print(f"  {path}")
except Exception as e:
    print(f"Error: {e}")
