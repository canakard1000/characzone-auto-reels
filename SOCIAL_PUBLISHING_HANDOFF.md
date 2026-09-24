# 캐릭존 Instagram·Threads·TikTok 게시 운영

2026-09-23 UTC / 2026-09-24 한국시간 업데이트.

## 대상과 승인 조건

- 사용자 승인: 기존 승인 릴스 `characzone-reel-05`부터 추가 채널 게시, 이후 승인 영상 자동 게시.
- Instagram: 기존 코드, workflow, 시간 및 썸네일 설정 유지. 이 연결 작업에서 `publish_reel.py`, `.github/workflows/publish-approved-reel.yml`, `approved.json` 수정 없음.
- Threads: `gacha_m2026`.
- TikTok: `jinwoo.jang5`, Buffer 무료 계정 연결. TikTok Lite `user7504613622941`는 다른 계정이며 대상 아님.
- 추가 채널은 `approved`가 boolean true, `rejected`가 true가 아니며 `scheduled_for`가 도달한 영상만 게시. Instagram의 `published` 필드는 추가 채널 게시 완료를 뜻하지 않음.
- 9/24 오전·오후 승인 영상은 예약 도달 후 대상. 9/25 영상은 현재 미승인으로 제외.

## 독립 실행 구조

| 채널 | 실행 파일 | workflow | 활성화 변수 | 별도 상태 브랜치/파일 |
|---|---|---|---|---|
| Threads | publish_threads.py | publish-approved-threads.yml | THREADS_ENABLED=true | social-publish-state / threads-state.json |
| TikTok | publish_tiktok.py | publish-approved-tiktok.yml | TIKTOK_ENABLED=true | tiktok-publish-state / tiktok-state.json |

- 기존 `Publish approved Instagram reel` workflow의 main 실행 완료 시 각각 독립 실행. 추가 채널 실패는 Instagram 게시에 영향 없음.
- 수동 실행 기본은 `publish=false` 읽기 전용 검증. 실제 게시에는 활성화 변수와 `publish=true`가 모두 필요.
- 한 실행에 승인·예약 도달 영상 하나. 이미 게시한 영상은 건너뜀. 승인 영상이 없으면 반복 게시하지 않음.
- 별도 branch에 외부 요청 전후 상태를 즉시 push. 저장 실패 시 게시 중지. main/approved.json에는 게시 상태를 쓰지 않음.
- 동일 채널 작업은 GitHub concurrency로 직렬 실행. 채널 간 상태 branch를 분리해 충돌 방지.
- GitHub 예약 실행은 지연될 수 있음. Buffer 기본 추천 슬롯이나 주간 목표 14개는 실제 예약의 기준이 아님. TikTok은 manifest 예약 도달 후 `shareNow` + `automatic`으로 전달.

## Threads 검증 완료

- Meta 부모 앱 `2864881330557790`, Threads 앱 `1645622460325496`.
- `threads_basic` + `threads_content_publish`만 승인. 답글/통계 권한 제외.
- GitHub Secret `THREADS_ACCESS_TOKEN` 저장. 기존 Instagram 토큰을 교체하지 않음.
- `THREADS_USER_ID`는 선택적 고정값이며 미설정 시 API 사용자명이 gacha_m2026일 때만 ID 채택.
- `/me/permissions`는 Threads에 없어서 실패했음. 공식 `/me/threads_publishing_limit`으로 권한/한도 확인하도록 수정 완료.
- 사전검증: https://github.com/canakard1000/characzone-auto-reels/actions/runs/35871745577 (3번째 시도 성공).
- 릴스05 실게시: https://github.com/canakard1000/characzone-auto-reels/actions/runs/35872299835 성공.
- 실제 게시: https://www.threads.com/@gacha_m2026/post/DdofpoHDQ48
- media `17988355277867159`, container `18116635165840344`, 2026-09-23T14:11:56Z.
- API published 상태 저장 및 브라우저 본문·영상 확인 완료.
- 장기 토큰 자동 갱신은 미구현. 만료 전 갱신 운영 필요. 만료 시 오류로 정지하며 성공 처리하지 않음.

## TikTok Buffer 연결 및 검증

- 자체 TikTok Direct Post 앱은 미심사/내부용 제한 때문에 사용하지 않음. 사용자 승인 후 Buffer 무료 가입, 이메일 인증, TikTok 연결 완료.
- Buffer channel ID `6ab41d16ea19ca0bdec9454b`, API 검증 사용자명 `jinwoo.jang5`, Seoul 시간대, automatic 게시 지원 확인.
- 새 key `characzone-tiktok-github-actions`, 만료 2027-09-24. 최소 범위 `account:read`, `posts:read`, `posts:write`만 승인.
- GitHub Secret `BUFFER_API_KEY` 저장 완료. 키 원문은 저장소/로그/채팅에 기록하지 않음.
- Buffer UI 무료 플랜 1/3채널. 유료 플랜/체험판 신청 없음. 가입 후 UI API 한도는 100/15분, 500/24시간, 10,000/30일 표시. 이전 공개 문서 수치와 다를 수 있으므로 현재 계정 UI를 기준으로 확인.
- 구현 커밋: `7fec8bba2647c3fa4feff60f3c926d76c696ee53`.
- 실계정 읽기 전용 사전검증: https://github.com/canakard1000/characzone-auto-reels/actions/runs/35906540024 성공.
- 로컬 테스트33개, GitHub 전체 테스트37개 통과. 저장 실패/응답 유실/중복/계정 불일치/예약 전/승인 취소/알림 게시 상태 검사.
- 실제 게시 실행: https://github.com/canakard1000/characzone-auto-reels/actions/runs/35906805733
- Buffer post ID `6ab422bd746aac800cfb1d11`. 실제 완료 링크와 최종 상태는 아래 기록 및 state branch 확인.

