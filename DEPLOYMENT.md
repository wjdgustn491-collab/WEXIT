# Q-Menu Vercel 배포 안내

이 문서는 Supabase와 Google Gemini를 연결한 뒤 현재 프로젝트를 Vercel에 배포하는
순서입니다. 실제 비밀키는 파일이나 Git 저장소에 기록하지 마세요.

## 1. Supabase 프로젝트 생성

1. Supabase Dashboard에서 새 프로젝트를 만듭니다.
2. 프로젝트 생성이 끝나면 왼쪽 메뉴에서 `SQL Editor`를 엽니다.

## 2. 데이터베이스 구성

1. `schema.sql` 전체를 SQL Editor에 붙여 넣고 실행합니다.
2. 오류 없이 완료되면 `seed.sql` 전체를 새 쿼리에서 실행합니다.
3. `Table Editor`에서 `stores`, `menus`, `tables`, `orders`,
   `reservations` 테이블을 확인합니다.
4. `Database > Functions` 또는 SQL 조회로
   `replace_store_tables`, `update_reservation_and_table` 함수가 생성됐는지
   확인합니다.

`seed.sql`의 기본 매장 ID는 다음과 같습니다.

```text
11111111-1111-4111-8111-111111111111
```

이 값을 Vercel의 `DEFAULT_STORE_ID`로 사용합니다. 다른 매장을 사용할 경우
`stores.id` 값을 복사해 대신 설정합니다.

## 3. Supabase 연결 값 확인

1. 프로젝트 상단의 `Connect` 대화상자 또는 `Settings > API Keys`를 엽니다.
2. 프로젝트 URL을 확인해 `SUPABASE_URL` 값으로 사용합니다.
3. 서버용 키는 `Settings > API Keys`의 `Secret keys`에서 생성하거나
   확인합니다. 새 키가 없는 레거시 프로젝트는 `Legacy API Keys` 탭의
   `service_role` 값을 사용할 수 있습니다.
4. 서버용 키 값을 `SUPABASE_SERVICE_KEY`에 등록합니다.

Secret key와 `service_role` 키는 RLS를 우회하는 높은 권한의 서버 키입니다.
브라우저, HTML, QR, 공개 문서, Git 저장소에 넣지 마세요.

## 4. Google AI Studio 키 준비

1. Google AI Studio에서 Gemini API 키를 발급합니다.
2. 키 값은 `GEMINI_API_KEY`로 사용합니다.
3. 기본 모델은 `GEMINI_MODEL=gemini-3.6-flash`입니다.

Gemini 키가 없거나 요청이 실패하면 앱은 메뉴·좌석 조회를 계속 제공하고
AI 영역에 fallback 안내를 표시합니다.

## 5. GitHub에 업로드

1. 이 디렉터리를 Git 저장소 루트로 사용합니다.
2. `.env`, `.env.local`, `.env.production`, `.vercel`, `__pycache__`,
   `*.pyc`가 커밋되지 않는지 확인합니다.
3. 프로젝트 파일을 GitHub 저장소에 push합니다.

## 6. Vercel 프로젝트 생성

1. Vercel Dashboard에서 `Add New > Project`를 선택합니다.
2. GitHub 저장소를 Import합니다.
3. `Framework Preset`은 `Other`를 선택합니다.
4. `Root Directory`는 `api`, `public`, `vercel.json`이 함께 있는 현재
   프로젝트 루트로 지정합니다.
5. Build Command와 Output Directory는 별도로 지정하지 않습니다.
6. Install Command도 기본 자동 감지를 사용합니다.

Vercel은 `public/**`를 정적 파일로 제공하고 `api/index.py`의 FastAPI
`app`을 Python Function으로 감지합니다. 현재 구성에는 rewrite가 필요하지
않습니다.

## 7. Vercel 환경 변수 등록

Project `Settings > Environment Variables`에서 다음 값을 등록합니다.
Production과 필요한 Preview 환경에 모두 적용합니다.

```dotenv
GEMINI_API_KEY=<Google AI Studio API 키>
GEMINI_MODEL=gemini-3.6-flash
SUPABASE_URL=<Supabase 프로젝트 URL>
SUPABASE_SERVICE_KEY=<Supabase Secret key 또는 레거시 service_role>
DEFAULT_STORE_ID=11111111-1111-4111-8111-111111111111
ALLOWED_ORIGINS=
```

