# 캐릭존 추가 채널 연결 — 2026-09-22

## 사용자 요청 및 현재 상태

- 승인된 `characzone-reel-05`부터 Threads/TikTok에 게시하고 이후 승인 영상도 대상에 포함.
- Instagram 게시 코드, 기존 예약(한국시간 09:00·16:00), 썸네일 설정, approved.json은 변경하지 않음.
- Instagram 릴스 05는 기존 manifest에 게시 완료로 기록됨. 추가 채널 실제 게시 완료를 의미하지 않음.
- Threads 대상: `gacha_m2026`. 현재 브라우저는 로그아웃. 이전 기록의 테스터 초대 수락/토큰 발급은 재확인 필요.
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

필요한 GitHub Secrets: `THREADS_ACCESS_TOKEN`(Threads 전용), `THREADS_USER_ID`.
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

실제 추가 채널 게시/토큰 연결은 아직 검증 전. 코드 테스트 성공과 운영 연결 성공을 구분해서 보고할 것.

## 이번 검증 결과

- 로컬 모의 API 테스트 16건 통과. 중복 게시, 응답 유실, 상태 저장 실패, 계정 불일치, 권한 누락, 승인 취소 등을 검증.
- 기존 Instagram 코드·workflow·approved.json의 git diff 없음.
- `social-publish-state` 브랜치 생성 완료.
- 실제 Threads API 호출/게시 및 TikTok 게시 검증은 계정 연결 전으로 미실행.
