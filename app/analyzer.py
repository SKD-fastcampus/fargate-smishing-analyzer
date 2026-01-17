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
    
def count_js_navigation(navigation_log, http_redirects, time_threshold=1.5):
    """
    JS redirect 판단 기준:
    - HTTP redirect가 아님
    - 이전 navigation 이후 매우 짧은 시간 내 발생
    - eTLD+1 이 다름
    """
    def root(url):
        try:
            print("url에서 root domain 추출 중...")
            h = urlparse(url).hostname
            if not h:
                return None
            return ".".join(h.split(".")[-2:])
        except Exception:
            print("root domain 추출 실패")
            return None

    # HTTP redirect로 이미 처리된 이동 쌍
    http_pairs = {
        (r["from"], r["to"]) for r in http_redirects
    }

    count = 0
    for i in range(1, len(navigation_log)):
        prev = navigation_log[i - 1]
        curr = navigation_log[i]

        # 시간 간격 체크 (자동 이동 여부)
        if curr["timestamp"] - prev["timestamp"] > time_threshold:
            continue

        prev_url = prev["url"]
        curr_url = curr["url"]

        # HTTP redirect면 제외
        if (prev_url, curr_url) in http_pairs:
            continue

        r1 = root(prev_url)
        r2 = root(curr_url)

        if r1 and r2 and r1 != r2:
            count += 1

    return count

def risk_scoring(elements):
    score = 0
    MAX_SCORE = 284
    
    # --------------------
    # HTTP Redirects
    # --------------------
    http_redirects = len(elements["redirect_chain"])

    if http_redirects >= 6:
        score += 25
    elif http_redirects >= 4:
        score += 18
    elif http_redirects >= 2:
        score += 10
    elif http_redirects == 1:
        score += 4
    
    # --------------------
    # JS Navigation Redirects
    # --------------------
    js_nav_count = count_js_navigation(
        elements.get("navigation_log", []),
        elements.get("redirect_chain", [])
    )


    if js_nav_count >= 3:
        score += 25
    elif js_nav_count == 2:
        score += 15
    elif js_nav_count == 1:
        score += 8
    
    # --------------------
    # Download attempt
    # --------------------
    if elements["downloads"]:
        score += 30
        
    # --------------------
    # External POST
    # --------------------
    page_root = ".".join(urlparse(elements["page_url"]).hostname.split(".")[-2:])
    external_posts = []

    for p in elements["post_requests"]:
        try:
            print("외부로 post하는지 url 비교로 확인 중..")
            post_root = ".".join(urlparse(p["url"]).hostname.split(".")[-2:])
            if post_root != page_root:
                external_posts.append(p)
        except Exception:
            print("외부 post 요청 확인 실패")

    if len(external_posts) >= 2:
        score += 25
    elif len(external_posts) == 1:
        score += 15
    
    # --------------------
    # UI Deception
    # --------------------
    ui = elements["ui_deception"]
    if ui["fullscreen"]:
        score += 10
    if ui["hidden_overflow"]:
        score += 8
        
    # --------------------
    # Keystroke Capture
    # --------------------
    kc = elements["keystroke_capture"]
    key_events = kc["onkeydown"] + kc["onkeypress"] + kc["onkeyup"]

    if key_events >= 3:
        score += 25
    elif key_events >= 1:
        score += 10
        
    # --------------------
    # eval usage
    # --------------------
    eval_cnt = elements["eval_usage_count"]
    if eval_cnt > 10:
        score += 25
    elif eval_cnt > 5:
        score += 18
    elif eval_cnt > 2:
        score += 10
    elif eval_cnt > 0:
        score += 5

    # --------------------
    # Tab / Navigation control
    # --------------------
    tc = elements["tab_control"]
    
    score += 8 if tc["before_unload"] else 0
    score += 8 if tc["onunload"] else 0
    score += 4 if tc["visibility_handler"] else 0
    score += 3 if tc["onblur"] else 0
    score += 3 if tc["onfocus"] else 0

    if tc["history_length"] > 3:
        score += 10

    # --------------------
    # Domain age
    # --------------------
    age = elements["domain_age"]
    if age in (-1, None):
        score += 30
    elif age < 7:
        score += 30
    elif age < 30:
        score += 20
    elif age < 90:
        score += 10
    elif age < 365:
        score += 5

    # --------------------
    # TLS / Certificate
    # --------------------
    tls = elements["tls_info"]
    if "error" in tls:
        score += 25
    else:
        if tls.get("cert_age_days", 9999) < 7:
            score += 20
        elif tls.get("cert_age_days", 9999) < 30:
            score += 10
            
    # --------------------
    # Domain mismatch
    # --------------------
    mismatches = elements["domain_mismatch"]

    external = [
        f for f in mismatches
        if f["mismatch"]
    ]

    suspicious_scheme = [
        f for f in mismatches
        if f["scheme_suspicious"]
    ]

    external_forms = len(external)
    scheme_forms = len(suspicious_scheme)
    
    if external_forms >= 2:
        score += 30
    elif external_forms == 1:
        score += 20

    if scheme_forms > 0:
        score += 15
    
    # --------------------
    # 백분율 반영 & limitation 반영
    # --------------------
    score = score/MAX_SCORE * 100
            
    if any(elements["limitation"].values()):
        score *= 0.8

    return score


