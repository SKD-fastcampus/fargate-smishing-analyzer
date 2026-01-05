#!/bin/bash

TARGET_URL=$1
MAX_RETRIES=3
RETRY_COUNT=0
CLUSTER="smishing-analysis-cluster"
PROFILE="Admin@aground5"

if [ -z "$TARGET_URL" ]; then
  echo "Usage: $0 <TARGET_URL>"
  exit 1
fi

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    CURRENT_ATTEMPT=$((RETRY_COUNT + 1))
    echo "Attempt $CURRENT_ATTEMPT of $MAX_RETRIES..."

    # Run Task and capture ARN
    # Note: Using run_task.sh logic but inline to capture ARN
    TASK_JSON=$(aws ecs run-task \
      --cluster $CLUSTER \
      --task-definition smishing-analyzer \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=[subnet-0df98d0747157a6af,subnet-036c02d15ba75a859,subnet-06469bc1ec66a5b4c,subnet-047da211827c7d8ce],securityGroups=[sg-0b3c36f06a2e7799e],assignPublicIp=ENABLED}" \
      --overrides "containerOverrides=[{name='analyzer',environment=[{name='TARGET_URL',value='$TARGET_URL'}]}]" \
      --profile $PROFILE \
      --output json)

    TASK_ARN=$(echo $TASK_JSON | jq -r '.tasks[0].taskArn')

    if [ "$TASK_ARN" == "null" ]; then
        echo "Failed to start task."
        RETRY_COUNT=$((RETRY_COUNT + 1))
        continue
    fi

    echo "Task started: $TASK_ARN"
    echo "Waiting for task to complete..."
    
    # Wait for task to stop
    aws ecs wait tasks-stopped --cluster $CLUSTER --tasks $TASK_ARN --profile $PROFILE

    # Check exit code
    EXIT_CODE=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --profile $PROFILE --query "tasks[0].containers[0].exitCode" --output text)

    if [ "$EXIT_CODE" == "0" ]; then
        echo "Task completed successfully!"
        exit 0
    else
        echo "Task failed with exit code: $EXIT_CODE"
        RETRY_COUNT=$((RETRY_COUNT + 1))
        sleep 5
    fi
done

echo "Max retries reached. Analysis failed."
exit 1
