from browser import launch_browser
from page_elements_to_s3 import collect_elements
from playwright.sync_api import TimeoutError, Error
from playwright_stealth import stealth

def analyze(config):
    playwright, browser, context = launch_browser()
    
    page = context.new_page()
    stealth(page)
    
    try:
        page.goto(config["target_url"], timeout=30000, wait_until="domcontentloaded")
        results = collect_elements(page, context)
        
        # 여기서 수집해 온 페이지 요소 분석
        # 리다이렉트 체인, JS 리다이렉트 추적, html DOM input field 분석
        
    except TimeoutError:
        results = {"status": "timeout"}
    except Error as e:
        results = {"status": "error", "message": str(e)}
    finally:
        browser.close()
        playwright.stop()

    return results
