import os

# Check the compiled JS
js_file = r'C:\Users\priya\ActionPlan\frontend\dist\assets\index-DJ1XT8ui.js'
with open(js_file, 'r') as f:
    content = f.read()

print("=== COMPILED JS VERIFICATION ===")
print()
print("127.0.0.1 found:", "127.0.0.1" in content)
print("localhost:8000 found:", "localhost:8000" in content)
print("z6z9bqmchb found:", "z6z9bqmchb" in content)
print("execute-api found:", "execute-api" in content)
print()

# Find the API_BASE_URL context
idx = content.find('127.0.0.1')
if idx >= 0:
    start = max(0, idx - 80)
    end = min(len(content), idx + 80)
    print(f"Context around 127: {repr(content[start:end])}")

idx = content.find('z6z9bqmchb')
if idx >= 0:
    start = max(0, idx - 80)
    end = min(len(content), idx + 80)
    print(f"Context around z6z9: {repr(content[start:end])}")

# List all URLs found
import re
url_pattern = r'(?:https?://[^\s"\',;\]\)]+)'
urls = re.findall(url_pattern, content)
print(f"\nTotal URLs in bundle: {len(urls)}")
for url in urls:
    print(f"  {url}")

# Check for API_BASE_URL context
idx = content.find('API_BASE_URL')
if idx >= 0:
    start = max(0, idx - 20)
    end = min(len(content), idx + 200)
    print(f"\nAPI_BASE_URL context: {repr(content[start:end])}")
