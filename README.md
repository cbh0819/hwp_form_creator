# hwp_form_creator

PDF 파일을 업로드하면 유사한 구조의 **HWP(X) 템플릿**을 자동으로 생성하는 서비스입니다.  
Claude AI가 PDF 내용을 분석하여 제목·본문·표 구조를 파악하고, 한글(HWP) 호환 포맷으로 변환합니다.

---

## 동작 원리

```
PDF 업로드
  │
  ▼
[1] PDF 파싱 (PyMuPDF)
    - 블록 단위 텍스트 추출 (폰트 크기·볼드 플래그 포함)
    - 표(Table) 자동 감지 및 셀 데이터 추출
    - 폰트 크기 비율로 H1/H2/H3 자동 분류
  │
  ▼
[2] 문서 구조 분석 (Claude API)
    - 추출된 텍스트를 Claude claude-sonnet-4-6에 전달
    - 제목/본문/표 블록 구조를 JSON으로 반환
  │
  ▼
[3] HWPX 파일 생성 (hwpx_generator)
    - JSON 계획을 바탕으로 HWPX XML 구성
    - ZIP 아카이브로 패키징 (.hwpx)
  │
  ▼
.hwpx 파일 다운로드
```

### 주요 컴포넌트

| 파일 | 역할 |
|------|------|
| `app/pdf_parser.py` | PyMuPDF(fitz)로 텍스트 블록·표·폰트 메타데이터 추출. 폰트 크기 비율 기반으로 H1/H2/H3 자동 분류, 표 영역 텍스트 중복 제거 |
| `app/llm_analyzer.py` | Claude API 호출. 추출된 텍스트를 12,000자 이내로 전달하고 구조화된 JSON 수신 |
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
- PyMuPDF >= 1.23.0 (`pymupdf`)
- [Anthropic API 키](https://console.anthropic.com/)

### 설치

```bash
git clone https://github.com/cbh0819/hwp_form_creator.git
cd hwp_form_creator
pip install -r requirements.txt
```

### 환경 변수 설정

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 서버 실행

```bash
uvicorn main:app --reload
```

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

API 키를 직접 전달하는 경우:

```bash
curl -X POST http://localhost:8000/generate \
  -F "file=@your_document.pdf" \
  -F "api_key=sk-ant-..." \
  -o output_template.hwpx
```

---

### `POST /preview` — 분석 결과 JSON 미리보기

HWPX 파일을 생성하기 전에 Claude가 파악한 문서 구조를 JSON으로 확인합니다.

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
    { "type": "heading", "content": "서비스 이용 신청서", "level": 1, "align": "center" },
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
| 제목 H1 | 16pt 볼드, 가운데 정렬 |
| 제목 H2 | 13pt 볼드, 왼쪽 정렬 |
| 제목 H3 | 11pt 볼드, 왼쪽 정렬 |
| 본문 단락 | 10pt, justify/left/center/right 정렬 선택 가능 |
| 표 | 헤더행 볼드 강조, 페이지 본문 너비에 맞게 컬럼 균등 분배 |
| 용지 | A4 기본 (width/height/margin mm 단위 커스텀 가능) |

---

## 라이선스

[MIT](LICENSE)
