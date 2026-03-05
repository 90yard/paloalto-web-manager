import io
import csv
import os
import logging
import datetime
import asyncio
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from panos.firewall import Firewall
from panos.objects import AddressObject, AddressGroup
from panos.errors import PanDeviceError


# -------------------------------------------------------
# Logging
# -------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# -------------------------------------------------------
# .env Loading
# -------------------------------------------------------
def load_env_file(filepath=".env"):
    if os.path.isfile(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
            return True
        except Exception as e:
            logger.warning(f"Failed to load .env file: {e}")
    return False

load_env_file()


# -------------------------------------------------------
# App & Static Files
# -------------------------------------------------------
app = FastAPI(title="Palo Alto Web Controller")

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Thread pool for blocking SDK calls (prevents event loop blocking)
executor = ThreadPoolExecutor(max_workers=3)


# -------------------------------------------------------
# API Models
# -------------------------------------------------------
class ConnectionConfig(BaseModel):
    host: str
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None


class AddressObjectRequest(ConnectionConfig):
    name: str
    value: str
    description: Optional[str] = ""
    type: str = "ip-netmask"


class CommitRequest(ConnectionConfig):
    partial: bool = False


# -------------------------------------------------------
# Helper: Firewall Connection
# -------------------------------------------------------
def _make_firewall(config: ConnectionConfig) -> Firewall:
    """Create a Firewall instance (no network call). Validates auth params."""
    if config.api_key:
        fw = Firewall(hostname=config.host, api_key=config.api_key)
        if config.username:
            fw.api_username = config.username
    elif config.username and config.password:
        fw = Firewall(
            hostname=config.host,
            api_username=config.username,
            api_password=config.password
        )
        fw.api_username = config.username
    else:
        raise HTTPException(
            status_code=400,
            detail="api_key 또는 username+password 중 하나는 필수입니다."
        )
    fw.timeout = 30
    return fw


# -------------------------------------------------------
# Endpoints
# -------------------------------------------------------
@app.get("/")
async def read_index():
    return FileResponse("static/index.html")


@app.post("/api/connect")
async def connect(config: ConnectionConfig):
    fw = _make_firewall(config)
    loop = asyncio.get_event_loop()

    def _test():
        try:
            fw.op("show system info", cmd_xml=True)
        except PanDeviceError as e:
            raise HTTPException(status_code=401, detail=f"연결 테스트 실패: {e}")

    try:
        await loop.run_in_executor(executor, _test)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"Connection verified: {config.host}")
    return {"status": "success", "message": "Connection verified"}


@app.post("/api/address/list")
async def list_addresses(config: ConnectionConfig):
    fw = _make_firewall(config)
    loop = asyncio.get_event_loop()

    def _fetch():
        try:
            objects = AddressObject.refreshall(fw)
            data = sorted(
                [[obj.name, obj.value, obj.type, obj.description or ""] for obj in objects],
                key=lambda x: x[0]
            )
            return data
        except PanDeviceError as e:
            raise HTTPException(status_code=500, detail=f"Address Object 조회 실패: {e}")

    try:
        data = await loop.run_in_executor(executor, _fetch)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"Fetched {len(data)} address objects from {config.host}")
    return {"status": "success", "data": data}


@app.post("/api/address/add")
async def add_address(addr: AddressObjectRequest):
    fw = _make_firewall(addr)
    loop = asyncio.get_event_loop()

    def _create():
        try:
            obj = AddressObject(
                name=addr.name,
                value=addr.value,
                type=addr.type,
                description=addr.description
            )
            fw.add(obj)
            obj.create()
        except PanDeviceError as e:
            raise HTTPException(status_code=500, detail=f"Address Object 생성 실패: {e}")

    try:
        await loop.run_in_executor(executor, _create)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"Created address object '{addr.name}' on {addr.host}")
    return {"status": "success", "message": f"Address Object '{addr.name}' created"}


@app.post("/api/group/list")
async def list_groups(config: ConnectionConfig):
    fw = _make_firewall(config)
    loop = asyncio.get_event_loop()

    def _fetch():
        try:
            groups = AddressGroup.refreshall(fw)
            data = []
            for g in groups:
                m_list = g.static_value if g.static_value else []
                m_str = ", ".join(m_list[:3])
                if len(m_list) > 3:
                    m_str += f", ...(+{len(m_list) - 3})"
                data.append([
                    g.name,
                    "Static" if g.static_value else "Dynamic",
                    m_str,
                ])
            data.sort(key=lambda x: x[0])
            return data
        except PanDeviceError as e:
            raise HTTPException(status_code=500, detail=f"Address Group 조회 실패: {e}")

    try:
        data = await loop.run_in_executor(executor, _fetch)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"Fetched {len(data)} address groups from {config.host}")
    return {"status": "success", "data": data}


