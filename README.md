# AI 사용량 모니터 (AI Quota Monitor)

**Antigravity · Claude · Cursor · ChatGPT (Codex)** 4대 AI 코딩 에이전트의 **공식 한도(5시간 한도 / 주간 한도 / 월간 요청량)** 를 바탕화면 플로팅 위젯에서 실시간으로 확인하는 크로스플랫폼(macOS / Windows) 데스크톱 앱입니다.

---

## 주요 기능

- **4대 AI 에이전트 공식 쿼터 실시간 통합 조회**
  - **Antigravity**: 대표 3대 모델 그룹(`Gemini Models`, `Claude and GPT models`, `Gemini 4 Argon`)별 **5시간 한도(상단)** + **주간 한도(하단)** (총 3개 박스 · 6개 게이지 바)
  - **Claude (Claude Code / Pro / Max)**: **5시간 한도(상단)** + **주간 한도(하단)** 및 모델별 세부 주간 한도
  - **Cursor**: 월간 Fast Requests 사용량 / 잔여량 및 리셋 일정
  - **ChatGPT / Codex CLI**: **5시간 한도(상단)** + **주간 한도(하단)** 및 코드 리뷰 한도
- **사용량 기준 ↔ 잔여량 기준 원클릭 전환**
  - 기본값은 **사용량 기준 (`% 사용`)** 이며, 상단 헤더의 **`사용량 기준` / `잔여량 기준`** 버튼을 눌러 언제든 **남은 한도(`% 남음`)** 모드로 즉시 전환할 수 있습니다.
- **마우스 드래그 앤 드롭 순서 변경 (`⋮⋮`)**
  - 에이전트 카드(Antigravity, Claude, Cursor, ChatGPT) 순서뿐만 아니라 에이전트 내부의 모델 그룹 박스 순서까지 마우스로 직접 끌어 원하는 위치로 배치할 수 있습니다. 변경된 순서는 자동 저장됩니다.
- **개별 카드 및 모델 박스 접기 / 펼치기 (`▾`)**
  - 자주 보지 않는 에이전트 카드나 모델 박스를 클릭해 깔끔하게 접어둘 수 있으며, 접힌 상태에서도 핵심 퍼센트 배지를 한눈에 볼 수 있습니다.
- **원클릭 로그인 & 세션 유지**
  - 미로그인 에이전트는 **로그인** 버튼 하나만 깔끔하게 표시되며, 클릭 시 전용 로그인 창이나 공식 OAuth 인증으로 즉시 연동됩니다.
  - Rate Limit(429) 방어 및 로컬 캐시/토큰 자동 갱신이 내장되어 있어 로그인 풀림이나 깜빡임 없이 안정적으로 유지됩니다.
- **미니바 모드 & 항상 위 고정 (Pin)**
  - 작업 중 화면을 가리지 않도록 한 줄짜리 **미니바(`—`)** 로 축소하거나, **항상 위 고정(`📌`)** 을 켜고 끌 수 있습니다.

---

## 빠른 시작 (다운로드 및 실행)