## 실패 및 복구 규칙

- Threads: 컨테이너 처리 중이면 같은 컨테이너 재조회. publish 응답 유실 시 PUBLISHED 확인으로만 복구. 무조건 재전송하지 않음.
- TikTok: `creating`을 먼저 영구 저장 후 createPost. post ID를 받으면 `submitted` 저장, 같은 ID만 조회. `sent`일 때만 `published` 저장. notification/draft/error를 완료로 처리하지 않음.
- `creating`, `failed`, `needs_review`는 수동 대조 필요. 상태를 무조건 지우거나 새 업로드를 만들면 중복 위험.
- API 접수 후 처리 지연 시 다음 실행은 같은 post ID를 확인. 이미 제출된 게시물은 이후 manifest 승인 취소만으로 자동 취소되지 않으므로 필요 시 Buffer에서 직접 취소.
- 승인/본문/영상 URL이 업로드 시작 뒤 변경되면 중지. TikTok 본문 2200자, 해시태그5개 제한. 본문을 임의로 자르지 않음.
- AI 공개 표시가 필요한 새 영상은 `tiktok_is_ai_generated: true`를 boolean으로 manifest에 명시할 수 있음.
- TikTok 중복 확인은 최대500개 게시물을 조회 후 확인을 마치지 못하면 안전하게 중지. 장기 운영 시 보관 이력 크기에 맞춰 조회 범위 개선 필요.
- 기존 Telegram 승인 동기화/영상 생성 workflow에 실패 이력이 보였으나 이번 추가 채널 연결 범위에서 수정하지 않음. approved.json에 실제 반영된 승인만 추가 채널 대상으로 삼음.

## 공식 참고

- Buffer GraphQL: https://developers.buffer.com/reference.html
- 영상 게시: https://developers.buffer.com/examples/create-video-post.html
- TikTok 지원: https://support.buffer.com/en-us/articles/using-tiktok-with-buffer-oGEroY9Of2
- Threads 예제: https://github.com/fbsamples/threads_api/blob/main/postman/threads-api.postman_collection.json
- TikTok 자체 앱 지침: https://developers.tiktok.com/doc/content-sharing-guidelines/

## TikTok 릴스05 실제 게시 완료

- Buffer API status=sent, schedulingType=automatic 확인. 별도 ledger phase=published 저장 완료.
- 실제 링크: https://tiktok.com/@jinwoo.jang5/video/7688808693558791425
- 게시 시각: 2026-09-23T19:06:12.581Z (한국시간 9/24 04:06:12).
- 9/20 기존 TikTok 게시물 `7687336671154621717`와 다른 신규 게시물임.
- 이후 승인+예약 도달 영상은 기존 Instagram 작업 종료 후 각각 Threads/TikTok 자동 게시. 05는 재게시하지 않음.


## 2026-09-24 Threads 토큰 갱신 진행 기록

- 사용자 승인 후 갱신용 `refresh_threads_token.py`, 수동 workflow, 비밀값 노출 방지 테스트5개 추가.
- 최초 Bearer 방식 HTTP500/code100 → 공식 Meta Postman 컬렉션의 OAuth `addTokenTo=queryParams` 방식으로 수정.
- 갱신 API가 기존과 다른 token을 반환함. 같은 token의 만료기간만 연장된다고 가정해서는 안 됨.
- 실행 36004379275에서 새 토큰 발급과 gacha_m2026 계정/게시 권한 검증 성공. expires_in=5100259, 만료 예상 2026-11-22T13:59:41Z (KST 22:59).
- 새 토큰은 RSA-OAEP + AES-GCM 암호화로만 runner 밖으로 전달. 임시 개인키/전달파일 삭제 완료.
- GitHub 이메일 본인 확인을 사용자 완료한 뒤 THREADS_ACCESS_TOKEN 교체 저장 완료. Secret updated 알림과 갱신일 확인.
- Secret 수정 폼 종료 및 목록 화면 복귀 확인. 앞으로도 민감한 입력 폼은 전체 DOM/스크린샷으로 출력하지 말 것.
- 갱신 workflow는 Secret 반영 전에는 의도적으로 failure로 끝나며 성공으로 기록하지 않음. 자동 갱신 일정은 추가하지 않았음.
- 다음 갱신은 새 일회용 공개키를 workflow 입력으로 전달해야 함. 기존 일회용 개인키는 삭제되었으므로 과거 실행을 그대로 재실행하지 말 것.


## 갱신 최종 검증 완료 — 2026-09-24

- 저장된 새 THREADS_ACCESS_TOKEN으로 읽기 전용 실계정 preflight 성공: https://github.com/canakard1000/characzone-auto-reels/actions/runs/36007146124
- @gacha_m2026 계정과 게시 권한 확인. 전체 테스트42개 통과. 추가 게시물/컨테이너 생성 없음.
- API 반환 유효기간으로 계산한 만료 예상: 2026-11-22 22:59 KST. 별도 자동 갱신 일정은 없음. 만료 전 다시 갱신·Secrets 교체 필요.
- 앞선 갱신 workflow failure는 새 토큰을 Secrets에 반영하기 전 의도적으로 정지한 기록이며, 위 실제 검증으로 교체 완료 확인.
- Instagram/TikTok 설정과 승인/게시 상태는 갱신 작업에서 변경하지 않음.
