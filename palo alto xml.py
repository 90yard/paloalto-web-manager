#!/usr/bin/env python3
"""
paloalto_firewall_manager.py
=========================================================
Palo Alto Networks Firewall 자동화 관리 스크립트

이 스크립트는 pan-os-python SDK(XML API 기반)를 사용하여
다음 작업을 CLI 형태로 수행한다.

1. Address Object 생성
2. Address Group 생성 (텍스트 파일 지원)
3. Security Policy 생성 / 수정
4. GlobalProtect 사용자 조회
5. GlobalProtect 사용자 강제 로그아웃
6. 설정 Commit (자동 백업 포함)

[Safety Features]
- --dry-run: 실제 변경 없이 시뮬레이션 수행
- Auto Backup: Commit 전 running-config 자동 백업
=========================================================
"""

# -------------------------------------------------------
# [1] 표준 라이브러리 import
# -------------------------------------------------------

import argparse      # CLI 인자 파싱
import sys           # 오류 발생 시 명확한 종료 코드 반환
import os            # 파일 경로 확인
import getpass       # 보안 비밀번호 입력
import datetime      # 백업 파일명 생성
from typing import List


# -------------------------------------------------------
# [2] PAN-OS SDK import (XML API 래핑)
# -------------------------------------------------------

from panos.firewall import Firewall
from panos.objects import AddressObject, AddressGroup
from panos.policies import SecurityRule
from panos.errors import PanDeviceError


# -------------------------------------------------------
# [3] 방화벽 연결 함수
# -------------------------------------------------------

def connect_firewall(host, username=None, password=None, api_key=None):
    """
    Palo Alto 방화벽에 연결하는 함수
    """

    # API Key 방식
    if api_key:
        fw = Firewall(hostname=host, api_key=api_key)

    # 계정/비밀번호 방식
    elif username:
        if not password:
            # 터미널에서 보안 입력 받기
            password = getpass.getpass(f"Password for {username}@{host}: ")
        fw = Firewall(hostname=host, username=username, password=password)

    else:
        raise ValueError("Authentication (API Key or Username) is required. (Tip: Use double quotes for passwords with special characters like $)")

    return fw


# -------------------------------------------------------
# [4] API Key 발급 함수
# -------------------------------------------------------

def fetch_api_key(host, username, password=None):
    """
    ID/PW를 사용하여 방화벽에서 API Key를 직접 요청
    """
    if not password:
        password = getpass.getpass(f"Enter password for {username} to fetch API Key: ")
    
    # 임시 연결 객체 생성
    try:
        fw = Firewall(hostname=host, username=username, password=password)
        api_key = fw.refresh_key()
        print("\n" + "="*50)
        print(f"[*] Successfully retrieved API Key for {username}@{host}")
        print(f"[*] API KEY: {api_key}")
        print("="*50)
        print("[TIP] This key can be used with the --api-key argument instead of ID/PW.\n")
        return api_key
    except Exception as e:
        print(f"[ERROR] Failed to retrieve API Key: {e}")
        return None


# -------------------------------------------------------
# [5] 연결 테스트 함수
# -------------------------------------------------------

def test_connection(fw):
    """
    show system info 명령을 실행하여 API 통신 상태 확인
    """
    print(f"[INFO] Testing connection to {fw.hostname} ...")
    try:
        # show system info 실행
        system_info = fw.op("show system info", cmd_xml=True)
        
        # XML 결과에서 주요 정보 추출 (ElementTree 활용)
        import xml.etree.ElementTree as ET
        # op 결과가 ET 객체이므로 직접 탐색
        # <system><hostname>...</hostname><model>...</model>...</system>
        system_node = system_info.find('result/system')
        if system_node is not None:
            hostname = system_node.find('hostname').text
            model = system_node.find('model').text
            sw_ver = system_node.find('sw-version').text
            uptime = system_node.find('uptime').text
            
            print("\n" + "✓"*50)
            print(f"[SUCCESS] Connection verified!")
            print(f"[*] Hostname: {hostname}")
            print(f"[*] Model: {model}")
            print(f"[*] Software Version: {sw_ver}")
            print(f"[*] Uptime: {uptime}")
            print("✓"*50 + "\n")
        else:
            print("[OK] Connection successful, but system info structure unexpected.")
            
        return True
    except Exception as e:
        print(f"[ERROR] Connection test failed: {e}")
        return False


