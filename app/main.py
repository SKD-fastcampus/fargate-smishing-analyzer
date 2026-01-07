from analyzer import analyze
from config import load_config
from storage import upload_results

def main():
    config = load_config()
    results = analyze(config)
    
    if results["status"] == "ok":
        upload_results(results, config) # s3에 업로드
        
    # 어떤 데이터를 가져와서(page_elements_to_s3)
    # 어떻게 분석하고(analyzer) 점수 산출해서
    # db에 무엇을 올릴까
    
if __name__ == "__main__":
    main()