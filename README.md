# <img src="assets/icon.png" width="32" height="32" align="center" /> AI 모니터 v1.0 (AI Monitor v1.0)

**Antigravity · Claude · Cursor · ChatGPT (Codex)** 4대 AI 코딩 에이전트의 **공식 한도(5시간 한도 / 주간 한도 / 월간 요청량)** 를 바탕화면 플로팅 위젯에서 실시간으로 확인하는 데스크톱 프로그램입니다.

> **코딩/파이썬 설치가 전혀 필요 없습니다!** 아래에서 본인 운영체제(Windows 또는 Mac)에 맞는 설치 파일 하나만 다운로드해 바로 실행하세요.

---

## 📥 바로 다운로드 (v1.0 정식 릴리즈)

| 운영체제 | 다운로드 링크 (클릭 시 바로 다운로드) | 실행 방법 |
| :--- | :--- | :--- |
| **🪟 Windows (PC)** | **[👉 AI-Quota-Monitor-v1.0-Windows.exe 다운로드](https://github.com/sungomi/ai-quota-widget/releases/download/v1.0/AI-Quota-Monitor-v1.0-Windows.exe)** | 다운로드한 **`.exe` 파일을 더블클릭**하면 바로 실행됩니다. |
| **🍎 macOS (Mac)** | **[👉 AI-Quota-Monitor-v1.0-macOS.dmg 다운로드](https://github.com/sungomi/ai-quota-widget/releases/download/v1.0/AI-Quota-Monitor-v1.0-macOS.dmg)** | 다운로드한 **`.dmg` 파일을 더블클릭**해 열고 **`AI Monitor v1.0.app`** 을 실행(또는 `Applications` 폴더로 드래그)하세요. |

- 전체 릴리즈 페이지 보기: **[GitHub Releases (v1.0)](https://github.com/sungomi/ai-quota-widget/releases/tag/v1.0)**

---

## 🖥️ 처음 실행할 때 안내 (일반 사용자용)

### 1. Windows PC 사용자
1. 위의 **[AI-Quota-Monitor-v1.0-Windows.exe 다운로드](https://github.com/sungomi/ai-quota-widget/releases/download/v1.0/AI-Quota-Monitor-v1.0-Windows.exe)** 를 눌러 파일을 받습니다.
2. 다운로드된 `AI-Quota-Monitor-v1.0-Windows.exe`를 **더블클릭**합니다.
3. 만약 Windows에서 *"Windows의 PC 보호 (SmartScreen)"* 창이 뜨면 **`추가 정보(More info)` → `실행(Run anyway)`** 을 누르면 바로 실행됩니다.
4. **업데이트 시에도 로그인 유지**: 새 버전의 `.exe`를 받아 실행해도 기존 로그인 정보(`%USERPROFILE%\.ai_quota_widget.json`)는 풀리지 않고 그대로 유지됩니다.

### 2. Mac (macOS) 사용자
1. 위의 **[AI-Quota-Monitor-v1.0-macOS.dmg 다운로드](https://github.com/sungomi/ai-quota-widget/releases/download/v1.0/AI-Quota-Monitor-v1.0-macOS.dmg)** 를 눌러 파일을 받습니다.
2. `AI-Quota-Monitor-v1.0-macOS.dmg`를 더블클릭해 열고, 안의 **`AI Monitor v1.0`** 아이콘을 **`Applications(응용 프로그램)`** 폴더로 끌어다 놓은 뒤 실행합니다.
3. 최초 실행 시 *"개발자를 확인할 수 없기 때문에 열 수 없습니다"* 안내가 뜨면:
   - 앱 아이콘을 **우클릭(Control + 클릭) → `열기(Open)`** 를 누르거나,
   - `시스템 설정 → 개인정보 보호 및 보안` 하단에서 **`확인 없이 열기`** 를 누르면 정상 실행됩니다.

---

## ✨ 주요 기능

1. **4대 AI 에이전트 공식 사용량 실시간 통합 조회**
   - **Antigravity**: 대표 3대 모델 그룹(`Gemini Models`, `Claude and GPT models`, `Gemini 4 Argon`)별 **5시간 한도(상단)** + **주간 한도(하단)** (총 3개 박스 · 6개 게이지 바)
   - **Claude (Claude Code / Pro / Max)**: **5시간 한도(상단)** + **주간 한도(하단)** 및 모델별 세부 주간 한도
   - **Cursor**: 월간 Fast Requests 사용량 / 잔여량 및 리셋 일정
   - **ChatGPT / Codex CLI**: **5시간 한도(상단)** + **주간 한도(하단)** 및 코드 리뷰 한도
2. **사용량 기준 (`% 사용`) ↔ 잔여량 기준 (`% 남음`) 원클릭 전환**
   - 기본값은 **사용량 기준 (`% 사용`)** 이며, 상단 헤더의 **`사용량 기준` / `잔여량 기준`** 버튼을 눌러 언제든 **남은 한도(`% 남음`)** 모드로 즉시 바꿀 수 있습니다.
3. **크롬(Chrome) 기본 프로필 연동 원클릭 로그인**
   - 크롬이 설치되어 있으면 **기존 크롬 큰 창**이 바로 열려, 이미 로그인된 Google / Claude / OpenAI 계정을 클릭 한 번으로 선택해 즉시 연동할 수 있습니다. (크롬 미설치 시 전용 플로팅 로그인 창 자동 실행)
4. **마우스 드래그 앤 드롭 순서 변경 (`⋮⋮`) & 접기/펼치기 (`▾`)**
   - 각 에이전트 카드 순서와 내부 모델 박스 순서를 마우스로 직접 끌어 배치하고, 클릭해 접거나 펼칠 수 있습니다.
5. **업데이트 시에도 로그인 영구 유지**
   - 모든 인증 토큰과 설정은 사용자 홈 폴더(`~/.ai_quota_widget.json`)에 별도 보관되어, 앱을 업데이트하거나 재설치해도 로그인이 풀리지 않습니다.
