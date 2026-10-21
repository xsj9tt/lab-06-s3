#!/bin/bash
set -euo pipefail

# Check that all three arguments were given
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <book_url> <bucket> <expiration>"
    exit 1
fi

# Reads the arguments
BOOK_URL="$1"
BUCKET="$2"
EXPIRATION="$3"

# Gets the book filename
BOOK_FILENAME=$(basename "$BOOK_URL")

# Creates the books directory and downloads the book
mkdir -p books
curl -fL "$BOOK_URL" -o "books/$BOOK_FILENAME"

# Creates the bucket if it doesn't exist
if aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    echo "Bucket already exists: $BUCKET"
else
    aws s3 mb "s3://$BUCKET" --region us-east-1
fi

# Uploads the book to the bucket
aws s3 cp "books/$BOOK_FILENAME" "s3://$BUCKET/$BOOK_FILENAME" --content-type "text/plain; charset=utf-8"

# Assigns a presigned URL
echo "Presigned URL:"
aws s3 presign "s3://$BUCKET/$BOOK_FILENAME" --expires-in "$EXPIRATION"
