import os
import sys
import time
import hashlib
import mimetypes
from pathlib import Path

import boto3
from botocore.config import Config


ENDPOINT = os.environ["RGW_ENDPOINT_URL"]
BUCKET = os.environ["RGW_BUCKET"]

ACCESS_KEY = os.environ["AWS_ACCESS_KEY_ID"]
SECRET_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]


s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
    ),
)


def sha256_file(path):
    sha256 = hashlib.sha256()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def main(file_path):
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(file_path)

    object_key = f"put-get-test/{file_path.name}"

    content_type = (
        mimetypes.guess_type(file_path.name)[0]
        or "application/octet-stream"
    )

    file_size = file_path.stat().st_size

    print(f"Endpoint : {ENDPOINT}")
    print(f"Bucket   : {BUCKET}")
    print(f"Object   : {object_key}")
    print(f"File     : {file_path}")
    print(f"Size     : {file_size} bytes")
    print(f"Type     : {content_type}")

    # --------------------------------------------------
    # SHA-256 trước PUT
    # --------------------------------------------------

    sha256_before = sha256_file(file_path)

    print(f"\nSHA256 before PUT: {sha256_before}")

    # --------------------------------------------------
    # PUT
    # --------------------------------------------------

    start = time.perf_counter()

    with open(file_path, "rb") as f:
        put_response = s3.put_object(
            Bucket=BUCKET,
            Key=object_key,
            Body=f,
            ContentType=content_type,
            Metadata={
                "sha256": sha256_before
            },
        )

    put_latency = time.perf_counter() - start

    put_status = put_response["ResponseMetadata"]["HTTPStatusCode"]

    print("\n--- PUT ---")
    print(f"HTTP status : {put_status}")
    print(f"Latency     : {put_latency:.4f} s")

    # --------------------------------------------------
    # HEAD
    # --------------------------------------------------

    head = s3.head_object(
        Bucket=BUCKET,
        Key=object_key,
    )

    print("\n--- HEAD ---")
    print(
        f"HTTP status    : "
        f"{head['ResponseMetadata']['HTTPStatusCode']}"
    )
    print(f"Object key     : {object_key}")
    print(f"Content-Type   : {head.get('ContentType')}")
    print(f"Content-Length : {head.get('ContentLength')}")
    print(f"Metadata       : {head.get('Metadata')}")

    # --------------------------------------------------
    # GET + SHA256
    # --------------------------------------------------

    start = time.perf_counter()

    get_response = s3.get_object(
        Bucket=BUCKET,
        Key=object_key,
    )

    sha256_after = hashlib.sha256()

    # đọc theo chunk, không load toàn bộ object vào RAM
    for chunk in get_response["Body"].iter_chunks(
        chunk_size=1024 * 1024
    ):
        if chunk:
            sha256_after.update(chunk)

    get_latency = time.perf_counter() - start

    sha256_after = sha256_after.hexdigest()

    print("\n--- GET ---")
    print(
        f"HTTP status : "
        f"{get_response['ResponseMetadata']['HTTPStatusCode']}"
    )
    print(f"Latency     : {get_latency:.4f} s")
    print(f"SHA256 GET  : {sha256_after}")

    # --------------------------------------------------
    # VERIFY
    # --------------------------------------------------

    print("\n--- VERIFY ---")

    if sha256_before == sha256_after:
        print("Checksum: OK")
    else:
        print("Checksum: FAILED")

    if head["ContentLength"] == file_size:
        print("Content-Length: OK")
    else:
        print("Content-Length: FAILED")

    if head.get("ContentType") == content_type:
        print("Content-Type: OK")
    else:
        print("Content-Type: FAILED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            f"Usage: python3 {sys.argv[0]} <file>"
        )
        sys.exit(1)

    main(sys.argv[1])
