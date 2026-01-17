import asyncio
from playwright.async_api import async_playwright

async def launch_browser():
    try:
        print("playwright browser launching...")
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(
            ignore_https_errors=True,
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/14.0 Mobile/15E148 Safari/604.1"
            ),
            record_har_path="network.har",
            record_har_content="embed"
        )
    except Exception as e:
        print("failed to launch browser")
        
    return playwright, browser, context
