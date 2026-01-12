import os

def load_config():
    # 환경변수 읽기
    TARGET_URL = os.getenv("TARGET_URL")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
    
    USER_ID = os.getenv("USER_ID")
    
    PRIMARY_KEY = os.getenv("PRIMARY_KEY")
    
    if not TARGET_URL:
        print("Error: TARGET_URL environment variable is not set.")
        exit(1)
    if not S3_BUCKET_NAME:
        print("Warning: S3_BUCKET_NAME environment variable is not set. Results will not be uploaded.")
    if not AWS_REGION:
        print("Error: AWS_REGION environment variable is not set. Results will not be uploaded.")
    if not PRIMARY_KEY:
        print("Error: PRIMARY_KEY environment variable is not set. Results will not be uploaded.")
        
    return {
        "target_url": TARGET_URL,
        "s3_bucket_name": S3_BUCKET_NAME,
        "aws_region": AWS_REGION,
        "user_id": USER_ID,
        "primary_key": PRIMARY_KEY
    }