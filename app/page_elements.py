import ssl
import socket
import time
import whois
from urllib.parse import urlparse
from datetime import datetime, timezone

def attach_network_trackers(page):
    redirects = []
    navigation_log = []
    downloads = []
    post_requests = []
    js_eval_hits = []

    # --------------------
    # Network trackers
    # --------------------
    def on_request(request):
        if request.redirected_from:
            redirects.append({
                "from": request.redirected_from.url,
                "to": request.url
            })

        if request.method == "POST":
            post_requests.append({
                "url": request.url,
                "post_data": request.post_data
            })
    
    async def on_response(response):
        try:
            print("js 파일 불러오기(eval count)")
            ct = response.headers.get("content-type", "")
            if "javascript" in ct:
                body = await response.text()
                hits = body.count("eval(")
                if hits > 0:
                    js_eval_hits.append({
                        "url": response.url,
                        "count": hits
                    })
        except Exception as e:
            print(f"js 파일 불러오기 실패: {e}")

    def on_download(download):
        downloads.append({
            "url": download.url,
            "filename": download.suggested_filename
        })
        
    def on_frame_navigated(frame):
        if frame.parent_frame is None:  # main frame only
            navigation_log.append({
                "url": frame.url,
                "timestamp": time.time()
            })

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("download", on_download)
    page.on("framenavigated", on_frame_navigated)
    
    return {
        "redirects": redirects,
        "navigation_log": navigation_log,
        "downloads": downloads,
        "post_requests": post_requests,
        "js_eval_hits": js_eval_hits
    }

