# Q-Menu

Q-Menu는 단일 HTML 기반 고객 앱과 관리자 대시보드, FastAPI, Supabase,
Google Gemini를 연결한 매장 주문·예약 데모입니다. 기존 UI와 좌석 배치 편집기를
유지하면서 Vercel의 정적 파일 및 Python Function 구조에 맞췄습니다.

## 주요 기능

고객 앱:

- 매장 정보, 메뉴, 실내·테라스 좌석 배치 및 상태 조회
- 테이블별 `store&table_id=...` QR 진입과 해당 테이블에 고정된 메뉴 주문
- 이용 가능·예약 테이블 QR 스캔 시 해당 좌석을 즉시 `occupied`로 전환
- 좌석 예약 및 웨이팅 요청
- 고객 브라우저 UUID별 주문·예약 현황 조회와 5초 갱신
- 최신 매장·판매 메뉴·좌석 데이터를 사용하는 AI 메뉴 및 좌석 안내
- `web` 모드의 조회·AI 전용 동작

관리자 대시보드:

- 주문·예약·웨이팅 현황 5초 갱신 및 상태 처리
- 매장 정보, 추천 키워드, 메뉴 및 품절 상태 관리
- 좌석 선택, 드래그, 추가, 삭제, 위치·상태·뷰·태그 편집
- 현재 배포 도메인을 사용하는 외부용 QR과 저장된 테이블별 매장 주문 QR 생성
- 드래그 방식의 테이블 QR 표시 순서 변경 및 저장
- 다크·라이트 모드

## 데이터 흐름

브라우저는 같은 도메인의 `/api/*` 상대 경로만 호출합니다. FastAPI는 서버
환경 변수의 Supabase Secret key 또는 레거시 `service_role` 키로 PostgreSQL에
접근합니다. 서비스 키는 HTML, JavaScript, QR 또는 API 응답에 포함되지
않습니다.

운영 데이터는 `stores`, `menus`, `tables`, `orders`, `reservations`에
저장됩니다. 웨이팅은 별도 큐가 아니라 `reservations.status = 'waiting'`으로
집계됩니다. 추천 키워드는 `stores.recommendation_keywords`에 저장됩니다.

좌석 배치 전체 저장과 예약 승인·취소에 따른 좌석 상태 변경은 SQL 함수 안에서
트랜잭션으로 처리됩니다. 관리자가 좌석 상태를 직접 저장한 시점과 예약 처리
시점이 겹치면 마지막으로 완료된 작업이 기준이 됩니다. 예약 승인 시 좌석은
`reserved`, 취소 시 다른 활성 예약이 없는 좌석은 `available`이 됩니다.
테이블 QR 주문은 주문 생성과 함께 해당 좌석을 `occupied`로 바꾸며, 이 처리는
SQL 함수 안에서 하나의 트랜잭션으로 수행됩니다.

## 디렉터리

