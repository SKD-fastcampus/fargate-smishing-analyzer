#!/bin/bash

CLUSTER_NAME="smishing-analysis-cluster"
PROFILE="Admin@aground5"

echo "Checking tasks in cluster: $CLUSTER_NAME..."

# List tasks
TASK_ARNS=$(aws ecs list-tasks --cluster $CLUSTER_NAME --desired-status RUNNING --profile $PROFILE --query "taskArns[]" --output text)

if [ -z "$TASK_ARNS" ]; then
    echo "No running tasks found."
    
    # Check for recently stopped tasks (to see if they failed or finished)
    echo "Checking recently stopped tasks..."
    STOPPED_TASK_ARNS=$(aws ecs list-tasks --cluster $CLUSTER_NAME --max-items 5 --desired-status STOPPED --profile $PROFILE --query "taskArns[]" --output text)
    
    if [ -n "$STOPPED_TASK_ARNS" ] && [ "$STOPPED_TASK_ARNS" != "None" ]; then
        aws ecs describe-tasks --cluster $CLUSTER_NAME --tasks $STOPPED_TASK_ARNS --profile $PROFILE \
            --query "tasks[].{Arn:taskArn, Status:lastStatus, StoppedReason:stoppedReason, CreatedAt:createdAt}" \
            --output table
    else
        echo "No stopped tasks found either."
    fi
else
    # Describe running tasks
    aws ecs describe-tasks --cluster $CLUSTER_NAME --tasks $TASK_ARNS --profile $PROFILE \
        --query "tasks[].{Arn:taskArn, Status:lastStatus, Health:healthStatus, CreatedAt:createdAt}" \
        --output table
fi
