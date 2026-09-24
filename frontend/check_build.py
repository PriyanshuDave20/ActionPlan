import re

with open(r'C:\Users\priya\ActionPlan\frontend\dist\assets\index-BVRwaQLY.js', 'r') as f:
    content = f.read()

# Check for key patterns
print("127.0.0.1 found:", "127.0.0.1" in content)
print("z6z9bqmchb found:", "z6z9bqmchb" in content)
print("execute-api found:", "execute-api" in content)
print("localhost found:", "localhost" in content)

# Find the API URL context
idx = content.find('127.0.0.1')
if idx >= 0:
    start = max(0, idx - 100)
    end = min(len(content), idx + 100)
    print(f"\nContext around 127.0.0.1: {repr(content[start:end])}")

# Find URLs
url_pattern = r'(?:https?://[^\s"\'),;\]]+)'
url_matches = re.findall(url_pattern, content)
print(f"\nTotal URLs in compiled JS: {len(url_matches)}")
for url in url_matches:
    print(f"  {url}")

# Check if VITE_API_BASE_URL was replaced
if "import.meta.env" in content:
    print("\nWARNING: import.meta.env not replaced!")
else:
    print("\nimport.meta.env was replaced at build time (expected)")