async def collect_elements(page, context, network_data): 
    parsed = urlparse(page.url)
    domain = parsed.hostname
    
    # Playwright가 에러 페이지에 있거나 도메인 해석에 실패했는지 확인
    is_invalid_domain = False
    if not domain or "about:blank" in page.url:
        is_invalid_domain = True
        
    # DOM 존재 여부 체크(only download 케이스)
    try:
        if is_invalid_domain:
            has_dom = False
        else:
            has_dom = await page.evaluate("() => !!document.body && document.body.innerText.length > 0")
    except Exception:
        has_dom = False
    
    if network_data["downloads"]:
        has_dom = False

    # --------------------
    # DOM 없는 다운로드 케이스 or 존재하지 않는 domain
    # --------------------
    if not has_dom or is_invalid_domain:
        return {
            "status": "ok",
            "page_url": page.url,

            # DOM 없음
            "html": None,
            "screenshot": None,
            "cookies": [],

            # network 중심 분석
            "redirect_chain": network_data["redirects"],
            "navigation_log": network_data["navigation_log"],
            "downloads": network_data["downloads"],
            "post_requests": network_data["post_requests"],

            # behavioral → 없음
            "ui_deception": {
                "fullscreen": False,
                "hidden_overflow": False
            },
            "keystroke_capture": {
                "onkeydown": 0,
                "onkeypress": 0,
                "onkeyup": 0
            },
            "eval_usage_count": 0,
            "tab_control": {
                "before_unload": False,
                "onunload": False,
                "visibility_handler": False,
                "onblur": False,
                "onfocus": False,
                "onresize": False,
                "history_length": 0
            },

            # domain / tls
            "domain_mismatch": [],
            "domain_age": None,
            "tls_info": {},

            "limitation": {
                "no_dom": True
            }
        }
        
    # --------------------
    # UI deception / DOM
    # --------------------
    ui_deception = await page.evaluate("""
    () => ({
        fullscreen: !!document.fullscreenElement,
        hidden_overflow: getComputedStyle(document.body).overflow === 'hidden'
    })
    """)

    # --------------------
    # Keystroke capture
    # --------------------
    keystroke_capture = await page.evaluate("""
    () => ({
        onkeydown: document.querySelectorAll('[onkeydown]').length,
        onkeypress: document.querySelectorAll('[onkeypress]').length,
        onkeyup: document.querySelectorAll('[onkeyup]').length
    })
    """)

    # --------------------
    # eval usage (STATIC SCAN)
    # --------------------
    eval_usage_count = sum(
        hit["count"] for hit in network_data["js_eval_hits"]
    )

    # --------------------
    # Tab / navigation control
    # --------------------
    tab_control = await page.evaluate("""
    () => ({
        // 탭 닫기 / 뒤로가기 방해
        before_unload: !!window.onbeforeunload,
        onunload: !!window.onunload,

        // 탭 전환 / 포커스 제어
        visibility_handler: document.onvisibilitychange !== null,
        onblur: !!window.onblur,
        onfocus: !!window.onfocus,

        // UI 재조정 기반 락 (모바일에서 중요)
        onresize: !!window.onresize,

        // history 조작 존재 여부
        history_length: history.length
    })
    """)

    # --------------------
    # Domain mismatch
    # --------------------
    domain_mismatch = await page.evaluate("""
    () => {
        const pageHost = location.hostname;
        const root = h => h?.split('.').slice(-2).join('.');

        return Array.from(document.querySelectorAll("form")).map(f => {
            const action = f.getAttribute("action") || "";
            let host = null;
            let schemeSuspicious = false;

            if (action.startsWith("javascript:") || action.startsWith("data:")) {
                schemeSuspicious = true;
            } else {
                try {
                    host = new URL(action, location.href).hostname;
                } catch(e) {}
            }

            return {
                action,
                host,
                mismatch: host && root(host) !== root(pageHost),
                scheme_suspicious: schemeSuspicious
            };
        });
    }
    """)


    # --------------------
    # TLS / certificate info
    # --------------------
    parsed = urlparse(page.url)
    domain = parsed.hostname
    host = domain
    
    tls_info = {}
    
    if parsed.scheme != "https" or not host:
        tls_info = {
            "https": False,
            "error": "not_https"
        }
        
    try:
        print("tls 연결 시작")
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=30) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                
                # --------------------
                # Parse certificate dates
                # --------------------
                not_before = datetime.strptime(
                    cert["notBefore"],
                    "%b %d %H:%M:%S %Y %Z"
                ).replace(tzinfo=timezone.utc)

                not_after = datetime.strptime(
                    cert["notAfter"],
                    "%b %d %H:%M:%S %Y %Z"
                ).replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                
                tls_info = {
                    "https": True,
                    # 발급자, 발급 시점, 만료 시점
                    "issuer": cert.get("issuer"),
                    "not_before": cert.get("notBefore"),
                    "not_after": cert.get("notAfter"),
                    
                    # --------------------
                    # Derived signals
                    # --------------------
                    "cert_age_days": (now - not_before).days,
                    "cert_validity_days": (not_after - not_before).days,
                    "days_until_expiry": (not_after - now).days
                }
    except Exception as e:
        print(f"tls 연결 실패: {e}")
        tls_info = {
            "https": True,
            "error": str(e)
        }

    # --------------------
    # Domain age
    # --------------------
    domain_age = None
    try:
        print("domain 정보 불러오기...")
        w = whois.whois(domain)

        created = w.creation_date
        if isinstance(created, list):
            created = created[0]

        if not created:
            domain_age = None

        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        domain_age = (now - created).days

    except Exception:
        print("domain 정보 불러오기 실패")
        domain_age = -1
    
    captcha_detected = await page.evaluate("""
    () => {
        return {
            recaptcha: !!document.querySelector('[src*="recaptcha"]'),
            hcaptcha: !!document.querySelector('[src*="hcaptcha"]'),
            cf_turnstile: !!document.querySelector('[src*="challenges.cloudflare.com"]')
        };
    }
    """)


    return {
        "status": "ok",
        "page_url": page.url,

        # raw
        "html": await page.content(),
        "screenshot": await page.screenshot(full_page=True),
        "cookies": await context.cookies(),

        # network
        "redirect_chain": network_data["redirects"],
        "navigation_log": network_data["navigation_log"],
        "downloads": network_data["downloads"],
        "post_requests": network_data["post_requests"],

        # behavioral
        "ui_deception": ui_deception,
        "keystroke_capture": keystroke_capture,
        "eval_usage_count": eval_usage_count,
        "tab_control": tab_control,

        # domain / tls
        "domain_mismatch": domain_mismatch,
        "domain_age": domain_age,
        "tls_info": tls_info,
        
        # limitation
        "limitation": captcha_detected
    }