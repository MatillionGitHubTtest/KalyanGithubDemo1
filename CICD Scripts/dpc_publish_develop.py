import os
import requests
import subprocess
from pathlib import Path
import json
import enum
from dataclasses import dataclass, field
from collections import namedtuple

# Load secrets from environment variables
client_id = os.getenv("DPC_CLIENT_ID")
client_secret = os.getenv("DPC_CLIENT_SECRET")
token_url = os.getenv("DPC_TOKEN_URL")
version_name = os.getenv("VERSION_NAME")
tst_environment_name = os.getenv("DPC_TEST_ENV")
branch_name = os.getenv("BRANCH_NAME")
# Derive DPC API URLs
artifacts_url = (
    "https://"
    + os.getenv("DPC_ACCOUNT_REGION")
    + ".api.matillion.com/dpc/v1/projects/"
    + os.getenv("DPC_PROJECT_ID")
    + "/artifacts"
)
cc_url = (
    "https://"
    + os.getenv("DPC_ACCOUNT_REGION")
    + ".api.matillion.com/dpc/v1/custom-connectors"
)
flex_url = (
    "https://"
    + os.getenv("DPC_ACCOUNT_REGION")
    + ".api.matillion.com/dpc/v1/flex-connectors"
)
print("artifacts_url = " + artifacts_url)
print("version_name = " + version_name)


### Classes for dealing with custom/flex connectors ####
@dataclass
class PublicationFormEntry:
    key: str
    value: tuple


class PublicationResource:
    def id(self) -> str:
        raise NotImplementedError("id() must be implemented by subclasses.")

    def content(self) -> bytes | str:
        raise NotImplementedError("content() must be implemented by subclasses.")

    def content_type(self) -> str:
        return "text/plain"

    def headers(self) -> dict:
        return {}

    def form_data(self) -> PublicationFormEntry:
        return PublicationFormEntry(
            key=self.id(),
            value=(None, self.content(), self.content_type(), self.headers()),
        )


@dataclass
class FileResource(PublicationResource):
    name: str
    path: str
    type: str = field(default="text/plain")

    def id(self) -> str:
        return self.name

    def content(self) -> bytes:
        with open(self.path, "rb") as f:
            return f.read()

    def content_type(self) -> str:
        return self.type


ConnectorTypeData = namedtuple("ConnectorTypeData", ["id_key", "prefix"])


class ConnectorType(enum.Enum):
    FLEX = ConnectorTypeData("alternateId", "flex")
    CUSTOM = ConnectorTypeData("id", "custom")

    @property
    def id(self):
        return self.value.id_key

    @property
    def prefix(self):
        return self.value.prefix


@dataclass
class ConnectorResource(PublicationResource):
    type: ConnectorType
    connector: dict

    def id(self) -> str:
        if self.type.id not in self.connector:
            raise AttributeError(
                f"{self.type.prefix.title()} Connector does not have an {self.type.id} field."
            )
        return (
            f"connector-profile:{self.type.prefix}-{self.connector[self.type.id]}.json"
        )

    def content(self) -> bytes | str:
        return json.dumps(self.connector)

    def content_type(self) -> str:
        return "application/vnd.matillion.connector-profile+json"


#########################
# Step 0: Get Commit Hash
try:
    commit_hash = (
        subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    )
except subprocess.CalledProcessError:
    print("Error: Unable to retrieve Git commit hash.")
    exit(1)
print("commit_hash = " + commit_hash)
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
print("access_token = " + access_token)
# Step 2: Find .yml, .py, .sql files
repo_path = Path(".")
allowed_extensions = {
    ".yaml": "application/vnd.matillion.dpl+yaml",
    ".yml": "application/vnd.matillion.dpl+yaml",
    ".py": "text/plain",
    ".sql": "text/plain",
}
files_to_upload = [
    file for file in repo_path.rglob("*") if file.suffix in allowed_extensions
]
if not files_to_upload:
    print("No matching files found to upload.")
    exit(0)
# Step 3: Get Custom and Flex Connectors
headers = {"Authorization": f"Bearer {access_token}"}
cc_response = requests.get(cc_url, headers=headers)
for v in cc_response.json():
    files_to_upload.append(ConnectorResource(type=ConnectorType.CUSTOM, connector=v))
flex_response = requests.get(flex_url, headers=headers)
for v in flex_response.json():
    files_to_upload.append(ConnectorResource(type=ConnectorType.FLEX, connector=v))
# Step 4: Prepare files for multipart/form-data
files = {}
try:
    for file in files_to_upload:
        if isinstance(file, Path):
            mime_type = allowed_extensions.get(file.suffix, "application/octet-stream")
            relative_path = file.relative_to(repo_path).as_posix()
            files[relative_path] = (relative_path, open(file, "rb"), mime_type)
        elif isinstance(file, ConnectorResource):
            files[file.id()] = (file.id(), file.content(), file.content_type())
    # Step 5: Make the API call
    headers = {
        "Authorization": f"Bearer {access_token}",
        "versionName": f"{version_name}",
        "commitHash": f"{commit_hash}",
        "environmentName": f"{tst_environment_name}",
        "branch": f"{branch_name}",
    }
    print("headers = " + str(headers))
    response = requests.post(artifacts_url, headers=headers, files=files)
    # Step 6: Handle response
    if response.status_code in [200, 201]:
        print(
            f"Successfully uploaded files: {[str(file.relative_to(repo_path)) if isinstance(file, Path) else file.id() for file in files_to_upload]}"
        )
    else:
        print(f"Failed to upload files: {response.status_code} - {response.text}")
        exit(1)
finally:
    # Close file handles to avoid memory leaks
    for file in files.values():
        if hasattr(file[1], "close"):
            file[1].close()
