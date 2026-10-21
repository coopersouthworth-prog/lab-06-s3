#!/bin/bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 BOOK_URL BUCKET EXPIRES_IN_SECONDS" >&2
    exit 1
fi

BOOK_URL="$1"
BUCKET="$2"
EXPIRES="$3"

if ! [[ "$EXPIRES" =~ ^[0-9]+$ ]]; then
    echo "Error: EXPIRES_IN_SECONDS must be a positive integer" >&2
    exit 1
fi

FILENAME="$(basename "$BOOK_URL")"

# Download the book into books/
mkdir -p books
echo "Downloading $FILENAME..." >&2
curl -fsSL -o "books/$FILENAME" "$BOOK_URL"

if aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    echo "Bucket $BUCKET already exists" >&2
else
    aws s3 mb "s3://$BUCKET" --region us-east-1 >&2
fi

aws s3 cp "books/$FILENAME" "s3://$BUCKET/$FILENAME" \
    --content-type "text/plain; charset=utf-8" >&2

URL="$(aws s3 presign "s3://$BUCKET/$FILENAME" --expires-in "$EXPIRES")"
echo "Presigned URL (expires in $EXPIRES seconds):" >&2
echo "$URL"
