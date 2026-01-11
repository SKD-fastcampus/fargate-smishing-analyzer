from datetime import datetime, timezone
import re
import json
import boto3
import pymysql
import os
from dotenv import load_dotenv

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
        
        results["screenshot"] = {
            "provider": "s3",
            "bucket": config["s3_bucket_name"],
            "key": f"{artifact_prefix}/{timestamp}.png",
            "region": config["aws_region"]
        }
        
    except Exception as e:
        print(f"Failed to upload screenshot: {e}")
    
    # DB 업로드 수행
    load_dotenv()  # .env 로드
    
    conn = pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )
    
    try:
        with conn.cursor() as cursor:
            sql = """
            INSERT INTO AnalysisResults (
                original_url,
                final_url,
                status,
                risk_score,
                screenshot_path,
                details,
                Field
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s
            )
            """

            screenshot_path = None
            if "screenshot" in results:
                s = results["screenshot"]
                screenshot_path = f"s3://{s['bucket']}/{s['key']}"

            cursor.execute(
                sql,
                (
                    results.get("target_url"),              # original_url
                    results.get("final_url"),               # final_url
                    "DONE",                                 # status
                    results.get("risk_score"),              # risk_score
                    screenshot_path,                        # screenshot_path
                    json.dumps(results, ensure_ascii=False),# details (전체 분석 결과)
                    config.get("user_id")                   # Field (user id)
                )
            )

        conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise e
    
    finally:
        conn.close()