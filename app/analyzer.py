from browser import launch_browser
from page_elements import collect_elements, attach_network_trackers
from playwright.sync_api import TimeoutError, Error
from playwright_stealth import Stealth
from urllib.parse import urlparse

def build_redirect_chain(elements):
    chain = []
    
    for r in elements["redirect_chain"]:
        chain.append({
            "type": "HTTP",   # JS redirect 추적하면 분리 가능
            "from": r["from"],
            "to": r["to"],
            "status": 302
        })
    
    # JS redirect (navigation_log 기반)
    nav_log = elements.get("navigation_log", [])
    for i in range(1, len(nav_log)):
        prev = nav_log[i - 1]["url"]
        curr = nav_log[i]["url"]
        if prev != curr:
            # 오탐 필터: 같은 eTLD면 제외
            def root(h):
                return ".".join(h.split(".")[-2:]) if h else None

            if root(prev) != root(curr):
                chain.append({
                    "type": "JS",
                    "from": prev,
                    "to": curr
                })
    
    return chain

def build_download_attempt(elements):
    if not elements["downloads"]:
        return {
            "attempted": False
        }

    d = elements["downloads"][0]
    return {
        "attempted": True,
        "filename": d["filename"],
        "auto_triggered": True
    }

def technical_findings(elements):
    return {
        "ui_deception": (
            elements["ui_deception"]["fullscreen"] or
            elements["ui_deception"]["hidden_overflow"]
        ),
        "domain_mismatch": any(
            f["mismatch"] or f["scheme_suspicious"]
            for f in elements["domain_mismatch"]
        )
    }

def behavioral_findings(elements):
    def is_external_post(post_url, page_url):
        page_root = ".".join(urlparse(page_url).hostname.split(".")[-2:])
        post_root = ".".join(urlparse(post_url).hostname.split(".")[-2:])
        return page_root != post_root

    external_posts = [
        p for p in elements["post_requests"]
        if is_external_post(p["url"], elements["page_url"])
    ]
    
    return {
        "keystroke_capture": (
            elements["keystroke_capture"]["onkeydown"] > 0 or
            elements["keystroke_capture"]["onkeypress"] > 0 or
            elements["keystroke_capture"]["onkeyup"] > 0
        ),
        "external_post_on_input": bool(external_posts),
        "eval_usage_count": elements["eval_usage_count"],
        "tab_control_script": (
            elements["tab_control"]["before_unload"] or
            elements["tab_control"]["onunload"] or
            elements["tab_control"]["visibility_handler"] or
            elements["tab_control"]["onblur"] or
            elements["tab_control"]["onfocus"] or
            elements["tab_control"]["onresize"] or
            elements["tab_control"]["history_length"] > 1
        )
    }


def domain_analysis(elements):
    return {
        "domain_age_days": elements["domain_age"]
    }

def certificate_analysis(elements):
    tls = elements["tls_info"]
    suspicious = False

    if "cert_age_days" in tls and tls["cert_age_days"] < 5:
        suspicious = True

    return {
        "issuer": tls.get("issuer"),
        "issued_days_ago": tls.get("cert_age_days"),
        "suspicious": suspicious
    }

def risk_scoring(elements):
    score = 0

    if elements["domain_age"] == -1 or elements["domain_age"] < 5:
        score += 20

    if elements["eval_usage_count"] > 5:
        score += 15

    if any(elements["downloads"]):
        score += 30

    if any(f["mismatch"] for f in elements["domain_mismatch"]):
        score += 25

    if elements["ui_deception"]["fullscreen"]:
        score += 10

    return min(score, 100)


def risk_leveling(risk_score):
    if risk_score >= 70:
        return "HIGH"
    elif risk_score >= 40:
        return "MEDIUM"
    else:
        return "LOW"

async def analyze(config):
    playwright, browser, context = await launch_browser()
    
    stealth = Stealth()
    await stealth.apply_stealth_async(context)
    
    page = await context.new_page()
    
    try:
        network_data = attach_network_trackers(page)
        
        # 페이지 JS 동작 안정화 대기
        await page.wait_for_timeout(2000)
        
        await page.goto(config["target_url"], timeout=30000, wait_until="domcontentloaded")
        elements = await collect_elements(page, context, network_data)
        
    except TimeoutError:
        elements = {"status": "timeout"}
    except Error as e:
        elements = {"status": "error", "message": str(e)}
    finally:
        await browser.close()
        await playwright.stop()
    
    results = {
        "status": "err"
    }
    if elements["status"] == "ok":
        risk_score = risk_scoring(elements)
        
        results["status"] = "ok"
        results["user_id"] = config["user_id"]
        results["target_url"] = config["target_url"]
        results["final_url"] = config["page_url"]
        results["screenshot"] = elements["screenshot"]
        results["summary"] = {
            "risk_score": risk_score,
            "risk_level": risk_leveling(risk_score)
        }
        results["details"] = {
            "redirect_chain": build_redirect_chain(elements),
            "download_attempt": build_download_attempt(elements),
            "technical_findings": technical_findings(elements),
            "behavioral_findings": behavioral_findings(elements),
            "domain_analysis": domain_analysis(elements),
            "certificate_analysis": certificate_analysis(elements)   
        }
        
        limitations = []
        
        if any(elements["limitation"].values()):
            limitations.append("CAPTCHA")

        results["confidence"] = {
            "analysis_coverage": "PARTIAL" if limitations else "ALL",
            "limitations": limitations or None
        }
    return results
