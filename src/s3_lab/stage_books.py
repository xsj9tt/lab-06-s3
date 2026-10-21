#!/usr/bin/env python3
"""Download Gutenberg books and stage them in a public S3 bucket."""

import json
import logging
import os
import sys
import time

import boto3
import requests
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import ClientError

# Logger setup
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# Shared S3 client used by all functions
s3 = boto3.client("s3", region_name="us-east-1")

def parse_args():
    """Returns list_file, index_path, bucket"""
    if len(sys.argv) < 4:
        log.error("Usage: python stage_books.py <list_file> <index_path> <bucket>")
        sys.exit(1)
    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    """Download each book in list_file into dest_dir"""
    os.makedirs(dest_dir, exist_ok=True)
    downloaded_files = []

    # Read the URLs and skip the lines
    try:
        with open(list_file, "r") as f:
            urls = [line.strip() for line in f if line.strip()]
    except OSError as e:
        log.error(f"Cannot read book list: {e}")
        return []

    # Download each book
    for url in urls:
        filename = os.path.basename(url)
        path = os.path.join(dest_dir, filename)

        # Skip files that were already downloaded
        if os.path.exists(path):
            log.info(f"Skipping {filename}, already exists")
            downloaded_files.append(path)
            continue

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # raise an error for 404 etc.
            with open(path, "wb") as f:
                f.write(response.content)
            log.info(f"Downloaded {filename}")
            downloaded_files.append(path)
        except requests.RequestException as e:
            log.error(f"Error downloading {url}")

            time.sleep(1)

    return downloaded_files


def create_bucket(bucket):
    """Create the bucket if needed; return True if it exists afterwards."""
    # Check whether the bucket already exists
    try:
        s3.head_bucket(Bucket=bucket)
        log.info(f"Bucket exists: {bucket}")
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code not in ("404", "NoSuchBucket", "NotFound"):
            log.error(f"Error checking bucket {bucket}: {e}")
            return False

    # Creates the bucket
    try:
        s3.create_bucket(Bucket=bucket)
        log.info(f"Created bucket: {bucket}")
        return True
    except ClientError as e:
        log.error(f"Error creating bucket {bucket}: {e}")
        return False


def make_public(bucket):
    """Makes bucket publicly readable"""
    try:
        # Turn off Block Public Access
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )

        # Creates a readable public bucket
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
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))

        log.info(f"Bucket is publicly readable: {bucket}")
        return True
    except ClientError as e:
        log.error(f"Error making bucket public: {e}")
        return False


def upload_files(bucket, file_paths):
    """Return the number of files uploaded"""
    uploaded = 0
    for path in file_paths:
        key = os.path.basename(path)
        try:
            s3.upload_file(
                path,
                bucket,
                key,
                ExtraArgs={"ContentType": "text/plain; charset=utf-8"},
            )
            log.info(f"Uploaded {key}")
            uploaded += 1
        except (ClientError, S3UploadFailedError, FileNotFoundError) as e:
            log.error(f"Error uploading {path}: {e}")
    return uploaded


def upload_index(bucket, index_path):
    """Upload the index page as index.html"""
    if not os.path.exists(index_path):
        log.error(f"Index file not found: {index_path}")
        return False
    try:
        s3.upload_file(
            index_path,
            bucket,
            "index.html",
            ExtraArgs={"ContentType": "text/html"},
        )
        log.info("Uploaded index.html")
        return True
    except (ClientError, S3UploadFailedError) as e:
        log.error(f"Error uploading index page: {e}")
        return False


def main():
    """Download the books, set up the public bucket, and upload everything"""
    list_file, index_path, bucket = parse_args()

    # Download books
    file_paths = download_books(list_file, "books")
    if not file_paths:
        log.error("No books were downloaded.")
        sys.exit(1)

    # Create bucket
    if not create_bucket(bucket):
        log.error("Could not create bucket")
        sys.exit(1)

    # Makes bucket public
    if not make_public(bucket):
        log.error("Could not make bucket public")
        sys.exit(1)

    # Uploads the books
    uploaded = upload_files(bucket, file_paths)

    # Uploads the index
    index_ok = upload_index(bucket, index_path)

    url = f"https://{bucket}.s3.amazonaws.com/index.html"

    if uploaded == len(file_paths) and index_ok:
        log.info(f"Success: uploaded {uploaded} books and index.html")
        log.info(f"Public index: {url}")
    else:
        log.error(f"Finished with errors: {uploaded}/{len(file_paths)} books uploaded")
        log.info(f"Index URL: {url}")
        sys.exit(1)

if __name__ == "__main__":
    main()
