from browser import launch_browser
from app.page_elements import collect_elements, attach_network_trackers
from playwright.sync_api import TimeoutError, Error
from playwright_stealth import stealth
from urllib.parse import urlparse

def build_redirect_chain(elements):
    chain = []
    
    
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
    pass

def behavioral_findings(elements):
    return {
        "keystroke_capture": (
            elements["keystroke_capture"]["onkeydown"] > 0 or
            elements["keystroke_capture"]["onkeyup"] > 0
        ),
        "external_post_on_input": any(
            p for p in elements["post_requests"]
        ),
        "eval_usage_count": elements["eval_usage_count"],
        "tab_control_script": (
            elements["tab_control"]["before_unload"] or
            elements["tab_control"]["visibility_handler"]
        )
    }


def domain_analysis(elements):
    return {
        "domain_mismatch": any(
            f["mismatch"] for f in elements["domain_mismatch"]
        ),
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

def analyze(config):
    playwright, browser, context = launch_browser()
    
    page = context.new_page()
    stealth(page)
    
    try:
        network_data = attach_network_trackers(page)
        
        # 페이지 JS 동작 안정화 대기
        page.wait_for_timeout(2000)
        
        page.goto(config["target_url"], timeout=30000, wait_until="domcontentloaded")
        elements = collect_elements(page, context, network_data)
        
        # 여기서 수집해 온 페이지 요소 분석
        # 리다이렉트 체인, JS 리다이렉트 추적, html DOM input field 분석
        
    except TimeoutError:
        elements = {"status": "timeout"}
    except Error as e:
        elements = {"status": "error", "message": str(e)}
    finally:
        browser.close()
        playwright.stop()
    
    results = {
        "status": "err"
    }
    if elements["status"] == "ok":
        risk_score = risk_scoring(elements)
        
        results["status"] = "ok"
        results["user_id"] = config["user_id"]
        results["target_url"] = config["target_url"]
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
