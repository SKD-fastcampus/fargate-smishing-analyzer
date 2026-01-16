from datetime import datetime, timezone
import re
import json
import boto3
import pymysql
import os
from dotenv import load_dotenv


def upload_results(results, config):
    results.pop("status", None)
    
    if results.get("screenshot"):
        try:
            print("S3 업로드 시작...")
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
            print(f"S3에 screenshot 업로드 실패: {e}")
    else:
        print("screenshot 없음 → S3 업로드 스킵")
        
    # DB 업로드 수행
    load_dotenv()  # .env 로드
    
    try:
        conn = pymysql.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT", 3306)),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"DB 연결 실패: {e}")
        raise
    
    try:
        with conn.cursor() as cursor:
            print("DB 업로드 시작...")
            primary_key_col = "result_id"
            
            primary_key_val = config.get("primary_key")
            if not primary_key_val:
                raise ValueError("primary_key 값이 존재하지 않습니다.")
            
            screenshot_path = None
            s = results.get("screenshot")
            if isinstance(s, dict):
                screenshot_path = f"s3://{s['bucket']}/{s['key']}"
            
            sql = f"""
            UPDATE analysis_results
            SET
                original_url = %s,
                final_url = %s,
                status = %s,
                risk_score = %s,
                screenshot_path = %s,
                details = %s,
                user_id = %s
            WHERE {primary_key_col} = %s
            """

            cursor.execute(
                sql,
                (
                    results.get("target_url"),              # original_url
                    results.get("final_url"),               # final_url
                    "DONE",                                 # status
                    results.get("summary", {}).get("risk_score"),   # risk_score
                    screenshot_path,                        # screenshot_path
                    json.dumps(results, ensure_ascii=False),# details (전체 분석 결과)
                    config.get("user_id"),                  # Field (user id)
                    primary_key_val
                )
            )

        conn.commit()
        
    except Exception as e:
        print(f"DB 업데이트 실패: {e}")
        conn.rollback()
        raise e
    
    finally:
        print("close the DB connection")
        conn.close()