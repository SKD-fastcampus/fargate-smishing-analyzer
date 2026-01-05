#!/bin/bash

TARGET_URL=$1

if [ -z "$TARGET_URL" ]; then
  echo "Usage: ./run_task.sh <TARGET_URL>"
  exit 1
fi

echo "Triggering analysis for: $TARGET_URL"

aws ecs run-task \
  --cluster smishing-analysis-cluster \
  --task-definition smishing-analyzer \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0df98d0747157a6af,subnet-036c02d15ba75a859,subnet-06469bc1ec66a5b4c,subnet-047da211827c7d8ce],securityGroups=[sg-042b6749b75be2754],assignPublicIp=ENABLED}" \
  --overrides "containerOverrides=[{name='analyzer',environment=[{name='TARGET_URL',value='$TARGET_URL'}]}]" \
  --profile Admin@aground5

echo "Task started. Check ECS Console or S3 for results."