# -------------------------------------------------------
# [6] 설정 백업 함수 (안전장치)
# -------------------------------------------------------

def backup_config(fw):
    """
    Running Config를 로컬 파일로 백업
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{fw.hostname}_{timestamp}.xml"
    
    print(f"[INFO] Backing up running-config to {filename} ...")
    
    try:
        # running config 조회
        config_xml = fw.op("show config running", cmd_xml=True)
        
        # XML 내용을 문자열로 변환하여 저장
        with open(filename, "w", encoding="utf-8") as f:
            # pan-os-python의 op 리턴값은 ElementTree 객체일 수 있음
            # 문자열로 변환 (Python 3.8+ ET.tostring은 bytes 리턴하므로 decode)
            import xml.etree.ElementTree as ET
            xml_str = ET.tostring(config_xml, encoding='utf8', method='xml').decode('utf8')
            f.write(xml_str)
            
        print(f"[OK] Backup saved: {filename}")
        return True
        
    except Exception as e:
        print(f"[WARNING] Backup failed: {e}")
        # 백업 실패 시 작업을 중단할지 여부는 정책에 따름 (여기선 경고만)
        return False


# -------------------------------------------------------
# [7] Address Object 생성
# -------------------------------------------------------

def add_address_object(fw, name, value, description=None, dry_run=False):
    """
    Address Object 생성
    """
    if dry_run:
        print(f"[DRY-RUN] Would create Address Object: {name} = {value}")
        return

    addr = AddressObject(
        name=name,
        value=value,
        description=description
    )
    fw.add(addr)
    addr.create()
    print(f"[OK] Address Object created: {name} = {value}")


# -------------------------------------------------------
# [8] Address Group 생성
# -------------------------------------------------------

def add_address_group(fw, name, members_input, dry_run=False):
    """
    Static Address Group 생성
    members_input: 쉼표구분 문자열 또는 .txt 파일 경로
    """
    
    members = []
    # 파일 경로인지 확인
    if os.path.isfile(members_input) and members_input.endswith('.txt'):
        with open(members_input, 'r', encoding='utf-8') as f:
            # 각 줄을 읽고 공백 제거, 빈 줄 제외
            members = [line.strip() for line in f if line.strip()]
        print(f"[INFO] Loaded {len(members)} members from file: {members_input}")
    else:
        # 기존 방식: 쉼표 구분
        members = [m.strip() for m in members_input.split(',')]

    if dry_run:
        print(f"[DRY-RUN] Would create Address Group: {name}")
        print(f"          Members ({len(members)}): {members[:5]} ...")
        return

    group = AddressGroup(
        name=name,
        static_value=members
    )

    fw.add(group)
    group.create()

    print(f"[OK] Address Group created: {name} (Total: {len(members)})")


# -------------------------------------------------------
# [9] Security Policy 생성 / 수정
# -------------------------------------------------------

def create_or_update_rule(
    fw,
    name,
    from_zone,
    to_zone,
    source,
    destination,
    application,
    service,
    action,
    dry_run=False
):
    """
    Security Policy 생성 또는 수정
    """
    if dry_run:
        print(f"[DRY-RUN] Would create/update Security Rule: {name}")
        print(f"          From: {from_zone} -> To: {to_zone}")
        print(f"          Src: {source} -> Dst: {destination}")
        print(f"          App: {application}, Svc: {service}, Action: {action}")
        return

    rule = SecurityRule(
        name=name,
        fromzone=[from_zone],
        tozone=[to_zone],
        source=[source],
        destination=[destination],
        application=[application],
        service=[service],
        action=action
    )

    fw.add(rule)
    rule.create()
    print(f"[OK] Security Rule applied: {name}")


# -------------------------------------------------------
# [10] GlobalProtect 사용자 조회 / 로그아웃
# -------------------------------------------------------

def show_globalprotect_users(fw):
    """
    현재 접속 중인 GlobalProtect 사용자 조회
    """
    cmd = "show global-protect-gateway current-user"
    result = fw.op(cmd)
    print("[INFO] GlobalProtect Users:")
    print(result)

def logout_globalprotect_user(fw, username, dry_run=False):
    """
    특정 GlobalProtect 사용자 강제 로그아웃
    """
    if dry_run:
        print(f"[DRY-RUN] Would logout GP user: {username}")
        return

    cmd = f"""
    <request>
      <global-protect-gateway>
        <client-logout>
          <user>{username}</user>
        </client-logout>
      </global-protect-gateway>
    </request>
    """
    fw.op(cmd, cmd_xml=True)
    print(f"[OK] GlobalProtect user logged out: {username}")


# -------------------------------------------------------
# [11] Commit 수행 (백업 포함)
# -------------------------------------------------------

def commit_config(fw, dry_run=False):
    """
    Candidate config → Running config 반영
    """
    if dry_run:
        print("[DRY-RUN] Would commit configuration (Simulated)")
        return

    # 1. 안전장치: 백업 수행
    backup_config(fw)

    # 2. Commit 수행
    print("[INFO] Commit started... (This may take a while)")
    try:
        fw.commit(sync=True)
        print("[OK] Commit completed successfully")
    except Exception as e:
        print(f"[ERROR] Commit failed: {e}")
        print("Tip: Check the backup file if rollback is needed.")


# -------------------------------------------------------
# [12] CLI 엔트리 포인트
# -------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Palo Alto Firewall Management Tool (Safe Mode)"
    )

    # 기본 연결 인자
    parser.add_argument("--host", required=True, help="Firewall IP or FQDN")
    parser.add_argument("--username", help="Admin username")
    parser.add_argument("--password", help="Admin password (If omitted, will prompt)")
    parser.add_argument("--api-key", help="PAN-OS API Key")
    
    # 안전장치 플래그
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without changes")

    subparsers = parser.add_subparsers(dest="command")

    # 명령별 인자 설정
    addr = subparsers.add_parser("add-address", help="Create an Address Object")
    addr.add_argument("--name", required=True)
    addr.add_argument("--value", required=True)
    addr.add_argument("--description")

    grp = subparsers.add_parser("add-group", help="Create an Address Group")
    grp.add_argument("--name", required=True)
    grp.add_argument("--members", required=True, help="Comma-separated list or .txt file path")

    rule = subparsers.add_parser("add-rule", help="Create/Update Security Rule")
    rule.add_argument("--name", required=True)
    rule.add_argument("--from-zone", required=True)
    rule.add_argument("--to-zone", required=True)
    rule.add_argument("--source", required=True)
    rule.add_argument("--destination", required=True)
    rule.add_argument("--application", required=True)
    rule.add_argument("--service", required=True)
    rule.add_argument("--action", required=True)

    subparsers.add_parser("gp-users", help="List active GP users")
    
    gp_logout = subparsers.add_parser("gp-logout", help="Logout a specific GP user")
    gp_logout.add_argument("--user", required=True)

    # API Key Retrieval
    subparsers.add_parser("get-api-key", help="Fetch permanent API Key using credentials")

    # Connectivity Test
    subparsers.add_parser("test-connection", help="Verify API access and show system info")

    subparsers.add_parser("commit", help="Commit changes (Auto-backup)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        # get-api-key 명령어는 별도의 연결 방식 사용
        if args.command == "get-api-key":
            fetch_api_key(args.host, args.username, args.password)
            return

        fw = connect_firewall(
            args.host,
            args.username,
            args.password,
            args.api_key
        )

        if args.command == "add-address":
            add_address_object(fw, args.name, args.value, args.description, args.dry_run)

        elif args.command == "add-group":
            add_address_group(fw, args.name, args.members, args.dry_run)

        elif args.command == "add-rule":
            create_or_update_rule(
                fw,
                args.name,
                args.from_zone,
                args.to_zone,
                args.source,
                args.destination,
                args.application,
                args.service,
                args.action,
                args.dry_run
            )

        elif args.command == "gp-users":
            show_globalprotect_users(fw)

        elif args.command == "gp-logout":
            logout_globalprotect_user(fw, args.user, args.dry_run)

        elif args.command == "test-connection":
            test_connection(fw)

        elif args.command == "commit":
            commit_config(fw, args.dry_run)

    except PanDeviceError as e:
        print(f"[PAN-OS ERROR] {e}")
        sys.exit(1)

    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