> **사전 준비**: 시스템에 **Python 3.9 이상**이 설치되어 있어야 합니다.
> - **macOS**: 기본 설치되어 있거나 `brew install python` 또는 [python.org](https://www.python.org/downloads/)에서 설치
> - **Windows**: [python.org](https://www.python.org/downloads/)에서 설치 (**설치 시 반드시 `Add Python to PATH` 체크**)

### 1. 프로젝트 다운로드

```bash
git clone https://github.com/sungomi/ai-quota-widget.git
cd ai-quota-widget
```
*(Git을 사용하지 않는 경우, GitHub 페이지 우측 상단의 **Code → Download ZIP**을 눌러 압축을 풀어주세요.)*

---

### 2. macOS에서 실행하기

1. 폴더 안의 **`run_mac.command`** 파일을 더블클릭합니다.
   - 최초 실행 시 자동으로 가상환경(`.venv`)을 구성하고 필요한 패키지를 설치한 뒤 위젯을 띄웁니다.
2. **Mac 응용 프로그램(`/Applications`)에 앱으로 등록하려면**:
   - **`install_mac_app.command`** 파일을 더블클릭하세요.
   - 설치가 완료되면 Launchpad나 Spotlight(`⌘ + Space`)에서 **`AI Quota Monitor`** 를 검색해 일반 Mac 앱처럼 바로 실행할 수 있습니다.

> **참고 (macOS 보안 경고가 뜨는 경우)**  
> ZIP 파일로 다운로드한 경우 macOS Gatekeeper가 실행을 막을 수 있습니다. 터미널을 열고 폴더 경로에서 아래 명령어를 한 번 실행해 주세요:
> ```bash
> chmod +x *.command && xattr -cr .
> ```

---

### 3. Windows (PC)에서 실행하기

1. 폴더 안의 **`run_windows.bat`** 파일을 더블클릭합니다.
   - 최초 실행 시 자동으로 가상환경(`.venv`)과 필수 라이브러리를 설치한 뒤, 검은색 콘솔 창 없이 깔끔하게 위젯 창만 실행됩니다.
2. **바탕화면에 바로가기 아이콘을 만들려면**:
   - **`install_windows_shortcut.bat`** 파일을 더블클릭하세요.
   - 바탕화면에 **`AI 사용량 모니터`** 바로가기가 생성됩니다.

---

## 터미널 / CLI 모드로 확인하기

GUI 위젯을 띄우지 않고 터미널에서 즉시 현재 사용량/잔여량 수치만 출력하려면 `--cli` 옵션을 사용하세요:

```bash
# macOS
./run_mac.command --cli

# Windows
run_windows.bat --cli
```

---

## 에이전트별 로그인 방법

위젯 우측의 **`로그인`** 버튼을 누르면 각 에이전트에 맞는 인증이 자동으로 진행됩니다.

| 에이전트 | 인증 방식 |
| :--- | :--- |
| **Antigravity** | Google OAuth 브라우저 인증 (로컬 콜백으로 자동 완료 및 창 닫힘) |
| **Claude** | 로컬 Claude Code 자격증명 자동 감지 또는 플로팅 로그인 창에서 `claude.ai` 로그인 |
| **Cursor** | 로컬 Cursor IDE 로그인 세션 자동 감지 또는 플로팅 로그인 창에서 `cursor.com` 로그인 |
| **ChatGPT (Codex)** | 로컬 `~/.codex/auth.json` 자동 감지 또는 OpenAI 공식 OAuth 브라우저 로그인 |

---

## 설정 및 데이터 저장 위치

- 모든 로그인 세션 토큰, 캐시, 카드/박스 정렬 순서, 접기/펼치기 상태, 사용량/잔여량 표시 모드는 사용자 홈 디렉토리의 **`~/.ai_quota_widget.json`** (Windows: `%USERPROFILE%\.ai_quota_widget.json`)에 로컬로만 안전하게 저장되며 외부 서버로 전송되지 않습니다.
- 에이전트 계정을 초기화하거나 다른 계정으로 로그인하려면 위젯 내 각 카드 우측 상단의 **`로그아웃`**(`✕`) 버튼을 클릭하세요.

---

## 프로젝트 구조

```text
ai-quota-widget/
├── widget.py                     # PyWebView 기반 플로팅 데스크톱 위젯 UI 및 드래그/토글 로직
├── providers.py                  # Antigravity, Claude, Cursor, Codex 공식 쿼터 API 연동 및 캐싱
├── requirements.txt              # Python 필수 패키지 목록
├── pyproject.toml                # 프로젝트 메타데이터
├── run_mac.command               # [macOS] 원클릭 자동 설치 및 위젯 실행 스크립트
├── install_mac_app.command       # [macOS] /Applications 앱 번들 생성 스크립트
├── run_windows.bat               # [Windows] 원클릭 자동 설치 및 위젯 실행 스크립트
└── install_windows_shortcut.bat  # [Windows] 바탕화면 바로가기 생성 스크립트
```
