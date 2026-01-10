# 공식 Playwright Python 이미지 (Chromium 포함)
FROM mcr.microsoft.com/playwright/python:v1.57.0

# 작업 디렉토리
WORKDIR /app

# Python 패키지 복사
COPY requirements.txt .

# Python 라이브러리 설치
RUN pip install --no-cache-dir -r requirements.txt

# Playwright 브라우저 설치 (이미지에 포함돼 있지만 안전하게)
# RUN playwright install chromium

# 앱 코드 복사
COPY . /app

# 컨테이너 실행 시 명령
CMD ["python", "app/main.py"]
