# T15 네이버 키 없이 수집 — 실측 (2026. 9. 29., Main Claude, 이 Mac)

D-094 근거. 키워드 "에어컨 소음", 브라우저형 User-Agent, 요청 간 1초.

## 목록 (P1)
- 블로그: `GET https://search.naver.com/search.naver?ssc=tab.blog.all&query=<kw>` → 200, 페이지당 고유 글 주소 30개(`https://blog.naver.com/<blogId>/<logNo>`).
  `&start=31` → 200, 겹치지 않는 새 주소 30개. 즉 `start = 1 + 30·(page-1)`.
- 카페: `GET https://search.naver.com/search.naver?ssc=tab.cafe.all&query=<kw>` → 200, 페이지당 고유 글 주소 30개(`https://cafe.naver.com/<cafeUrl>/<articleId>`).
- 요약문 · 날짜 · 제목은 같은 결과 화면에 있다(구체 선택자는 녹화본에서 확인).

## 블로그 본문 (P3)
- `https://m.blog.naver.com/<blogId>/<logNo>` → 200, `se-main-container`(스마트에디터 본문) 포함. 추가 렌더링 불필요.

## 카페 본문 (P3)
- `m.cafe.naver.com` 글 페이지는 JS 앱이다. httpx로 받으면 "로딩중" 껍데기(약 9.6KB)만 온다. 기존 캡처 스크립트의 `--render`도 요청 직렬화 때문에 본문을 못 그렸다.
- 앱이 부르는 JSON: `GET https://article.cafe.naver.com/gw/v4/cafes/<cafeUrl>/articles/<articleId>?useCafeId=false`
  (Referer `https://m.cafe.naver.com/`). 로그인 · 브라우저 없이 httpx로 받아진다.
  - 공개 글 → 200, `result.article.contentHtml`(본문 HTML), `result.comments.items[]`(10개 단위).
    댓글 필드: `id, refId, isRef, content, writer{…}, updateDate, isDeleted, memberLevel…`.
    최상위 댓글은 `refId == id`, 답글은 `isRef == true` · `refId` = 부모 id → depth 0/1.
  - 회원 전용 글 → 401, `errorCode "0004"`, `reason "로그인하지 않았습니다."` → `access="restricted"`, 검색 요약문 문서.
- 공개 비율(첫 결과 15건 표본): 공개 4 · 로그인 필요 11 (약 27% 공개).
- 작성자 식별 정보 위치: `writer`(닉네임 · 회원키 · 프로필 이미지), 본문 HTML 속 멘션 · 프로필 링크. 녹화 시 가려야 한다.
