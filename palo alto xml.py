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
import csv           # 일괄 등록(CSV) 지원
from typing import List


# -------------------------------------------------------
# [2] PAN-OS SDK import (XML API 래핑)
# -------------------------------------------------------

from panos.firewall import Firewall
from panos.objects import AddressObject, AddressGroup
from panos.policies import SecurityRule
from panos.errors import PanDeviceError
import pan.xapi        # API Key 발급을 위해 직접 호출


# -------------------------------------------------------
# [3] 방화벽 연결 함수
# -------------------------------------------------------

def load_env_file(filepath=".env"):
    """
    .env 파일을 읽어서 환경 변수로 등록 (간이 구현)
    """
    if os.path.isfile(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, value = line.split('=', 1)
                    # 따옴표 제거 및 환경 변수 등록
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
            return True
        except Exception as e:
            print(f"[WARNING] Failed to load .env file: {e}")
    return False


def connect_firewall(host, username=None, password=None, api_key=None):
    """
    Palo Alto 방화벽에 연결하는 함수
    """

    # API Key 방식
    if api_key:
        fw = Firewall(hostname=host, api_key=api_key)
        if username:
            fw.api_username = username  # Partial Commit을 위해 계정명 저장
        fw._auth_method = "API Key"  # 인증 방식 기록

    # 계정/비밀번호 방식
    elif username:
        if not password:
            # 터미널에서 보안 입력 받기
            password = getpass.getpass(f"Password for {username}@{host}: ")
        
        # pan-os-python의 Firewall 클래스 생성
        fw = Firewall(hostname=host, api_username=username, api_password=password)
        fw.api_username = username   # Partial Commit을 위해 계정명 저장
        fw._auth_method = "ID/Password"  # 인증 방식 기록

    else:
        raise ValueError("Authentication (API Key or Username) is required. (Tip: Use double quotes for passwords with special characters like $)")

    return fw


# -------------------------------------------------------
# [4] API Key 발급 함수
# -------------------------------------------------------

def fetch_api_key(host, username, password=None):
    """
    ID/PW를 사용하여 방화벽에서 API Key를 직접 요청 (pan-python 라이브러리 직접 활용)
    """
    if not password:
        password = getpass.getpass(f"Enter password for {username} to fetch API Key: ")
    
    try:
        # SDK보다 로우레벨인 pan.xapi를 직접 사용하여 변수 의존성 제거
        xapi = pan.xapi.PanXapi(hostname=host, api_username=username, api_password=password)
        xapi.keygen()
        api_key = xapi.api_key
        
        if api_key:
            print("\n" + "="*50)
            print(f"[*] Successfully retrieved API Key for {username}@{host}")
            print(f"[*] API KEY: {api_key}")
            print("="*50)
            print("[TIP] This key can be used with the --api-key argument instead of ID/PW.\n")
            return api_key
        else:
            print("[ERROR] Failed to retrieve API Key: Empty result")
            return None
            
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
            print(f"[*] Authenticated via: {getattr(fw, '_auth_method', 'Unknown')}")
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


def print_table(headers, data):
    """
    ASCII 테이블 형식으로 데이터 출력
    """
    if not data:
        print("[INFO] No data to display.")
        return

    # 각 컬럼의 최대 너비 계산
    col_widths = [len(h) for h in headers]
    for row in data:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    # 구분선 생성
    separator = "+" + "+".join(["-" * (w + 2) for w in col_widths]) + "+"
    
    # 헤더 출력
    print(separator)
    header_row = "|" + "|".join([f" {h:<{col_widths[i]}} " for i, h in enumerate(headers)]) + "|"
    print(header_row)
    print(separator)

    # 데이터 출력
    for row in data:
        data_row = "|" + "|".join([f" {str(val):<{col_widths[i]}} " for i, val in enumerate(row)]) + "|"
        print(data_row)
    
    print(separator)


# -------------------------------------------------------
# [6] 설정 백업 함수 (안전장치)
# -------------------------------------------------------

def backup_config(fw):
    """
    Running Config를 로컬 backups/ 폴더에 백업
    """
    # backups 폴더 생성
    os.makedirs("backups", exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join("backups", f"backup_{fw.hostname}_{timestamp}.xml")
    
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

def add_address_object(fw, name, value, description=None, type="ip-netmask", bulk_file=None, dry_run=False):
    """
    Address Object 생성 (단일 또는 일괄)
    """
    objects_to_create = []

    # 1. 일괄 등록 모드 (파일)
    if bulk_file:
        if not os.path.isfile(bulk_file):
            print(f"[ERROR] File not found: {bulk_file}")
            return
        
        print(f"[INFO] Loading addresses from {bulk_file}...")
        try:
            with open(bulk_file, 'r', encoding='utf-8-sig') as f:
                # CSV 형식 지원 (이름,값,타입,설명)
                reader = csv.reader(f)
                for row in reader:
                    if not row or not row[0].strip() or row[0].strip().startswith('#'): 
                        continue
                    
                    # 부족한 필드는 기본값 채움
                    b_name = row[0].strip()
                    b_value = row[1].strip() if len(row) > 1 else ""
                    b_type = row[2].strip() if len(row) > 2 else "ip-netmask"
                    b_desc = row[3].strip() if len(row) > 3 else ""
                    
                    obj = AddressObject(name=b_name, value=b_value, type=b_type, description=b_desc)
                    objects_to_create.append(obj)
            print(f"[INFO] Loaded {len(objects_to_create)} objects from file.")
        except Exception as e:
            print(f"[ERROR] Failed to read file: {e}")
            return
    
    # 2. 단일 등록 모드
    else:
        objects_to_create.append(AddressObject(name=name, value=value, type=type, description=description))

    # 3. 실제 생성 (최적화 적용)
    if dry_run:
        for obj in objects_to_create:
            print(f"[DRY-RUN] Would create Address Object ({obj.type}): {obj.name} = {obj.value}")
        return

    try:
        # 방화벽 트리 연결
        for obj in objects_to_create:
            fw.add(obj)
        
        # [Optimization] Bulk push (한 번의 API 호출로 모두 생성)
        if objects_to_create:
            # 첫 번째 객체를 기준으로 create_similar() 실행 (동일 타입 대량 생성 시 유리)
            objects_to_create[0].create_similar()
            print(f"[OK] Successfully created {len(objects_to_create)} Address Object(s).")
    except Exception as e:
        print(f"[ERROR] Bulk creation failed: {e}")
        print("[TIP] Check if any object names already exist or if values are invalid.")


def delete_address_object(fw, name=None, bulk_file=None, dry_run=False):
    """
    Address Object 삭제 (단일 또는 일괄)
    """
    objects_to_delete = []

    if bulk_file:
        if not os.path.isfile(bulk_file):
            print(f"[ERROR] File not found: {bulk_file}")
            return
        
        try:
            with open(bulk_file, 'r', encoding='utf-8-sig') as f:
                names = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
                for n in names:
                    objects_to_delete.append(AddressObject(name=n))
            print(f"[INFO] Loaded {len(objects_to_delete)} names for deletion from {bulk_file}.")
        except Exception as e:
            print(f"[ERROR] Failed to read file: {e}")
            return
    else:
        objects_to_delete.append(AddressObject(name=name))

    if dry_run:
        for obj in objects_to_delete:
            print(f"[DRY-RUN] Would delete Address Object: {obj.name}")
        return

    try:
        for obj in objects_to_delete:
            fw.add(obj)
        
        if objects_to_delete:
            # [Optimization] Bulk delete
            objects_to_delete[0].delete_similar()
            print(f"[OK] Successfully deleted {len(objects_to_delete)} Address Object(s).")
    except Exception as e:
        print(f"[ERROR] Deletion failed: {e}")
        print("[TIP] Objects might not exist or are currently in use by policies/groups.")


def check_usage(fw, name):
    """
    특정 주소 객체가 어디서 사용 중인지 검색 (그룹, 정책)
    """
    print(f"[INFO] Searching for references of '{name}' on {fw.hostname}...")
    found_count = 0

    try:
        # 1. 주소 그룹 검색
        groups = AddressGroup.refreshall(fw)
        for g in groups:
            if g.static_value and name in g.static_value:
                print(f"[FOUND] Included in Address Group: {g.name}")
                found_count += 1

        # 2. 보안 정책 검색
        rules = SecurityRule.refreshall(fw)
        for r in rules:
            if name in (r.source if r.source else []) or name in (r.destination if r.destination else []):
                role = "Source" if name in (r.source if r.source else []) else "Destination"
                if name in (r.source if r.source else []) and name in (r.destination if r.destination else []):
                    role = "Source & Destination"
                print(f"[FOUND] Used in Security Rule: {r.name} ({role})")
                found_count += 1

        if found_count == 0:
            print(f"[OK] No references found for '{name}'. It should be safe to delete.")
        else:
            print(f"\n[SUMMARY] Found {found_count} references. Remove these before deleting the object.")

    except Exception as e:
        print(f"[ERROR] Usage check failed: {e}")


def list_address_objects(fw):
    """
    모든 Address Object를 테이블 형식으로 출력
    """
    print(f"[INFO] Fetching Address Objects from {fw.hostname}...")
    try:
        objects = AddressObject.refreshall(fw)
        headers = ["Name", "Value", "Type", "Description"]
        data = []
        for obj in objects:
            data.append([
                obj.name,
                obj.value,
                obj.type,
                obj.description if obj.description else ""
            ])
        
        # 이름순 정렬
        data.sort(key=lambda x: x[0])
        print_table(headers, data)
        print(f"Total: {len(data)} objects")
    except Exception as e:
        print(f"[ERROR] Failed to fetch objects: {e}")


# -------------------------------------------------------
# [8] Address Group 생성
# -------------------------------------------------------

def add_address_group(fw, name, members_input, dry_run=False):
    """
    Static Address Group 생성 (멤버 존재 여부 사전 검토 포함)
    """
    members = []
    if os.path.isfile(members_input) and members_input.endswith('.txt'):
        with open(members_input, 'r', encoding='utf-8') as f:
            members = [line.strip() for line in f if line.strip()]
        print(f"[INFO] Loaded {len(members)} members from file: {members_input}")
    else:
        members = [m.strip() for m in members_input.split(',')]

    # [Safety Check] 멤버 존재 여부 확인
    if not dry_run:
        print("[INFO] Verifying members existence to prevent commit errors...")
        try:
            # 현재 장비의 모든 Address Object 이름 가져오기
            existing_objects = AddressObject.refreshall(fw)
            existing_names = [obj.name for obj in existing_objects]
            
            missing_members = [m for m in members if m not in existing_names]
            if missing_members:
                print(f"[ERROR] The following members do not exist: {missing_members}")
                print("[ABORT] Group creation canceled to prevent commit failure.")
                return
            print("[OK] All members verified.")
        except Exception as e:
            print(f"[WARNING] Could not verify members: {e} (Proceeding anyway)")

    if dry_run:
        print(f"[DRY-RUN] Would create Address Group: {name}")
        print(f"          Members ({len(members)}): {members[:5]} ...")
        return

    group = AddressGroup(name=name, static_value=members)
    fw.add(group)
    group.create()
    print(f"[OK] Address Group created: {name} (Total: {len(members)})")


def list_address_groups(fw):
    """
    모든 Address Group을 테이블 형식으로 출력
    """
    print(f"[INFO] Fetching Address Groups from {fw.hostname}...")
    try:
        groups = AddressGroup.refreshall(fw)
        headers = ["Name", "Type", "Members"]
        data = []
        for g in groups:
            # 멤버 리스트를 문자열로 변환 (최대 3개까지 표시하고 나머지는 줄임표)
            m_list = g.static_value if g.static_value else []
            m_str = ", ".join(m_list[:3])
            if len(m_list) > 3:
                m_str += f", ... (+{len(m_list)-3})"
            
            data.append([
                g.name,
                "Static" if g.static_value else "Dynamic",
                m_str
            ])
        
        data.sort(key=lambda x: x[0])
        print_table(headers, data)
        print(f"Total: {len(data)} groups")
    except Exception as e:
        print(f"[ERROR] Failed to fetch groups: {e}")


def delete_address_group(fw, name, dry_run=False):
    """
    Address Group 삭제
    """
    if dry_run:
        print(f"[DRY-RUN] Would delete Address Group: {name}")
        return

    try:
        group = AddressGroup(name=name)
        fw.add(group)
        group.delete()
        print(f"[OK] Address Group deleted: {name}")
    except Exception as e:
        print(f"[ERROR] Failed to delete group '{name}': {e}")


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

def commit_config(fw, partial=False, dry_run=False):
    """
    Candidate config → Running config 반영
    partial: 현재 관리자(API 접속 계정)의 변경사항만 반영할지 여부
    """
    if dry_run:
        print(f"[DRY-RUN] Would commit configuration (Partial: {partial})")
        return

    # 1. 안전장치: 백업 수행
    backup_config(fw)

    # 2. Commit 수행
    print(f"[INFO] Commit started (Partial: {partial})...")
    try:
        # partial=True 이면 현재 세션의 관리자 리스트만 보냄
        admins = None
        if partial:
            # connect_firewall에서 사용한 계정명 추출
            current_admin = getattr(fw, 'api_username', None)
            if current_admin:
                admins = [current_admin]
                print(f"[INFO] Only committing changes made by admin: {current_admin}")
            else:
                print("[ERROR] admin name is unknown. Partial commit requires --username argument even when using --api-key.")
                return

        fw.commit(sync=True, admins=admins)
        print("[OK] Commit completed successfully")
    except Exception as e:
        print(f"[ERROR] Commit failed: {e}")
        print("Tip: Check the backup folder if rollback is needed.")


# -------------------------------------------------------
# [12] CLI 엔트리 포인트
# -------------------------------------------------------

def main():
    # 0. .env 파일이 있으면 로드
    load_env_file()

    # 1. 공통 인자를 담은 부모 파서 생성
    # [Connection] 모든 명령어가 공유
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument("-H", "--host", 
                               default=os.environ.get("PAN_HOST"),
                               required=not os.environ.get("PAN_HOST"), 
                               help="Firewall IP or FQDN (Default: env PAN_HOST)")
    base_parser.add_argument("-u", "--username", 
                               default=os.environ.get("PAN_USER"),
                               help="Admin username (Default: env PAN_USER)")
    base_parser.add_argument("-p", "--password", 
                               default=os.environ.get("PAN_PASS"),
                               help="Admin password (Default: env PAN_PASS)")
    base_parser.add_argument("-k", "--api-key", 
                               default=os.environ.get("PAN_KEY"),
                               help="PAN-OS API Key (Default: env PAN_KEY)")

    # [Action] 설정 변경이 있는 명령어만 --dry-run 지원
    action_parser = argparse.ArgumentParser(add_help=False, parents=[base_parser])
    action_parser.add_argument("-d", "--dry-run", action="store_true", help="Simulate actions without changes")

    # 2. 메인 파서 생성
    parser = argparse.ArgumentParser(
        description="Palo Alto Firewall Management Tool (Safe Mode)"
    )
    subparsers = parser.add_subparsers(dest="command")

    # 3. 각 명령에 부모 파서(parent_parser)를 상속시켜 공통 인자 포함
    
    # [Add Address]
    addr = subparsers.add_parser("add-address", parents=[action_parser], help="Create Address Object(s)")
    addr.add_argument("--name", help="Name of the object (Required if not using --file)")
    addr.add_argument("--value", help="Value of the object (Required if not using --file)")
    addr.add_argument("--description")
    addr.add_argument("--type", choices=["ip-netmask", "ip-range", "fqdn"], default="ip-netmask", help="Type (default: ip-netmask)")
    addr.add_argument("--file", help="CSV file for bulk import (format: name,value,type,description)")

    # [List Address]
    subparsers.add_parser("list-address", parents=[base_parser], help="List all Address Objects in table format")

    # [Add Group]
    grp = subparsers.add_parser("add-group", parents=[action_parser], help="Create an Address Group")
    grp.add_argument("--name", required=True)
    grp.add_argument("--members", required=True, help="Comma-separated list or .txt file path")
    
    # [Delete Address]
    del_addr = subparsers.add_parser("del-address", parents=[action_parser], help="Delete Address Object(s)")
    del_addr.add_argument("--name", help="Name of the object to delete")
    del_addr.add_argument("--file", help="TXT file containing names to delete (one per line)")

    # [Check Usage]
    check = subparsers.add_parser("check-usage", parents=[base_parser], help="Find where an address object is used")
    check.add_argument("--name", required=True, help="Name of the object to check")

    # [Delete Group]
    del_grp = subparsers.add_parser("del-group", parents=[action_parser], help="Delete an Address Group")
    del_grp.add_argument("--name", required=True, help="Name of the group to delete")

    # [List Group]
    subparsers.add_parser("list-group", parents=[base_parser], help="List all Address Groups in table format")

    # [Add Rule]
    rule = subparsers.add_parser("add-rule", parents=[action_parser], help="Create/Update Security Rule")
    rule.add_argument("--name", required=True)
    rule.add_argument("--from-zone", required=True)
    rule.add_argument("--to-zone", required=True)
    rule.add_argument("--source", required=True)
    rule.add_argument("--destination", required=True)
    rule.add_argument("--application", required=True)
    rule.add_argument("--service", required=True)
    rule.add_argument("--action", required=True)

    # [GP Users]
    subparsers.add_parser("gp-users", parents=[base_parser], help="List active GP users")
    
    # [GP Logout]
    gp_logout = subparsers.add_parser("gp-logout", parents=[action_parser], help="Logout a specific GP user")
    gp_logout.add_argument("--user", required=True)

    # [Get API Key]
    subparsers.add_parser("get-api-key", parents=[base_parser], help="Fetch permanent API Key using credentials")

    # [Connectivity Test]
    subparsers.add_parser("test-connection", parents=[base_parser], help="Verify API access and show system info")

    # [Commit]
    cmt = subparsers.add_parser("commit", parents=[action_parser], help="Commit changes (Auto-backup)")
    cmt.add_argument("--partial", action="store_true", help="Only commit changes made by current admin")

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
            if not args.file and (not args.name or not args.value):
                print("[ERROR] Either --file or both --name and --value are required.")
                return
            add_address_object(fw, args.name, args.value, args.description, args.type, args.file, getattr(args, 'dry_run', False))

        elif args.command == "list-address":
            list_address_objects(fw)

        elif args.command == "add-group":
            add_address_group(fw, args.name, args.members, getattr(args, 'dry_run', False))

        elif args.command == "list-group":
            list_address_groups(fw)

        elif args.command == "del-address":
            if not args.name and not args.file:
                print("[ERROR] Either --name or --file is required for deletion.")
                return
            delete_address_object(fw, args.name, args.file, getattr(args, 'dry_run', False))

        elif args.command == "check-usage":
            check_usage(fw, args.name)

        elif args.command == "del-group":
            delete_address_group(fw, args.name, getattr(args, 'dry_run', False))

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
                getattr(args, 'dry_run', False)
            )

        elif args.command == "gp-users":
            show_globalprotect_users(fw)

            logout_globalprotect_user(fw, args.user, getattr(args, 'dry_run', False))

        elif args.command == "test-connection":
            test_connection(fw)

        elif args.command == "commit":
            commit_config(fw, args.partial, getattr(args, 'dry_run', False))

    except PanDeviceError as e:
        print(f"[PAN-OS ERROR] {e}")
        sys.exit(1)

    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()