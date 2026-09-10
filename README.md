# Organic Chemistry Academy — Live Teacher-Managed Website

A self-contained Class 11 & 12 organic chemistry learning website with:

- Premium responsive student-facing UI
- Teacher admin dashboard
- Add/edit/delete/publish concepts, videos, notes, resources and announcements
- Class 11 / Class 12 chapter organization
- Search
- Direct PDF/image/video/document uploads
- Optional external teacher video links
- SQLite database (no separate database service required)
- Server-Sent Events (SSE) live update signal: when the teacher publishes a change, open student pages automatically reload with the newest content

## 1. Install

Python 3.11+ is recommended.

### Windows PowerShell

```powershell
cd organic_chemistry_realtime_site
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Linux/macOS

```bash
cd organic_chemistry_realtime_site
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Set teacher login and security secret

For a quick local test, the defaults are:

- Username: `teacher`
- Password: `chemistry123`

**Change these before putting the website on the internet.**

PowerShell example:

```powershell
$env:ADMIN_USERNAME="teacher"
$env:ADMIN_PASSWORD="your-strong-password"
$env:SITE_SECRET_KEY="replace-this-with-a-long-random-secret"
```

Linux/macOS example:

```bash
export ADMIN_USERNAME="teacher"
export ADMIN_PASSWORD="your-strong-password"
export SITE_SECRET_KEY="replace-this-with-a-long-random-secret"
```

## 3. Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:

- Public site: `http://127.0.0.1:8000`
- Teacher dashboard: `http://127.0.0.1:8000/admin/login`

## How the real-time behavior works

1. The teacher signs in to `/admin/login`.
2. The teacher creates, updates, publishes or deletes content.
3. The change is committed to the SQLite database on the server.
4. The server broadcasts an SSE version update to all connected public browser pages.
5. Those pages automatically reload and show the new database content.

So there is only **one source of truth**. Students do not receive separate copies of the website.

## Making it visible to everyone on the internet

The app itself is complete, but any real public website needs one computer/server to stay online and serve it. Run the exact same project on a public Linux VM or another server you control, expose port 8000 through a reverse proxy, and point your domain at it. Because SQLite and uploaded files live on that server, teacher changes remain persistent.

For a production deployment, also use HTTPS and set the session cookie to `secure=True` in `app/main.py` once HTTPS is active.

## Data location

- Database: `app/data/site.db`
- Uploaded teacher files: `app/static/uploads/`

Back up these two locations to preserve all teacher content.
