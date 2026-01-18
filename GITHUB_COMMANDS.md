# 윈도우 터미널(PowerShell)용 GitHub 명령어 모음

## 1. 기본 명령어 (가장 자주 씀!)
이 세 단계만 기억하세요: **저장 -> 확정 -> 업로드**

### 1단계: 변경사항 확인 & 담기 (Stage)
작업한 파일들을 "택배 상자"에 담는 과정입니다.
```powershell
# 현재 상태 확인 (어떤 파일이 바뀌었는지)
git status

# 모든 변경사항을 상자에 담기
git add .
```

### 2단계: 설명 쓰고 포장하기 (Commit)
상자에 라벨(설명)을 붙이고 테이프로 포장하는 과정입니다.
```powershell
# "설명" 부분에 작업 내용을 적으세요
git commit -m "작업한 내용 요약"
```

### 3단계: GitHub에 보내기 (Push)
포장된 상자를 GitHub 창고(클라우드)로 보내는 과정입니다.
```powershell
git push origin main
```

---

## 2. 가끔 쓰는 명령어

### 최신 내용 가져오기 (Pull)
남들이 올린 코드나, 다른 컴퓨터에서 작업한 내용을 내 컴퓨터로 가져옵니다.
```powershell
git pull origin main
```

### 작업 히스토리 보기 (Log)
누가 언제 무엇을 수정했는지 봅니다.
```powershell
git log --oneline
```
(나갈 때는 키보드 `q`를 누르세요)

---

## 3. 팁 (PowerShell)
- **화면 지우기**: `cls` 또는 `clear`
- **파일 목록 보기**: `ls` 또는 `dir`
- **폴더 이동**: `cd 폴더이름` (탭 키를 누르면 자동완성 됨!)
