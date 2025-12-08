# -*- coding: utf-8 -*-
import os
import sys
from datetime import datetime

sys.path.append("..")
import config

def save_report(username, content):
    """개별 사용자의 리포트를 마크다운 파일로 저장"""
    # 파일명에 특수문자 제거
    safe_username = "".join([c for c in username if c.isalnum() or c in (' ', '_', '-')]).strip()
    filename = f"{safe_username}_Profile.md"
    filepath = config.REPORT_DIR / filename
    
    # 리포트 헤더 추가
    header = f"""# 🕵️‍♂️ {username} 심층 프로파일링 보고서
- **분석 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **분석 모델**: {config.GEMINI_MODEL}

---
"""
    final_content = header + content
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_content)
        # print(f"     📄 리포트 저장됨: {filename}") # Analyzer 로그와 겹쳐서 주석처리
    except Exception as e:
        print(f"     ❌ 파일 저장 실패 ({filename}): {e}")

def open_report_folder():
    """OS에 맞춰 폴더 열기"""
    path = str(config.REPORT_DIR)
    try:
        if os.name == 'nt':  # Windows
            os.startfile(path)
        elif sys.platform == 'darwin':  # macOS
            os.system(f'open "{path}"')
        else:  # Linux
            os.system(f'xdg-open "{path}"')
    except Exception as e:
        print(f"❌ 폴더 열기 실패: {e}")