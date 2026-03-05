# Palo Alto Firewall Web Controller

A web-based management interface for Palo Alto Networks firewalls, built with FastAPI and the official `pan-os-python` SDK.

Designed to simplify firewall object management without requiring direct CLI or GUI access to the device.

---

## Features

- **Firewall Connection** — supports both API key and username/password authentication
- **Address Object Management** — list, add, and bulk-import address objects
- **Address Group Management** — view static/dynamic groups and their members
- **CSV Bulk Import** — upload up to 500 address objects at once via CSV file (UTF-8 and EUC-KR/cp949 supported)
- **Commit with Auto-Backup** — saves running config as XML before every commit
- **Partial Commit** — commit only changes made by the authenticated admin
- **Non-blocking API** — all SDK calls run in a thread pool to avoid blocking the async event loop

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3, FastAPI, Uvicorn |
| Firewall SDK | pan-os-python (panos) |
| Frontend | Vanilla HTML / CSS / JavaScript |
| Config | python-dotenv (.env) |

---

## Project Structure

```
.
├── app.py              # FastAPI backend — all API endpoints
├── paloalto_xml.py     # Legacy CLI script (reference)
├── static/
│   ├── index.html
│   ├── script.js
│   └── style.css
├── template_env.txt    # .env template
├── requirements.txt
└── backups/            # Auto-generated XML backups before each commit
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Access to a Palo Alto Networks firewall (PAN-OS 9.x or later)

### Installation

```bash
git clone https://github.com/90yard/gst-securitys.git
cd gst-securitys
pip install -r requirements.txt
```

### Configuration

Copy the template and fill in your firewall credentials:

```bash
cp template_env.txt .env
```

`.env` format:

```
PAN_HOST=<firewall-ip>
PAN_USER=<username>
PAN_KEY=<api-key>
```

### Run

```bash
uvicorn app:app --reload
```

Open `http://localhost:8000` in your browser.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/connect` | Test firewall connectivity |
| `POST` | `/api/address/list` | List all address objects |
| `POST` | `/api/address/add` | Add a single address object |
| `POST` | `/api/address/bulk` | Bulk-import address objects from CSV |
| `POST` | `/api/group/list` | List all address groups |
| `POST` | `/api/commit` | Commit changes (with auto-backup) |

All endpoints accept JSON with `host`, `api_key` (or `username` + `password`) fields.

### CSV Format (for bulk import)

```
name,value,type,description
block-list-1,192.168.1.0/24,ip-netmask,Internal subnet
bad-host,10.0.0.5,ip-netmask,Known bad actor
```

- `type` defaults to `ip-netmask` if omitted
- `description` is optional
- Duplicate names are automatically skipped

---

## Architecture Notes

- SDK calls are wrapped with `ThreadPoolExecutor` + `run_in_executor` to prevent blocking FastAPI's async event loop
- Every commit automatically saves a timestamped XML backup under `backups/` before applying changes
- `.env` is loaded at startup via a custom `load_env_file()` — no external dependency required

---

## License

MIT
