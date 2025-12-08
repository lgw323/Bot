# -*- coding: utf-8 -*-
import sys
import asyncio
import os

# 모듈 경로 확보
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from modules import dumper, processor, analyzer, reporter

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    print("\n" + "=" * 50)
    print(" 🕵️‍♂️  DISCORD DEEP PROFILING SYSTEM (Standalone)")
    print("=" * 50)
    
    is_ok, msg = config.check_requirements()
    if is_ok:
        print(f"✅ 상태: {msg}")
        print(f"📂 저장소: {config.DATA_DIR}")
    else:
        print(f"❌ 오류: {msg}")
        print("   -> .env 파일을 확인해주세요.")
    print("-" * 50)

def print_menu():
    print("\n[ 작업 선택 ]")
    print(" 1. 📥 데이터 수집 (Channel Dump)")
    print("    - 3년 치 대화 내역 다운로드 (오래 걸림)")
    print(" 2. 🧹 데이터 전처리 & 통계 (Preprocessing)")
    print("    - 분석 대상자 확인 및 데이터 정제")
    print(" 3. 🧠 AI 성향 분석 (Gemini Profiling)")
    print("    - Gemini 2.5 Flash를 이용한 심층 분석")
    print(" 4. 📄 리포트 폴더 열기")
    print(" Q. 종료")
    print("-" * 50)

async def main():
    # 윈도우 콘솔 인코딩 문제 해결용
    if sys.platform.startswith('win'):
        os.system('chcp 65001')
        
    clear_screen()
    print_banner()

    is_ok, _ = config.check_requirements()
    if not is_ok:
        input("\n엔터 키를 누르면 종료합니다...")
        return

    while True:
        print_menu()
        choice = input(">> 실행할 작업 번호: ").strip().upper()

        if choice == '1':
            print("\n🚀 [모듈 1] 데이터 수집을 시작합니다...")
            await dumper.run_dump_process()
            
        elif choice == '2':
            print("\n🚀 [모듈 2] 데이터 전처리를 시작합니다...")
            processor.run_processing()

        elif choice == '3':
            print("\n🚀 [모듈 3] AI 분석을 시작합니다...")
            print("💡 분석 모드를 선택하세요:")
            print("   [A] 전원 분석 (All Users)")
            print("   [S] 특정 유저 1명 검색 (Single User)")
            sub_choice = input("   >> ").strip().upper()
            
            target = "ALL"
            if sub_choice == 'S':
                target = input("   >> 분석할 닉네임 입력 (정확히 입력): ").strip()
            
            await analyzer.run_analysis(target)

        elif choice == '4':
            print(f"\n📂 리포트 폴더를 엽니다...")
            reporter.open_report_folder()

        elif choice == 'Q':
            print("\n👋 프로그램을 종료합니다.")
            break
            
        else:
            print("❌ 잘못된 입력입니다.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⛔ 사용자 중단으로 종료되었습니다.")
    except Exception as e:
        print(f"\n❌ 치명적인 오류 발생: {e}")
        input("엔터를 누르면 종료합니다.")