from datetime import datetime, timezone
import re
import boto3

def upload_results(results, config):
    results.pop("status", None)
    
    try:
        # s3 클라이언트 생성
        s3 = boto3.client("s3", region_name=config["aws_region"])
        
        timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-").replace(".", "-")
        safe_url = re.sub(r"[^a-zA-Z0-9]", "_", config["target_url"])[:50]
        artifact_prefix = f"screenshots/{safe_url}"

        # 업로드
        s3.put_object(
            Bucket=config["s3_bucket_name"],
            Key=f"{artifact_prefix}/{timestamp}.png",
            Body=results["screenshot"],
            ContentType="image/png"
        )
        
        results["screenshots"] = {
            "provider": "s3",
            "bucket": config["s3_bucket_name"],
            "key": "{artifact_prefix}/{timestamp}.png",
            "region": config["aws_region"]
        }
        
    except Exception as e:
        print(f"Failed to upload screenshot: {e}")
    
    ### DB 업로드 수행