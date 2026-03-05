# Palo Alto 방화벽 웹 관리 도구

FastAPI와 공식 `pan-os-python` SDK를 기반으로 한 Palo Alto Networks 방화벽 웹 관리 인터페이스입니다.

장비에 직접 CLI나 GUI로 접속하지 않고도 방화벽 객체를 손쉽게 관리할 수 있도록 설계되었습니다.

---

## 주요 기능

- **방화벽 연결** — API 키 및 사용자 계정/비밀번호 인증 모두 지원
- **Address Object 관리** — 주소 객체 조회, 단건 추가, CSV 일괄 등록
- **Address Group 관리** — Static/Dynamic 그룹 및 멤버 조회
- **CSV 일괄 등록** — CSV 파일로 최대 500개 주소 객체 일괄 등록 (UTF-8, EUC-KR/cp949 인코딩 지원)
- **커밋 + 자동 백업** — 커밋 전 실행 중인 설정을 XML 파일로 자동 저장
- **부분 커밋(Partial Commit)** — 현재 인증된 관리자의 변경 사항만 선택 커밋
- **논블로킹 API** — 모든 SDK 호출을 스레드 풀로 처리하여 비동기 이벤트 루프 블로킹 방지

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| 백엔드 | Python 3, FastAPI, Uvicorn |
| 방화벽 SDK | pan-os-python (panos) |
| 프론트엔드 | Vanilla HTML / CSS / JavaScript |
| 환경 설정 | python-dotenv (.env) |

---

## 프로젝트 구조

```
.
├── app.py              # FastAPI 백엔드 — 모든 API 엔드포인트
├── paloalto_xml.py     # 레거시 CLI 스크립트 (참고용)
├── static/
│   ├── index.html
│   ├── script.js
│   └── style.css
├── template_env.txt    # .env 템플릿
├── requirements.txt
└── backups/            # 커밋 시 자동 생성되는 XML 백업 폴더
```

---

## 시작하기

### 사전 요구사항

- Python 3.10 이상
- Palo Alto Networks 방화벽 접근 권한 (PAN-OS 9.x 이상)

### 설치

```bash
git clone https://github.com/90yard/gst-securitys.git
cd gst-securitys
pip install -r requirements.txt
```

### 환경 설정

템플릿을 복사한 후 방화벽 접속 정보를 입력하세요:

```bash
cp template_env.txt .env
```

`.env` 형식:

```
PAN_HOST=<방화벽 IP>
PAN_USER=<사용자명>
PAN_KEY=<API 키>
```

### 실행

```bash
uvicorn app:app --reload
```

브라우저에서 `http://localhost:8000` 접속

---

## API 엔드포인트

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `POST` | `/api/connect` | 방화벽 연결 테스트 |
| `POST` | `/api/address/list` | 주소 객체 전체 조회 |
| `POST` | `/api/address/add` | 주소 객체 단건 추가 |
| `POST` | `/api/address/bulk` | CSV 파일로 주소 객체 일괄 등록 |
| `POST` | `/api/group/list` | 주소 그룹 전체 조회 |
| `POST` | `/api/commit` | 변경 사항 커밋 (자동 백업 포함) |

모든 엔드포인트는 `host`, `api_key` (또는 `username` + `password`) 필드를 포함한 JSON을 받습니다.

### CSV 형식 (일괄 등록 시)

```
name,value,type,description
block-list-1,192.168.1.0/24,ip-netmask,내부 서브넷
bad-host,10.0.0.5,ip-netmask,악성 호스트
```

- `type` 생략 시 `ip-netmask`로 자동 설정
- `description` 선택 입력
- 이미 존재하는 이름은 자동으로 건너뜀

---

## 아키텍처 메모

- SDK 호출은 `ThreadPoolExecutor` + `run_in_executor`로 래핑하여 FastAPI 비동기 이벤트 루프 블로킹 방지
- 커밋 시 `backups/` 폴더에 타임스탬프가 포함된 XML 백업 자동 저장
- `.env`는 별도 외부 라이브러리 없이 자체 구현한 `load_env_file()`로 로드

---

## 라이선스

MIT
