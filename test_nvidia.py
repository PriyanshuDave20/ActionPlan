#!/usr/bin/env python3
"""Test NVIDIA LLM API connectivity"""
import os
import json
import sys
import requests
from pathlib import Path

# Load .env file
env_path = Path(__file__).parent / "backend" / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

api_key = os.getenv("LLM_API_KEY")
model = os.getenv("LLM_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
base_url = os.getenv("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1")

print(f"Testing NVIDIA API...")
print(f"Model: {model}")
print(f"Base URL: {base_url}")
print(f"API Key: {api_key[:10]}..." if api_key else "NOT SET")

if not api_key:
    print("ERROR: LLM_API_KEY not set")
    sys.exit(1)

try:
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Say hello in one word"}],
            "max_tokens": 10,
            "temperature": 0
        },
        timeout=30
    )
    
    print(f"\nHTTP Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"\n✅ NVIDIA API working! Response: {content}")
    else:
        print(f"\n❌ NVIDIA API failed with status {response.status_code}")
        try:
            error_data = response.json()
            print(f"Error details: {json.dumps(error_data, indent=2)}")
        except:
            pass

except requests.exceptions.RequestException as e:
    print(f"\n❌ Request failed: {e}")
    sys.exit(1)