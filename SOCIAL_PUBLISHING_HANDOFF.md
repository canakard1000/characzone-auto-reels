# 캐릭존 추가 채널 연결 — 2026-09-23

## 사용자 요청 및 현재 상태

- 승인된 `characzone-reel-05`부터 Threads/TikTok에 게시하고 이후 승인 영상도 대상에 포함.
- Instagram 게시 코드, 기존 예약(한국시간 09:00·16:00), 썸네일 설정, approved.json은 변경하지 않음.
- Instagram 릴스 05는 기존 manifest에 게시 완료로 기록됨. 추가 채널 실제 게시 완료를 의미하지 않음.
- Threads 대상: `gacha_m2026`. 테스터 초대 수락, Threads 기본/게시 권한 승인, 장기 토큰 발급 및 GitHub Secrets 저장 완료. 실제 게시 검증 완료.
- TikTok 대상: `jinwoo.jang5`. TikTok Lite `user7504613622941`는 별도 계정이며 작업 대상이 아님.
- TikTok 앱 ID: `7688204010964256786`. 이전 기록의 Sandbox 계정 연결은 미완료. 이번 점검에서 기존 개발자 탭 응답 시간 초과 후 탭이 닫혀 현재 연결 상태는 검증하지 못함.

## Threads 구현

`publish_threads.py`, 별도 workflow, 테스트를 추가. `published` 필드는 Instagram 전용으로 취급하므로 릴스 05도 Threads 대상에 포함됨.

- Instagram workflow가 끝날 때 별도 Threads workflow 실행. 새 workflow 실패가 Instagram 실행에 영향 없음.
- `THREADS_ENABLED=true`일 때만 자동 게시. 연결 전에는 실행 요약에 미연결 상태 표시.
- 수동 실행 기본값은 읽기 전용 사전검증. 게시하려면 활성화 설정과 `publish=true` 모두 필요.
- `social-publish-state` 브랜치의 `threads-state.json`에 업로드/게시 전후 상태 즉시 저장. main/approved.json에는 쓰지 않아 Instagram 상태 저장과 충돌하지 않음.
- 컨테이너 처리 지연은 기존 컨테이너로 재개. 요청 응답 유실 시 자동 재전송하지 않음. PUBLISHED 상태만 확인되면 완료로 복구.
- 계정 ID와 `gacha_m2026` 사용자명, 기본/게시 권한 검사. 문자열 `"true"` 승인은 인정하지 않음.
- 한 실행에 승인 영상 하나. 게시 이력이 있으면 건너뜀. 승인된 영상이 없으면 새 영상을 만들거나 같은 영상을 반복 게시하지 않음.
- 미승인, 중복 ID, 변경된 컨텐츠, 500자 초과 본문, 외부 영상 URL은 차단.

필수 GitHub Secret: `THREADS_ACCESS_TOKEN`(저장 완료). `THREADS_USER_ID`는 선택적 추가 고정값이며, 미설정 시 API가 반환한 사용자명이 `gacha_m2026`일 때만 ID를 채택.
기존 `META_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`는 사용/교체하지 않음.

연결 순서:
1. Threads `gacha_m2026` 로그인 및 기존 앱 테스터 초대 수락 여부 확인.
2. 기존 Meta 앱에서 Threads 기본/게시 권한 승인, 장기 토큰 발급 후 GitHub Secrets에 안전하게 저장. 채팅/저장소에 토큰을 쓰지 않음.
3. `social-publish-state` 브랜치 존재 확인.
4. 새 workflow 수동 실행 `publish=false`로 계정과 권한 검증.
5. `THREADS_ENABLED=true` 설정 후 `publish=true` 수동 실행으로 릴스 05 게시.
6. 실제 Threads 게시 링크 확인 후 예약 연동 활성 상태 확인.
7. 장기 토큰 만료/갱신 운영은 연결 시 별도 설정 필요. 현재 코드에 자동 토큰 갱신은 없음. 만료되면 오류로 정지하며 성공 처리하지 않음.

불확실한 상태 복구: 공개 프로필과 API 컨테이너 상태를 대조한 뒤 state 브랜치만 수정. `creating`, `publishing`, `failed`를 무조건 지우면 중복 게시 위험. 미디어 ID 유실 상태는 `PUBLISHED`로 확인해도 링크 확보가 별도 필요.

## TikTok: 공개 자동 게시 차단 사유

공식 Direct Post 지침은 미심사 클라이언트를 비공개 게시로 제한하며 본인/팀 계정용 내부 업로드 도구를 허용 대상에서 제외함. 단순히 자체 앱에 video.publish를 추가해도 공개 예약 게시가 보장되지 않음.

공식 Upload API는 초안을 받은 사용자가 TikTok 알림에서 편집/게시를 완료하는 방식이며 완전 자동 공개 게시가 아님. 이를 사용자 동의 없이 대체 방식으로 활성화하지 않았음.

