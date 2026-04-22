# hwp_form_creator

PDF 파일을 업로드하면 유사한 구조의 **HWP(X) 템플릿**을 자동으로 생성하는 서비스입니다.  
외부 API 없이 PyMuPDF의 레이아웃 분석만으로 동작합니다.

---

## 동작 원리

```
PDF 업로드
  │
  ▼
[1] PDF 파싱 (PyMuPDF)
    - 블록 단위 텍스트 추출 (폰트 크기·볼드 플래그 포함)
    - 표(Table) 자동 감지 및 셀 데이터 추출
    - 표 영역과 겹치는 텍스트 블록 중복 제거
  │
  ▼
[2] 문서 구조 변환 (pdf_parser.to_document_plan)
    - 폰트 크기 비율로 H1/H2/H3 자동 분류
    - 페이지·수직 위치 기준 읽기 순서 정렬
    - HeadingBlock / ParagraphBlock / TableBlock 으로 매핑
  │
  ▼
[3] HWPX 파일 생성 (hwpx_generator)
    - HWPX XML 구성 (폰트·스타일·용지 설정 포함)
    - ZIP 아카이브로 패키징 (.hwpx)
  │
  ▼
.hwpx 파일 다운로드
```

### 주요 컴포넌트

| 파일 | 역할 |
|------|------|
| `app/pdf_parser.py` | PyMuPDF(fitz)로 텍스트 블록·표·폰트 메타데이터 추출. 폰트 크기 비율 기반 H1/H2/H3 분류, 읽기 순서 정렬, `DocumentPlan` 직접 생성 |
| `app/hwpx_generator.py` | HWPX(HWP Open XML) 포맷의 ZIP 파일 생성. 폰트·스타일·용지 설정을 header.xml에, 본문을 section0.xml에 작성 |
| `app/models.py` | `HeadingBlock` / `ParagraphBlock` / `TableBlock` Pydantic 모델 |
| `app/api.py` | FastAPI 라우터 (`/generate`, `/preview`) |

### HWPX 파일 구조

```
document.hwpx (ZIP)
├── mimetype
├── META-INF/container.xml    ← 루트 파일 지시자
└── Contents/
    ├── content.hpf           ← 패키지 디스크립터
    ├── header.xml            ← 폰트·스타일·용지 설정
    └── section0.xml          ← 본문 (단락·표)
```

---

## 설치 및 실행

### 요구 사항

- Python 3.11 이상
- PyMuPDF >= 1.23.0

---

### Windows

**1. Python 설치**

[python.org](https://www.python.org/downloads/)에서 Python 3.11 이상을 내려받아 설치합니다.  
설치 시 **"Add Python to PATH"** 옵션을 반드시 체크하세요.

**2. 저장소 클론 및 의존성 설치**

```powershell
git clone https://github.com/cbh0819/hwp_form_creator.git
cd hwp_form_creator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**3. 서버 실행**

```powershell
uvicorn main:app --reload
```

**4. API 호출 (PowerShell)**

```powershell
# /generate
Invoke-RestMethod -Uri "http://localhost:8000/generate" `
  -Method Post `
  -Form @{ file = Get-Item "your_document.pdf" } `
  -OutFile "output_template.hwpx"

# /preview
Invoke-RestMethod -Uri "http://localhost:8000/preview" `
  -Method Post `
  -Form @{ file = Get-Item "your_document.pdf" }
```

> curl이 설치되어 있다면 Linux/macOS와 동일한 curl 명령을 사용할 수 있습니다.

---

### macOS

**1. Python 설치**

```bash
# Homebrew를 이용한 설치 (권장)
brew install python@3.11
```

또는 [python.org](https://www.python.org/downloads/)에서 직접 설치합니다.

**2. 저장소 클론 및 의존성 설치**

```bash
git clone https://github.com/cbh0819/hwp_form_creator.git
cd hwp_form_creator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. 서버 실행**

```bash
uvicorn main:app --reload
```

**4. API 호출**

```bash
# /generate
curl -X POST http://localhost:8000/generate \
  -F "file=@your_document.pdf" \
  -o output_template.hwpx

# /preview
curl -X POST http://localhost:8000/preview \
  -F "file=@your_document.pdf"
```

---

### Linux

**1. Python 설치**

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip

# Fedora / RHEL
sudo dnf install -y python3.11
```

**2. 저장소 클론 및 의존성 설치**

```bash
git clone https://github.com/cbh0819/hwp_form_creator.git
cd hwp_form_creator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. 서버 실행**

```bash
uvicorn main:app --reload
```

**4. API 호출**

```bash
# /generate
curl -X POST http://localhost:8000/generate \
  -F "file=@your_document.pdf" \
  -o output_template.hwpx

# /preview
curl -X POST http://localhost:8000/preview \
  -F "file=@your_document.pdf"
```

---

서버가 실행되면 `http://localhost:8000/docs` 에서 Swagger UI를 통해 바로 테스트할 수 있습니다.

---

## API 사용법

### `POST /generate` — PDF → HWPX 변환

PDF를 업로드하면 `.hwpx` 파일을 반환합니다.

```bash
curl -X POST http://localhost:8000/generate \
  -F "file=@your_document.pdf" \
  -o output_template.hwpx
```

---

### `POST /preview` — 분석 결과 JSON 미리보기

HWPX 파일을 생성하기 전에 파싱된 문서 구조를 JSON으로 확인합니다.

```bash
curl -X POST http://localhost:8000/preview \
  -F "file=@your_document.pdf"
```

응답 예시:

```json
{
  "title": "서비스 이용 신청서",
  "page": {
    "width_mm": 210,
    "height_mm": 297,
    "margin_left_mm": 30,
    "margin_right_mm": 30,
    "margin_top_mm": 20,
    "margin_bottom_mm": 15
  },
  "blocks": [
    { "type": "heading", "content": "서비스 이용 신청서", "level": 1, "align": "left" },
    { "type": "paragraph", "content": "아래와 같이 신청합니다.", "align": "justify", "bold": false },
    {
      "type": "table",
      "has_header": true,
      "rows": [
        ["항목", "내용"],
        ["신청인", "홍길동"],
        ["연락처", "010-0000-0000"]
      ]
    }
  ]
}
```

---

### `GET /health` — 헬스 체크

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

---

## 지원 문서 요소

| 요소 | 세부 사항 |
|------|----------|
| 제목 H1 | 16pt 볼드, 왼쪽 정렬 |
| 제목 H2 | 13pt 볼드, 왼쪽 정렬 |
| 제목 H3 | 11pt 볼드, 왼쪽 정렬 |
| 본문 단락 | 10pt, justify 정렬 |
| 표 | 헤더행 볼드 강조, 페이지 본문 너비에 맞게 컬럼 균등 분배 |
| 용지 | PDF 원본 크기 자동 감지 (기본 A4) |

---

## 라이선스

[MIT](LICENSE)
