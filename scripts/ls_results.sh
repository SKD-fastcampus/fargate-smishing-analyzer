#!/bin/bash

# Find the bucket name dynamically
BUCKET_NAME=$(aws s3 ls --profile Admin@aground5 | grep smishing-analysis-results- | awk '{print $3}')

if [ -z "$BUCKET_NAME" ]; then
  echo "Error: Could not find S3 bucket starting with 'smishing-analysis-results-'"
  exit 1
fi

echo "Found Bucket: $BUCKET_NAME"
echo "Listing analysis results..."
echo "---------------------------------------------------"

aws s3 ls s3://$BUCKET_NAME/analysis/ --recursive --profile Admin@aground5
