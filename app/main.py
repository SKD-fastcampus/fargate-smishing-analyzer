from analyzer import analyze
from config import load_config
from storage import upload_results

def main():
    config = load_config()
    results = analyze(config)
    
    if results["status"] == "ok":
        upload_results(results, config)
    
if __name__ == "__main__":
    main()