따라서 이번 변경에는 동작하지 않는 TikTok 직접 게시 코드나 가짜 완료 상태를 넣지 않음. 공개 자동 게시를 위해 심사된 게시 서비스 연결을 검토해야 하며 비용/계정 권한/원하는 예약 기능을 실제로 확인한 뒤 선택해야 함. 유료 가입이나 새 서비스 권한 부여는 하지 않음.

## 참고 링크

- 저장소: https://github.com/canakard1000/characzone-auto-reels
- TikTok 지침: https://developers.tiktok.com/docs/en/content-sharing-guidelines
- TikTok Upload API: https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content
- Meta 공식 Threads API 예제: https://github.com/fbsamples/threads_api/blob/main/postman/threads-api.postman_collection.json
- Threads: https://www.threads.com/

Threads 실제 게시와 연결은 검증 완료. TikTok은 아직 게시하지 않았음.

## 이번 검증 결과

- 로컬 모의 API 테스트 16건 통과. 중복 게시, 응답 유실, 상태 저장 실패, 계정 불일치, 권한 누락, 승인 취소 등을 검증.
- 기존 Instagram 코드·workflow·approved.json의 git diff 없음.
- `social-publish-state` 브랜치 생성 완료.
- Threads 실제 API 사전검증 및 릴스 05 게시 성공. TikTok 게시 미실행.


## 2026-09-23 연결 및 게시 완료 기록

- Threads 앱 ID `1645622460325496`, Meta 부모 앱 ID `2864881330557790`.
- 승인 범위: threads_basic + threads_content_publish. 답글 관리/읽기 및 통계 권한 제외.
- `THREADS_ACCESS_TOKEN` 저장 완료, `THREADS_ENABLED=true` 활성화 완료.
- 실제 사전검증: https://github.com/canakard1000/characzone-auto-reels/actions/runs/35871745577 (3번째 시도 성공).
- 실패 원인/수정: `/me/permissions`는 Threads에 없는 필드. HTTP 500/code100 반환. 공식 `/me/threads_publishing_limit` 조회로 게시 권한과 한도 검증하도록 수정. 사용자 계정 조회는 정상.
- 실제 게시 실행: https://github.com/canakard1000/characzone-auto-reels/actions/runs/35872299835 성공.
- 릴스 05 게시 링크: https://www.threads.com/@gacha_m2026/post/DdofpoHDQ48
- Threads media ID `17988355277867159`, container `18116635165840344`.
- 게시 시각: 2026-09-23T14:11:56Z (한국시간 23:11:56).
- 별도 state 브랜치에 phase=published 저장 완료. 브라우저에서 해당 계정·본문·영상 재생 화면 확인.
- 로컬 Threads 테스트 19건, GitHub 전체 테스트 23건 통과.
- 동시 추가된 9/24 오전·오후 릴스 확인. `scheduled_for` 이전 게시 및 rejected=true 게시를 차단하도록 보완. 기존 Instagram 코드/manifest/workflow 수정 없음.
- 기존 Instagram workflow 완료 후 Threads workflow가 독립 실행. 승인+예약 도달 영상 한 개/실행. 이미 게시한 05는 재게시하지 않음.
- 장기 토큰 자동 갱신은 아직 미구현. 다음 운영 작업에서 만료일 확인/갱신 관리 필요. 토큰/앱 시크릿은 파일이나 로그에 남기지 말 것.

## TikTok 다음 연결 후보 (아직 가입·연결·게시 안 함)

자체 앱 Direct Post 제한 때문에 Buffer 무료 플랜을 조사하고 가입 직전 화면까지 준비.
- 공식 무료 플랜: 최대 3채널, 채널당 동시 대기 10개(소진 후 재충전), API key 1개, 월 API 3,000회. 월 게시 10개 제한이 아님.
- TikTok 자동 게시/API 생성 지원. 하루 2개를 한 개씩 전달하는 방식은 문서상 무료 한도 내 구성 가능. 실제 계정 연결 후 검증 필요.
- 가격: https://buffer.com/pricing
- API 한도: https://developers.buffer.com/guides/api-limits.html
- 영상 게시 예제: https://developers.buffer.com/examples/create-video-post.html
- TikTok 지원: https://support.buffer.com/en-us/articles/using-tiktok-with-buffer-oGEroY9Of2
- 브라우저에 Free 플랜 가입 화면 준비. 이메일/새 비밀번호 입력 전. 유료 결제나 체험판 신청 없음.
- 새 서비스 가입 및 TikTok 권한은 아직 승인/연결 전. 대상은 jinwoo.jang5. Instagram 연결을 Buffer로 이전하지 말 것.
- 승인 후: Buffer 무료 가입/로그인 → TikTok jinwoo.jang5 연결 → 최소 API 키 발급/Secrets 저장 → 별도 TikTok ledger/워크플로 구현 → 사전검증 → 05 실게시 → 게시 링크 및 재실행 중복 방지 확인.
- 신규 비밀번호 생성은 브라우저 정책상 사용자 직접 입력 필요. 보안값을 채팅으로 요청하지 말 것.