def risk_leveling(risk_score):
    risk_level = "LOW"
    
    if risk_score >= 55:
        risk_level = "HIGH"
    elif risk_score >= 25:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
        
    return risk_level

async def analyze(config):
    playwright, browser, context = await launch_browser()
    
    stealth = Stealth()
    await stealth.apply_stealth_async(context)
    
    page = await context.new_page()
    
    network_data = attach_network_trackers(page)
        
    # 페이지 JS 동작 안정화 대기
    await page.wait_for_timeout(2000)
    
    try:
        print("새 page 생성")
        
        await page.goto(config["target_url"], timeout=30000, wait_until="domcontentloaded")
    except TimeoutError:
        print("timeout")
        elements = {"status": "timeout"}
    except Error as e:
        print(f"error 발생: {e}")
        if "Download is starting" in str(e):
            print("다운로드 전용 URL")
    
    try:
        elements = await collect_elements(page, context, network_data)
    except Exception as e:
        print(f"collect_elements 실패: {e}")
        elements = {"status": "error", "message": str(e)}
    finally:
        print("browser 닫는 중...")
        await browser.close()
        await playwright.stop()
    
    results = {
        "status": "err"
    }
    if elements["status"] == "ok":
        # =========================
        # 🔥 NO_DOM / Download only
        # =========================
        if elements.get("html") is None:
            results["status"] = "ok"
            results["user_id"] = config["user_id"]
            results["target_url"] = config["target_url"]
            results["final_url"] = elements["page_url"]
            results["screenshot"] = None
            results["summary"] = {
                "risk_score": 60,
                "risk_level": "HIGH"
            }
            results["details"] = {
                "redirect_chain": build_redirect_chain(elements),
                "download_attempt": build_download_attempt(elements)
            }
            results["confidence"] = {
                "analysis_coverage": "PARTIAL",
                "limitations": ["NO_DOM"]
            }
            return results
        risk_score = risk_scoring(elements)
        
        results["status"] = "ok"
        results["user_id"] = config["user_id"]
        results["target_url"] = config["target_url"]
        results["final_url"] = elements["page_url"]
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

        limitation = elements.get("limitation", {})

        if limitation.get("no_dom"):
            limitations.append("NO_DOM")
        elif any(limitation.values()):
            limitations.append("CAPTCHA")

        results["confidence"] = {
            "analysis_coverage": "PARTIAL" if limitations else "ALL",
            "limitations": limitations or None
        }

    return results
