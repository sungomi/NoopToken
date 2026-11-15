# AI 사용량 모니터 v1.0 (AI Quota Monitor v1.0)

**Antigravity · Claude · Cursor · ChatGPT (Codex)** 4대 AI 코딩 에이전트의 **공식 한도(5시간 한도 / 주간 한도 / 월간 요청량)** 를 바탕화면 플로팅 위젯에서 실시간으로 확인하는 데스크톱 프로그램입니다.

> **코딩/파이썬 설치가 전혀 필요 없습니다!** 아래에서 본인 운영체제(Windows 또는 Mac)에 맞는 설치 파일 하나만 다운로드해 바로 실행하세요.

---

## 📥 바로 다운로드 (v1.0 정식 릴리즈)

| 운영체제 | 다운로드 링크 (클릭 시 바로 다운로드) | 실행 방법 |
| :--- | :--- | :--- |
| **🪟 Windows (PC)** | **[👉 AI-Quota-Monitor-v1.0-Windows.exe 다운로드](https://github.com/sungomi/ai-quota-widget/releases/download/v1.0/AI-Quota-Monitor-v1.0-Windows.exe)** | 다운로드한 **`.exe` 파일을 더블클릭**하면 바로 실행됩니다. |
| **🍎 macOS (Mac)** | **[👉 AI-Quota-Monitor-v1.0-macOS.dmg 다운로드](https://github.com/sungomi/ai-quota-widget/releases/download/v1.0/AI-Quota-Monitor-v1.0-macOS.dmg)** | 다운로드한 **`.dmg` 파일을 더블클릭**해 열고 **`AI Quota Monitor v1.0.app`** 을 실행(또는 `Applications` 폴더로 드래그)하세요. |

- 전체 릴리즈 페이지 보기: **[GitHub Releases (v1.0)](https://github.com/sungomi/ai-quota-widget/releases/tag/v1.0)**

---

## 🖥️ 처음 실행할 때 안내 (일반 사용자용)

### 1. Windows PC 사용자
1. 위의 **[AI-Quota-Monitor-v1.0-Windows.exe 다운로드](https://github.com/sungomi/ai-quota-widget/releases/download/v1.0/AI-Quota-Monitor-v1.0-Windows.exe)** 를 눌러 파일을 받습니다.
2. 다운로드된 `AI-Quota-Monitor-v1.0-Windows.exe`를 **더블클릭**합니다.
3. 만약 Windows에서 *"Windows의 PC 보호 (SmartScreen)"* 창이 뜨면 **`추가 정보(More info)` → `실행(Run anyway)`** 을 누르면 바로 위젯이 뜹니다.

### 2. Mac (macOS) 사용자
1. 위의 **[AI-Quota-Monitor-v1.0-macOS.dmg 다운로드](https://github.com/sungomi/ai-quota-widget/releases/download/v1.0/AI-Quota-Monitor-v1.0-macOS.dmg)** 를 눌러 파일을 받습니다.
2. `AI-Quota-Monitor-v1.0-macOS.dmg`를 더블클릭해 열고, 안의 **`AI Quota Monitor v1.0`** 아이콘을 **`Applications(응용 프로그램)`** 폴더로 끌어다 놓은 뒤 실행합니다.
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
3. **마우스 드래그 앤 드롭 순서 변경 (`⋮⋮`)**
   - 각 에이전트 카드 순서와 내부 모델 박스 순서를 마우스로 직접 끌어서 원하는 순서로 배치할 수 있습니다.
4. **개별 카드 및 모델 박스 접기 / 펼치기 (`▾`)**
   - 각 에이전트 카드나 모델 박스를 클릭해 접어둘 수 있으며, 접힌 상태에서도 핵심 퍼센트를 한눈에 볼 수 있습니다.
5. **원클릭 로그인 & 자동 세션 유지**
   - 미로그인 에이전트는 **`로그인`** 버튼 하나만 표시되며, 클릭 시 전용 로그인 창이나 브라우저 인증으로 즉시 연동됩니다.
6. **미니바 모드 (`—`) & 항상 위 고정 (`📌`)**
   - 작업 중 화면을 가리지 않도록 한 줄짜리 미니바로 줄이거나 항상 위 고정을 켜고 끌 수 있습니다.

---

## 🔑 에이전트별 로그인 방법

위젯 우측의 **`로그인`** 버튼을 누르면 각 에이전트에 맞는 인증이 자동으로 진행됩니다.

| 에이전트 | 인증 방식 |
| :--- | :--- |
| **Antigravity** | Google OAuth 브라우저 인증 (로컬 콜백으로 자동 완료 및 창 닫힘) |
| **Claude** | 로컬 Claude Code 자격증명 자동 감지 또는 플로팅 로그인 창에서 `claude.ai` 로그인 |
| **Cursor** | 로컬 Cursor IDE 로그인 세션 자동 감지 또는 플로팅 로그인 창에서 `cursor.com` 로그인 |
| **ChatGPT (Codex)** | 로컬 `~/.codex/auth.json` 자동 감지 또는 OpenAI 공식 OAuth 브라우저 로그인 |

---

## 🛠️ 개발자용 (소스코드로 직접 실행하고 싶은 경우)

파이썬(`Python 3.9+`) 환경에서 소스코드를 직접 수정하거나 실행하려면:

```bash
git clone https://github.com/sungomi/ai-quota-widget.git
cd ai-quota-widget

# macOS
./run_mac.command

# Windows
run_windows.bat
```
