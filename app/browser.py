from playwright.sync_api import sync_playwright

def launch_browser():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage"
        ]
    )
    context = browser.new_context(
        ignore_https_errors=True,
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/14.0 Mobile/15E148 Safari/604.1"
        ),
        record_har_path="network.har",
        record_har_content="embed"
    )
    return playwright, browser, context
