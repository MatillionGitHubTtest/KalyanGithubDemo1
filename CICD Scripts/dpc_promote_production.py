import os
import requests
import subprocess
from pathlib import Path
import json

# Load secrets from environment variables
client_id = os.getenv("DPC_CLIENT_ID")
client_secret = os.getenv("DPC_CLIENT_SECRET")
token_url = os.getenv("DPC_TOKEN_URL")
version_name = os.getenv("VERSION_NAME")
prod_environment_name = os.getenv("DPC_PROD_ENV")

# Derive DPC API URL for promotion
# This is an assumed endpoint. Actual endpoint might vary.
promote_url = (
    "https://"
    + os.getenv("DPC_ACCOUNT_REGION")
    + ".api.matillion.com/dpc/v1/projects/"
    + os.getenv("DPC_PROJECT_ID")
    + "/promote"
)

print(f"Promotion URL: {promote_url}")
print(f"Version Name: {version_name}")

# Step 0: Get Commit Hash
try:
    commit_hash = (
        subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    )
except subprocess.CalledProcessError:
    print("Error: Unable to retrieve Git commit hash.")
    exit(1)
print(f"Commit Hash: {commit_hash}")

# Step 1: Get OAuth Token
auth_payload = {
    "grant_type": "client_credentials",
    "client_id": client_id,
    "client_secret": client_secret,
}
token_response = requests.post(token_url, data=auth_payload)
if token_response.status_code != 200:
    print(f"Failed to obtain token: {token_response.text}")
    exit(1)
access_token = token_response.json().get("access_token")
print("Access Token obtained.")

# Step 2: Promote to Production
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}

# The body of the promotion request might vary based on DPC API.
# Assuming it needs version_name, commit_hash, and target environment.
promotion_payload = {
    "versionName": version_name,
    "commitHash": commit_hash,
    "targetEnvironmentName": prod_environment_name,
    # Add any other required parameters for promotion
}

print(f"Promotion Payload: {json.dumps(promotion_payload, indent=2)}")

response = requests.post(promote_url, headers=headers, json=promotion_payload)

# Step 3: Handle response
if response.status_code in [200, 201, 202]:
    print(
        f"Successfully initiated promotion for version '{version_name}' to '{prod_environment_name}'."
    )
    print(f"Response: {response.text}")
else:
    print(f"Failed to promote version '{version_name}' to '{prod_environment_name}'.")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    exit(1)