정적 페이지와 API가 같은 Vercel 도메인을 사용하므로 `ALLOWED_ORIGINS`는
비워 둘 수 있습니다. 별도 origin의 로컬 프런트엔드를 연결할 때만 정확한
origin을 쉼표로 구분해 설정합니다.

## 8. 배포 및 기본 확인

1. `Deploy`를 실행합니다.
2. 배포가 끝나면 Deployment URL을 엽니다.
3. 다음 주소를 차례로 확인합니다.

```text
/
/admin.html
/app.html?mode=web
/app.html?mode=store
/api/health
/api/store
/api/menus
/api/tables
/api/docs
```

`/api/health`의 `database`는 `connected`여야 합니다.
`gemini_configured`는 Gemini 키가 등록된 경우 `true`여야 합니다.
`misconfigured` 또는 `disconnected`이면 Vercel 환경 변수와 Function Logs를
확인합니다.

## 9. QR 확인

1. `/admin.html`에서 `라우팅 QR 시스템`을 엽니다.
2. 외부용 URL이 `/app.html?mode=web`으로 끝나는지 확인합니다.
3. 매장용 URL이 `/app.html?mode=store`로 끝나는지 확인합니다.
4. QR 이미지가 보이지 않아도 URL 텍스트와 `URL 복사` 버튼이 동작하는지
   확인합니다.

## 10. 관리자와 고객 연동 확인

1. 관리자에서 매장 이름을 수정하고 저장합니다.
2. 다른 브라우저의 고객 앱을 새로고침해 변경된 이름을 확인합니다.
3. 추천 키워드를 추가한 뒤 관리자 페이지를 새로고침해 유지되는지 확인합니다.
4. 메뉴를 등록하고 고객 앱에서 표시되는지 확인합니다.
5. 메뉴를 품절 처리하고 고객 앱의 품절 표시와 주문 차단을 확인합니다.
6. 좌석을 드래그하고 상태를 바꾼 뒤 `저장하기`를 누릅니다.
7. 다른 기기의 고객 앱을 새로고침해 위치와 상태를 확인합니다.
8. `store` 모드에서 주문한 뒤 관리자 주문 목록과 고객 주문 현황을
   확인합니다.
9. 관리자가 주문을 완료하고 고객 화면에 5초 이내 반영되는지 확인합니다.
10. `store` 모드에서 예약 또는 웨이팅을 요청하고 관리자가 승인합니다.
11. 고객 예약 현황과 좌석 상태에 결과가 반영되는지 확인합니다.
12. `web` 모드에서 조회와 AI는 가능하고 주문·예약은 차단되는지 확인합니다.

## 11. AI 확인

1. 고객 앱에서 `창가 자리 남아 있어?`라고 질문합니다.
2. 현재 `tables` 데이터와 맞는 답변인지 확인합니다.
3. `따뜻한 메뉴 추천해줘`라고 질문합니다.
4. 판매 중인 메뉴만 추천되고 품절 메뉴가 제외되는지 확인합니다.
5. Gemini 키를 잘못 설정한 Preview 배포에서는 fallback 안내가 표시되고
   다른 화면은 계속 동작하는지 확인합니다.

## 12. 로그와 재배포

1. Vercel Project의 `Deployments`에서 배포를 선택합니다.
2. `Functions` 또는 `Logs`에서 `api/index.py` 오류를 확인합니다.
3. Supabase 오류는 URL, 서버 키, `DEFAULT_STORE_ID`, SQL 실행 여부를
   확인합니다.
4. Gemini 오류는 API 키, 모델 접근 권한, 사용 한도를 확인합니다.
5. 코드를 수정해 GitHub에 push하면 Vercel이 새 배포를 시작합니다.
6. 환경 변수 변경 후에는 Redeploy해야 기존 배포에 반영됩니다.

## 13. 상용 전 필수 보완

현재 로그인은 데모이며 관리자 페이지와 API는 실제 인증으로 보호되지
않습니다. `mode` query parameter도 보안 토큰이 아닙니다. 공개 상용 운영 전
Supabase Auth 또는 별도 인증, 관리자 API 권한 검사, 매장 전용 접근 토큰,
요청 제한과 감사 로그를 추가해야 합니다.
