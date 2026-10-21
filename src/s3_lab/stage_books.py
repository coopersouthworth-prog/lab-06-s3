#!/usr/bin/env python3

import json
import logging
import os
import sys
import time

import boto3
import requests
from botocore.exceptions import ClientError

# Logger setup: timestamped status messages at INFO level and above
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

# One S3 client shared by all functions
s3 = boto3.client("s3", region_name="us-east-1")


def parse_args():
    if len(sys.argv) < 4:
        log.error("Usage: stage_books.py BOOK_LIST INDEX_HTML BUCKET")
        sys.exit(1)
    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)

    try:
        with open(list_file) as f:
            urls = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        log.error(f"Book list not found: {list_file}")
        return []
    log.info(f"Found {len(urls)} URLs in {list_file}")

    paths = []
    for url in urls:
        filename = url.rstrip("/").split("/")[-1]
        path = os.path.join(dest_dir, filename)

        if os.path.exists(path):
            log.info(f"Skipping {filename}: already downloaded")
            paths.append(path)
            continue

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # raise an error for 404 etc.
            with open(path, "wb") as out:
                out.write(response.content)
            log.info(f"Downloaded {filename}")
            paths.append(path)
        except requests.RequestException as e:
            log.error(f"Error downloading {url}: {e}")

        time.sleep(1)

    log.info(f"{len(paths)} of {len(urls)} books available in {dest_dir}/")
    return paths


def create_bucket(bucket):
    try:
        s3.head_bucket(Bucket=bucket)
        log.info(f"Bucket {bucket} already exists")
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code not in ("404", "NoSuchBucket"):
            # 403 means the name exists but belongs to someone else
            log.error(f"Cannot access bucket {bucket} ({code}); "
                      "the name may be taken. Try adding a number.")
            return False

    try:
        s3.create_bucket(Bucket=bucket)
        log.info(f"Created bucket {bucket}")
        return True
    except ClientError as e:
        log.error(f"Error creating bucket {bucket}: {e}")
        return False


def make_public(bucket):
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket}/*",
            }
        ],
    }
    try:
        # Block Public Access must be off before the policy is accepted
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )
        log.info(f"Turned off Block Public Access for {bucket}")

        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        log.info(f"Attached public-read policy to {bucket}")
        return True
    except ClientError as e:
        log.error(f"Error making {bucket} public: {e}")
        return False


def upload_files(bucket, file_paths):
    count = 0
    for path in file_paths:
        key = os.path.basename(path)  # pg1342.txt, not books/pg1342.txt
        try:
            s3.upload_file(
                path, bucket, key,
                ExtraArgs={"ContentType": "text/plain; charset=utf-8"},
            )
            log.info(f"Uploaded {key}")
            count += 1
        except (ClientError, FileNotFoundError) as e:
            log.error(f"Error uploading {path}: {e}")
    log.info(f"Uploaded {count} of {len(file_paths)} files to {bucket}")
    return count


def upload_index(bucket, index_path):
    if not os.path.exists(index_path):
        log.error(f"Index file not found: {index_path}")
        return False
    try:
        s3.upload_file(
            index_path, bucket, "index.html",
            ExtraArgs={"ContentType": "text/html"},
        )
        log.info("Uploaded index.html")
        return True
    except ClientError as e:
        log.error(f"Error uploading {index_path}: {e}")
        return False


def main():
    list_file, index_path, bucket = parse_args()

    paths = download_books(list_file, "books")
    if not paths:
        log.error("No books were downloaded")
        sys.exit(1)

    if not create_bucket(bucket):
        sys.exit(1)

    if not make_public(bucket):
        sys.exit(1)

    uploaded = upload_files(bucket, paths)
    index_ok = upload_index(bucket, index_path)

    url = f"https://{bucket}.s3.amazonaws.com/index.html"
    if uploaded == len(paths) and index_ok:
        log.info(f"Success: all {uploaded} books and index.html are online")
    else:
        log.warning(f"Finished with errors: {uploaded} of {len(paths)} books, "
                    f"index.html {'ok' if index_ok else 'failed'}")
    log.info(f"Public index page: {url}")


if __name__ == "__main__":
    main()