@app.post("/api/commit")
async def commit_changes(req: CommitRequest):
    fw = _make_firewall(req)
    loop = asyncio.get_event_loop()

    def _commit():
        # 1. Backup before commit
        os.makedirs("backups", exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join("backups", f"backup_{fw.hostname}_{timestamp}.xml")
        try:
            config_xml = fw.op("show config running", cmd_xml=True)
            with open(backup_path, "w", encoding="utf-8") as f:
                xml_str = ET.tostring(config_xml, encoding='utf8', method='xml').decode('utf8')
                f.write(xml_str)
            logger.info(f"Backup saved: {backup_path}")
        except Exception as e:
            logger.warning(f"Backup failed (commit will continue): {e}")

        # 2. Commit
        try:
            admins = None
            if req.partial:
                current_admin = getattr(fw, 'api_username', None)
                if not current_admin:
                    raise HTTPException(
                        status_code=400,
                        detail="Partial commit requires username. Please provide username."
                    )
                admins = [current_admin]
                logger.info(f"Partial commit for admin: {current_admin}")

            fw.timeout = 300  # commit job 완료 대기 타임아웃 (5분)
            fw.commit(sync=True, admins=admins)
            logger.info(f"Commit completed on {fw.hostname}")
        except HTTPException:
            raise
        except PanDeviceError as e:
            raise HTTPException(status_code=500, detail=f"Commit 실패: {e}")

    try:
        await loop.run_in_executor(executor, _commit)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "success", "message": "Commit completed"}


@app.post("/api/address/bulk")
async def bulk_add_addresses(
    file: UploadFile = File(...),
    host: str = Form(...),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    api_key: Optional[str] = Form(None),
):
    # 1. Read & size-check
    content = await file.read()
    if len(content) > 1 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일 크기는 1MB 이하여야 합니다.")

    # 2. Decode — try UTF-8 (with BOM) first, fall back to cp949 (Excel Korean default)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp949")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="파일 인코딩을 읽을 수 없습니다. UTF-8 또는 EUC-KR(cp949)로 저장해 주세요.")
    reader = csv.reader(io.StringIO(text))
    rows = []
    for i, line in enumerate(reader):
        if not line:
            continue
        first = line[0].strip()
        if not first or first.startswith("#"):
            continue
        # Auto-detect header: skip if first cell contains 'name' (case-insensitive)
        if i == 0 and first.lower() == "name":
            continue
        if len(line) < 2 or not line[1].strip():
            raise HTTPException(
                status_code=400,
                detail=f"행 {i+1}: name과 value는 필수입니다. ({','.join(line)})"
            )
        name = line[0].strip()
        value = line[1].strip()
        addr_type = line[2].strip() if len(line) > 2 and line[2].strip() else "ip-netmask"
        description = line[3].strip() if len(line) > 3 else ""
        rows.append((name, value, addr_type, description))
        if len(rows) >= 500:
            break

    if not rows:
        raise HTTPException(status_code=400, detail="유효한 데이터 행이 없습니다.")

    config = ConnectionConfig(host=host, username=username, password=password, api_key=api_key)
    fw = _make_firewall(config)
    loop = asyncio.get_event_loop()

    def _bulk_create():
        try:
            existing = {obj.name for obj in AddressObject.refreshall(fw)}
        except PanDeviceError as e:
            raise HTTPException(status_code=500, detail=f"기존 객체 조회 실패: {e}")

        skipped = [r[0] for r in rows if r[0] in existing]
        to_create = [r for r in rows if r[0] not in existing]

        if not to_create:
            return 0, skipped

        objects = [
            AddressObject(name=r[0], value=r[1], type=r[2], description=r[3])
            for r in to_create
        ]
        for obj in objects:
            fw.add(obj)

        try:
            objects[0].create_similar()
        except PanDeviceError as e:
            raise HTTPException(status_code=500, detail=f"일괄 등록 실패: {e}")

        return len(to_create), skipped

    try:
        created, skipped = await loop.run_in_executor(executor, _bulk_create)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if created == 0:
        msg = f"모두 이미 존재합니다. ({len(skipped)}개 건너뜀)"
    else:
        msg = f"{created}개 등록 완료"
        if skipped:
            msg += f", {len(skipped)}개 건너뜀 (이미 존재)"

    logger.info(f"Bulk add on {host}: created={created}, skipped={len(skipped)}")
    return {
        "status": "success",
        "created": created,
        "skipped": len(skipped),
        "skipped_names": skipped,
        "message": msg,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
