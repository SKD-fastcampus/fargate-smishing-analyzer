#!/bin/bash
set -e

# Configuration
AWS_REGION="ap-northeast-2"
REPO_NAME="smishing-bot"
TAG="latest"

# Get Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --profile Admin@aground5 --query Account --output text)
ECR_URL="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_IMAGE_NAME="${ECR_URL}/${REPO_NAME}:${TAG}"

echo "Login to ECR..."
aws ecr get-login-password --region ${AWS_REGION} --profile Admin@aground5 | docker login --username AWS --password-stdin ${ECR_URL}

# Determine script directory to find app folder
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${SCRIPT_DIR}/../app"

echo "Building Docker Image from ${APP_DIR}..."
docker build --platform linux/amd64 --provenance=false -t ${REPO_NAME} "${APP_DIR}"

echo "Tagging Image..."
docker tag ${REPO_NAME}:${TAG} ${FULL_IMAGE_NAME}

echo "Pushing Image to ECR..."
docker push ${FULL_IMAGE_NAME}

echo "Done! Image pushed to: ${FULL_IMAGE_NAME}"
