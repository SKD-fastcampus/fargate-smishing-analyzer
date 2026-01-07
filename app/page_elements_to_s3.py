def collect_elements(page, context):
    return {
        "status": "ok",
        "html": page.content(),
        "screenshot": page.screenshot(full_page=True),
        "cookies": context.cookies()
    }
