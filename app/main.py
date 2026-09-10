from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
DB_PATH = DATA_DIR / "site.db"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "teacher")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "chemistry123")
SECRET_KEY = os.getenv("SITE_SECRET_KEY", "dev-secret-change-me")
COOKIE_NAME = "orgchem_admin"

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp",
    ".mp4", ".webm", ".mov", ".doc", ".docx", ".ppt", ".pptx"
}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024

content_version = 1
version_condition = asyncio.Condition()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "lesson"


def unique_slug(conn: sqlite3.Connection, title: str, exclude_id: Optional[int] = None) -> str:
    base = slugify(title)
    candidate = base
    counter = 2
    while True:
        if exclude_id:
            row = conn.execute("SELECT id FROM content WHERE slug = ? AND id != ?", (candidate, exclude_id)).fetchone()
        else:
            row = conn.execute("SELECT id FROM content WHERE slug = ?", (candidate,)).fetchone()
        if not row:
            return candidate
        candidate = f"{base}-{counter}"
        counter += 1


def init_db() -> None:
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_level TEXT NOT NULL DEFAULT '11',
            chapter TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            content_type TEXT NOT NULL DEFAULT 'concept',
            summary TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            video_url TEXT NOT NULL DEFAULT '',
            upload_path TEXT NOT NULL DEFAULT '',
            published INTEGER NOT NULL DEFAULT 1,
            featured INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )

    defaults = {
        "site_name": "Organic Chemistry Academy",
        "teacher_name": "Your Chemistry Teacher",
        "hero_title": "Organic Chemistry, made visual and memorable.",
        "hero_subtitle": "A focused Class 11 & 12 learning space for concepts, mechanisms, reactions, notes and teacher-led video lessons.",
        "teacher_bio": "Clear explanations, exam-focused practice and strong conceptual foundations for Class 11 and Class 12 Organic Chemistry.",
    }
    for key, value in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value))

    count = conn.execute("SELECT COUNT(*) FROM content").fetchone()[0]
    if count == 0:
        now = utc_now()
        samples = [
            ("11", "General Organic Chemistry", "General Organic Chemistry (GOC)", "concept", "Build the foundation: electronic effects, acidity/basicity and reactive intermediates.", "Organic chemistry becomes easier once you learn how electrons move. Start with inductive effect, resonance, hyperconjugation and the stability of carbocations, carbanions and free radicals.\n\nKey idea: most reaction mechanisms can be understood by identifying an electron-rich site, an electron-poor site and the most stable intermediate or transition pathway.", 1),
            ("11", "Nomenclature", "IUPAC Nomenclature", "concept", "A systematic method to name organic compounds confidently.", "1. Select the longest parent chain containing the principal functional group.\n2. Number it to give the principal functional group the lowest locant.\n3. Name and alphabetize substituents.\n4. Add unsaturation and the functional-group suffix.\n\nPractice by naming structures from simple alkanes to multifunctional compounds.", 1),
            ("11", "Isomerism", "Structural & Stereoisomerism", "concept", "Understand how the same molecular formula can create different molecules.", "Structural isomerism changes connectivity; stereoisomerism changes three-dimensional arrangement. Focus on chain, position, functional, geometrical and optical isomerism, and always connect the definition to a structure.", 0),
            ("11", "Hydrocarbons", "Hydrocarbons: Alkanes, Alkenes & Alkynes", "concept", "Reaction patterns of the most important hydrocarbon families.", "Compare substitution in alkanes with electrophilic addition in alkenes and alkynes. Learn Markovnikov orientation, peroxide effect where applicable, oxidation and common preparation methods.", 0),
            ("12", "Haloalkanes & Haloarenes", "SN1 vs SN2 Reactions", "concept", "Predict substitution mechanisms using substrate, nucleophile and solvent.", "SN1 proceeds through a carbocation and is favored by substrates that stabilize positive charge. SN2 is a one-step backside attack and is favored by less hindered substrates.\n\nWhen solving a question, check substrate structure first, then nucleophile strength, solvent and leaving group.", 1),
            ("12", "Alcohols, Phenols & Ethers", "Alcohols, Phenols & Ethers", "concept", "Acidity, preparation and high-yield reaction pathways.", "Focus on acidity of phenols, reactions of alcohols, dehydration, oxidation, Williamson ether synthesis and important distinctions used in board and entrance questions.", 0),
            ("12", "Aldehydes, Ketones & Carboxylic Acids", "Carbonyl Chemistry", "concept", "Master nucleophilic addition and the characteristic reactions of carbonyl compounds.", "The carbonyl carbon is electrophilic because oxygen withdraws electron density. Use this fact to understand nucleophilic addition, oxidation/reduction and common named transformations instead of memorizing isolated equations.", 1),
            ("12", "Amines", "Amines and Diazonium Salts", "concept", "Basicity trends, preparations and diazonium chemistry.", "Compare basicity using electron availability on nitrogen, resonance and solvation. Diazonium salts are especially useful because they connect aromatic amines to many substitution products and azo dyes.", 0),
            ("All", "Updates", "Welcome to the learning portal", "announcement", "Your teacher can publish class updates here instantly.", "This portal is designed so new lessons, notes, announcements and videos become visible to students as soon as the teacher publishes them.", 1),
        ]
        for level, chapter, title, kind, summary, body, featured in samples:
            conn.execute(
                """INSERT INTO content(class_level, chapter, title, slug, content_type, summary, body, published, featured, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (level, chapter, title, unique_slug(conn, title), kind, summary, body, 1, featured, now, now),
            )
    conn.commit()
    conn.close()


def get_settings() -> dict[str, str]:
    conn = db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


def sign_session(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def read_session(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME)
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:
        return None
    if data.get("exp", 0) < int(time.time()):
        return None
    return data


def require_admin(request: Request, csrf: Optional[str] = None) -> dict:
    session = read_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Admin login required")
    if csrf is not None and not secrets.compare_digest(str(csrf), str(session.get("csrf", ""))):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return session


async def broadcast_update() -> None:
    global content_version
    async with version_condition:
        content_version += 1
        version_condition.notify_all()


async def save_upload(upload: Optional[UploadFile]) -> str:
    if not upload or not upload.filename:
        return ""
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {suffix or 'unknown'} is not allowed")
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(upload.filename).stem).strip("-")[:70] or "file"
    filename = f"{int(time.time())}-{secrets.token_hex(4)}-{safe_stem}{suffix}"
    path = UPLOAD_DIR / filename
    total = 0
    try:
        with path.open("wb") as f:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload is larger than 500 MB")
                f.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return f"/static/uploads/{filename}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Organic Chemistry Academy", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

def nl2br(text: str) -> str:
    import html
    return html.escape(text).replace("\n", "<br>")

templates.env.filters["nl2br"] = nl2br


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = db()
    featured = conn.execute(
        "SELECT * FROM content WHERE published=1 AND content_type!='announcement' ORDER BY featured DESC, updated_at DESC LIMIT 6"
    ).fetchall()
    announcements = conn.execute(
        "SELECT * FROM content WHERE published=1 AND content_type='announcement' ORDER BY updated_at DESC LIMIT 3"
    ).fetchall()
    conn.close()
    return templates.TemplateResponse("home.html", {"request": request, "settings": get_settings(), "featured": featured, "announcements": announcements})


@app.get("/class/{level}", response_class=HTMLResponse)
def class_page(request: Request, level: str):
    if level not in {"11", "12"}:
        raise HTTPException(status_code=404)
    conn = db()
    items = conn.execute(
        "SELECT * FROM content WHERE published=1 AND class_level=? AND content_type!='announcement' ORDER BY chapter COLLATE NOCASE, updated_at DESC",
        (level,),
    ).fetchall()
    conn.close()
    chapters: dict[str, list] = {}
    for item in items:
        chapters.setdefault(item["chapter"] or "Other", []).append(item)
    return templates.TemplateResponse("class.html", {"request": request, "settings": get_settings(), "level": level, "chapters": chapters})


@app.get("/lesson/{slug}", response_class=HTMLResponse)
def lesson(request: Request, slug: str):
    conn = db()
    item = conn.execute("SELECT * FROM content WHERE slug=? AND published=1", (slug,)).fetchone()
    conn.close()
    if not item:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("lesson.html", {"request": request, "settings": get_settings(), "item": item})


@app.get("/videos", response_class=HTMLResponse)
def videos(request: Request):
    conn = db()
    items = conn.execute("SELECT * FROM content WHERE published=1 AND content_type='video' ORDER BY updated_at DESC").fetchall()
    conn.close()
    return templates.TemplateResponse("listing.html", {"request": request, "settings": get_settings(), "title": "Video Library", "subtitle": "Teacher-led lessons and reaction walkthroughs.", "items": items})


@app.get("/resources", response_class=HTMLResponse)
def resources(request: Request):
    conn = db()
    items = conn.execute("SELECT * FROM content WHERE published=1 AND content_type IN ('note','resource') ORDER BY updated_at DESC").fetchall()
    conn.close()
    return templates.TemplateResponse("listing.html", {"request": request, "settings": get_settings(), "title": "Notes & Resources", "subtitle": "Revision notes, PDFs, worksheets and exam-focused material.", "items": items})


@app.get("/announcements", response_class=HTMLResponse)
def announcements(request: Request):
    conn = db()
    items = conn.execute("SELECT * FROM content WHERE published=1 AND content_type='announcement' ORDER BY updated_at DESC").fetchall()
    conn.close()
    return templates.TemplateResponse("listing.html", {"request": request, "settings": get_settings(), "title": "Announcements", "subtitle": "The latest updates from your teacher.", "items": items})


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request, "settings": get_settings()})


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = ""):
    q = q.strip()
    items = []
    if q:
        conn = db()
        like = f"%{q}%"
        items = conn.execute(
            """SELECT * FROM content WHERE published=1 AND content_type!='announcement'
               AND (title LIKE ? OR chapter LIKE ? OR summary LIKE ? OR body LIKE ?)
               ORDER BY updated_at DESC LIMIT 50""",
            (like, like, like, like),
        ).fetchall()
        conn.close()
    return templates.TemplateResponse("listing.html", {"request": request, "settings": get_settings(), "title": f"Search results for “{q}”" if q else "Search", "subtitle": "Search concepts, chapters, notes and lessons.", "items": items, "search_query": q})


@app.get("/events")
async def events(request: Request):
    async def event_stream():
        last_seen = content_version
        yield f"data: {last_seen}\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                async with version_condition:
                    await asyncio.wait_for(version_condition.wait_for(lambda: content_version != last_seen), timeout=20)
                    last_seen = content_version
                    yield f"data: {last_seen}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if read_session(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("admin_login.html", {"request": request, "settings": get_settings(), "error": ""})


@app.post("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    valid_user = secrets.compare_digest(username, ADMIN_USERNAME)
    valid_pass = secrets.compare_digest(password, ADMIN_PASSWORD)
    if not (valid_user and valid_pass):
        return templates.TemplateResponse("admin_login.html", {"request": request, "settings": get_settings(), "error": "Incorrect username or password."}, status_code=401)
    csrf = secrets.token_urlsafe(24)
    token = sign_session({"exp": int(time.time()) + 12 * 3600, "csrf": csrf})
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=False, samesite="strict", max_age=12 * 3600)
    return response


@app.get("/admin/logout")
def admin_logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    session = require_admin(request)
    conn = db()
    items = conn.execute("SELECT * FROM content ORDER BY updated_at DESC").fetchall()
    conn.close()
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "settings": get_settings(), "items": items, "csrf": session["csrf"]})


@app.post("/admin/content/create")
async def create_content(
    request: Request,
    csrf: str = Form(...),
    class_level: str = Form("11"),
    chapter: str = Form(""),
    title: str = Form(...),
    content_type: str = Form("concept"),
    summary: str = Form(""),
    body: str = Form(""),
    video_url: str = Form(""),
    published: Optional[str] = Form(None),
    featured: Optional[str] = Form(None),
    upload: Optional[UploadFile] = File(None),
):
    require_admin(request, csrf)
    if class_level not in {"11", "12", "All"}:
        class_level = "All"
    if content_type not in {"concept", "video", "note", "resource", "announcement"}:
        content_type = "concept"
    upload_path = await save_upload(upload)
    now = utc_now()
    conn = db()
    slug = unique_slug(conn, title)
    conn.execute(
        """INSERT INTO content(class_level, chapter, title, slug, content_type, summary, body, video_url, upload_path, published, featured, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (class_level, chapter.strip(), title.strip(), slug, content_type, summary.strip(), body.strip(), video_url.strip(), upload_path, 1 if published else 0, 1 if featured else 0, now, now),
    )
    conn.commit()
    conn.close()
    await broadcast_update()
    return RedirectResponse("/admin?status=created", status_code=303)


@app.post("/admin/content/{item_id}/update")
async def update_content(
    request: Request,
    item_id: int,
    csrf: str = Form(...),
    class_level: str = Form("11"),
    chapter: str = Form(""),
    title: str = Form(...),
    content_type: str = Form("concept"),
    summary: str = Form(""),
    body: str = Form(""),
    video_url: str = Form(""),
    published: Optional[str] = Form(None),
    featured: Optional[str] = Form(None),
    upload: Optional[UploadFile] = File(None),
):
    require_admin(request, csrf)
    conn = db()
    existing = conn.execute("SELECT * FROM content WHERE id=?", (item_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404)
    upload_path = existing["upload_path"]
    new_upload = await save_upload(upload)
    if new_upload:
        old_path = upload_path
        upload_path = new_upload
        if old_path.startswith("/static/uploads/"):
            (UPLOAD_DIR / Path(old_path).name).unlink(missing_ok=True)
    slug = unique_slug(conn, title, exclude_id=item_id)
    conn.execute(
        """UPDATE content SET class_level=?, chapter=?, title=?, slug=?, content_type=?, summary=?, body=?, video_url=?, upload_path=?, published=?, featured=?, updated_at=? WHERE id=?""",
        (class_level, chapter.strip(), title.strip(), slug, content_type, summary.strip(), body.strip(), video_url.strip(), upload_path, 1 if published else 0, 1 if featured else 0, utc_now(), item_id),
    )
    conn.commit()
    conn.close()
    await broadcast_update()
    return RedirectResponse("/admin?status=updated", status_code=303)


@app.post("/admin/content/{item_id}/delete")
async def delete_content(request: Request, item_id: int, csrf: str = Form(...)):
    require_admin(request, csrf)
    conn = db()
    existing = conn.execute("SELECT upload_path FROM content WHERE id=?", (item_id,)).fetchone()
    if existing:
        conn.execute("DELETE FROM content WHERE id=?", (item_id,))
        conn.commit()
        if existing["upload_path"].startswith("/static/uploads/"):
            (UPLOAD_DIR / Path(existing["upload_path"]).name).unlink(missing_ok=True)
    conn.close()
    await broadcast_update()
    return RedirectResponse("/admin?status=deleted", status_code=303)


@app.post("/admin/settings")
async def update_settings(
    request: Request,
    csrf: str = Form(...),
    site_name: str = Form(...),
    teacher_name: str = Form(...),
    hero_title: str = Form(...),
    hero_subtitle: str = Form(...),
    teacher_bio: str = Form(...),
):
    require_admin(request, csrf)
    values = {
        "site_name": site_name.strip(),
        "teacher_name": teacher_name.strip(),
        "hero_title": hero_title.strip(),
        "hero_subtitle": hero_subtitle.strip(),
        "teacher_bio": teacher_bio.strip(),
    }
    conn = db()
    for key, value in values.items():
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()
    await broadcast_update()
    return RedirectResponse("/admin?status=settings", status_code=303)