```text
.
|-- api/
|   `-- index.py
|-- public/
|   |-- index.html
|   |-- admin.html
|   `-- app.html
|-- .env.example
|-- .gitignore
|-- .python-version
|-- DEPLOYMENT.md
|-- README.md
|-- requirements.txt
|-- schema.sql
|-- seed.sql
`-- vercel.json
```

## API

| Method | Path | 역할 |
|---|---|---|
| GET | `/api/health` | API, DB, Gemini 설정 상태 |
| GET, PUT | `/api/store` | 매장 정보 조회·저장 |
| GET, POST | `/api/menus` | 메뉴 목록·등록 |
| PUT, DELETE | `/api/menus/{menu_id}` | UUID 기반 메뉴 수정·삭제 |
| GET, PUT | `/api/tables` | 좌석 배치 조회·일괄 저장 |
| POST | `/api/tables/{table_code}/occupy` | 테이블 QR 입장 및 이용 중 전환 |
| PUT | `/api/tables/order` | 테이블 QR 표시 순서 저장 |
| GET, PUT | `/api/keywords` | 추천 키워드 조회·저장 |
| GET, POST | `/api/orders` | 주문 조회·등록 |
| PUT | `/api/orders/{order_id}/status` | 주문 상태 변경 |
| GET, POST | `/api/reservations` | 예약·웨이팅 조회·등록 |
| PUT | `/api/reservations/{reservation_id}/status` | 예약 승인·취소 |
| GET | `/api/queue/status` | 실제 웨이팅 집계 |
| POST | `/api/chat` | 최신 DB 문맥 기반 AI 안내 |
| GET | `/api/docs` | FastAPI 문서 |

고객용 `GET /api/orders`와 `GET /api/reservations`는
`customer_session_id` query parameter를 사용하면 해당 브라우저의 데이터만
반환합니다. 관리자 화면은 parameter 없이 전체 데이터를 조회합니다.

## 환경 변수

`.env.example`을 참고해 실제 값은 로컬 `.env` 또는 Vercel 환경 변수에만
설정합니다.

- `GEMINI_API_KEY`: Google AI Studio에서 발급한 서버 API 키
- `GEMINI_MODEL`: 기본값 `gemini-3.6-flash`
- `SUPABASE_URL`: Supabase 프로젝트 URL
- `SUPABASE_SERVICE_KEY`: 서버 전용 Secret key 또는 레거시 `service_role`
- `DEFAULT_STORE_ID`: `seed.sql` 기준
  `11111111-1111-4111-8111-111111111111`
- `ALLOWED_ORIGINS`: 분리 실행 시 허용할 origin의 쉼표 구분 목록

Supabase 설정이 없으면 데이터 API는 `503` 설정 오류를 반환합니다.

## 로컬 실행

Python 3.12 환경에서 의존성을 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

전체 정적 페이지와 API 라우팅은 Vercel CLI로 실행하는 것이 배포 환경과 가장
가깝습니다.

```powershell
vercel dev
```

API만 확인할 때는 다음 명령을 사용할 수 있습니다.

```powershell
python -m uvicorn api.index:app --reload
```

## 메뉴 이미지

이번 버전은 Supabase Storage 대신 기존 Base64 또는 URL 방식을 유지합니다.
관리자 브라우저에서 JPEG, PNG, WEBP만 허용하고 원본 5MB, 긴 변 800px,
출력 품질 0.8 기준으로 리사이징합니다. 메뉴 관리 화면은 리사이징 결과를 2MB로
제한하고, 고객 리뷰 사진은 원본과 처리 결과를 모두 5MB로 제한합니다. 서버의
Base64 이미지 검증 한도도 5MB입니다. 수정 시 새 이미지를 선택하지 않으면 기존
이미지를 유지합니다.

## 현재 제한사항

- 로그인·회원가입은 데모 UI이며 이메일·비밀번호 인증을 수행하지 않습니다.
- 관리자 페이지와 변경 API는 실제 인증으로 보호되지 않습니다. 상용 배포 전
  Supabase Auth 또는 별도 관리자 인증과 권한 검사가 필요합니다.
- `mode=web|store`는 기능 분리 값이며 보안 권한이 아닙니다. 매장 전용 접근
  토큰은 후속 구현이 필요합니다. 매장용 QR은 `table_id`로 주문 테이블을
  고정하지만 별도의 인증 토큰 역할을 하지는 않습니다.
- 5초 폴링을 사용하며 WebSocket 기반 완전한 실시간 동기화는 아닙니다.
- 실제 결제, PWA, 푸시 알림, 다중 지점 및 정교한 통계는 포함하지 않습니다.
- 메뉴 번역은 기존 입력 구조를 유지하며 자동 번역하지 않습니다.
- QR 이미지는 외부 생성 서비스에 의존하지만 URL 텍스트와 복사 기능은 항상
  사용할 수 있습니다.

자세한 배포 순서는 [DEPLOYMENT.md](DEPLOYMENT.md)를 참고하세요.
