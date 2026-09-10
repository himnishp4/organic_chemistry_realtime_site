from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine

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
IS_RENDER = os.getenv("RENDER", "").lower() in {"1", "true", "yes"}
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true" if IS_RENDER else "false").lower() in {"1", "true", "yes"}

# Render should receive the Supabase Session Pooler URI in DATABASE_URL.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "course-media")
USE_CLOUD_STORAGE = bool(SUPABASE_URL and SUPABASE_SECRET_KEY)

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp",
    ".mp4", ".webm", ".mov", ".doc", ".docx", ".ppt", ".pptx"
}
LOCAL_MAX_UPLOAD_BYTES = 500 * 1024 * 1024
# Supabase Free projects currently cap an individual file at 50 MB.
CLOUD_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

content_version = 1
version_condition = asyncio.Condition()

metadata = MetaData()
content_table = Table(
    "content",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("class_level", String(10), nullable=False, default="11"),
    Column("chapter", Text, nullable=False, default=""),
    Column("title", Text, nullable=False),
    Column("slug", String(255), nullable=False, unique=True),
    Column("content_type", String(30), nullable=False, default="concept"),
    Column("summary", Text, nullable=False, default=""),
    Column("body", Text, nullable=False, default=""),
    Column("video_url", Text, nullable=False, default=""),
    Column("upload_path", Text, nullable=False, default=""),
    Column("published", Integer, nullable=False, default=1),
    Column("featured", Integer, nullable=False, default=0),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
)
settings_table = Table(
    "settings",
    metadata,
    Column("key", String(100), primary_key=True),
    Column("value", Text, nullable=False),
)


def _build_engine() -> Engine:
    kwargs = {"pool_pre_ping": True}
    if DATABASE_URL.startswith("sqlite:"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(DATABASE_URL, **kwargs)


engine = _build_engine()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "lesson"


def unique_slug(conn: Connection, title: str, exclude_id: Optional[int] = None) -> str:
    base = slugify(title)
    candidate = base
    counter = 2
    while True:
        stmt = select(content_table.c.id).where(content_table.c.slug == candidate)
        if exclude_id is not None:
            stmt = stmt.where(content_table.c.id != exclude_id)
        if conn.execute(stmt).first() is None:
            return candidate
        candidate = f"{base}-{counter}"
        counter += 1


def init_db() -> None:
    metadata.create_all(engine)
    defaults = {
        "site_name": "Organic Chemistry Academy",
        "teacher_name": "Your Chemistry Teacher",
        "hero_title": "Organic Chemistry, made visual and memorable.",
        "hero_subtitle": "A focused Class 11 & 12 learning space for concepts, mechanisms, reactions, notes and teacher-led video lessons.",
        "teacher_bio": "Clear explanations, exam-focused practice and strong conceptual foundations for Class 11 and Class 12 Organic Chemistry.",
    }
    with engine.begin() as conn:
        for key, value in defaults.items():
            exists = conn.execute(select(settings_table.c.key).where(settings_table.c.key == key)).first()
            if exists is None:
                conn.execute(insert(settings_table).values(key=key, value=value))

        count = conn.execute(select(func.count()).select_from(content_table)).scalar_one()
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
                    insert(content_table).values(
                        class_level=level,
                        chapter=chapter,
                        title=title,
                        slug=unique_slug(conn, title),
                        content_type=kind,
                        summary=summary,
                        body=body,
                        video_url="",
                        upload_path="",
                        published=1,
                        featured=featured,
                        created_at=now,
                        updated_at=now,
                    )
                )


def get_settings() -> dict[str, str]:
    with engine.connect() as conn:
        rows = conn.execute(select(settings_table.c.key, settings_table.c.value)).mappings().all()
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


def _storage_object_from_public_url(url: str) -> Optional[str]:
    if not (USE_CLOUD_STORAGE and url):
        return None
    prefix = f"{SUPABASE_URL}/storage/v1/object/public/{quote(SUPABASE_STORAGE_BUCKET, safe='')}/"
    if not url.startswith(prefix):
        return None
    return unquote(url[len(prefix):])


async def _delete_cloud_upload(public_url: str) -> None:
    object_path = _storage_object_from_public_url(public_url)
    if not object_path:
        return
    endpoint = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_STORAGE_BUCKET, safe='')}"
    headers = {"apikey": SUPABASE_SECRET_KEY, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.request("DELETE", endpoint, headers=headers, json={"prefixes": [object_path]})
    except Exception:
        # Content deletion should still succeed even if remote cleanup has a transient failure.
        pass


async def save_upload(upload: Optional[UploadFile]) -> str:
    if not upload or not upload.filename:
        return ""
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        await upload.close()
        raise HTTPException(status_code=400, detail=f"File type {suffix or 'unknown'} is not allowed")

    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(upload.filename).stem).strip("-")[:70] or "file"
    filename = f"{int(time.time())}-{secrets.token_hex(4)}-{safe_stem}{suffix}"

    if USE_CLOUD_STORAGE:
        payload = await upload.read(CLOUD_MAX_UPLOAD_BYTES + 1)
        content_type = upload.content_type or "application/octet-stream"
        await upload.close()
        if len(payload) > CLOUD_MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="On the free cloud storage plan, each uploaded file must be 50 MB or smaller. For larger videos, use the Video link field.")
        object_path = f"teacher-uploads/{filename}"
        endpoint = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_STORAGE_BUCKET, safe='')}/{quote(object_path, safe='/')}"
        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Content-Type": content_type,
            "cache-control": "3600",
            "x-upsert": "false",
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(endpoint, content=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Could not reach Supabase Storage. Try the upload again.") from exc
        if response.status_code not in {200, 201}:
            raise HTTPException(status_code=502, detail="Supabase Storage rejected the upload. Confirm that the 'course-media' bucket exists, is public, and your SUPABASE_SECRET_KEY is correct.")
        return f"{SUPABASE_URL}/storage/v1/object/public/{quote(SUPABASE_STORAGE_BUCKET, safe='')}/{quote(object_path, safe='/')}"

    if IS_RENDER:
        await upload.close()
        raise HTTPException(status_code=503, detail="Persistent file storage is not configured. Add SUPABASE_URL and SUPABASE_SECRET_KEY on Render before using direct uploads.")

    path = UPLOAD_DIR / filename
    total = 0
    try:
        with path.open("wb") as f:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > LOCAL_MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload is larger than 500 MB")
                f.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return f"/static/uploads/{filename}"


async def delete_upload(upload_path: str) -> None:
    if not upload_path:
        return
    if upload_path.startswith("/static/uploads/"):
        (UPLOAD_DIR / Path(upload_path).name).unlink(missing_ok=True)
    else:
        await _delete_cloud_upload(upload_path)


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
    with engine.connect() as conn:
        featured = conn.execute(
            select(content_table)
            .where(and_(content_table.c.published == 1, content_table.c.content_type != "announcement"))
            .order_by(content_table.c.featured.desc(), content_table.c.updated_at.desc())
            .limit(6)
        ).mappings().all()
        announcements = conn.execute(
            select(content_table)
            .where(and_(content_table.c.published == 1, content_table.c.content_type == "announcement"))
            .order_by(content_table.c.updated_at.desc())
            .limit(3)
        ).mappings().all()
    return templates.TemplateResponse("home.html", {"request": request, "settings": get_settings(), "featured": featured, "announcements": announcements})


@app.get("/class/{level}", response_class=HTMLResponse)
def class_page(request: Request, level: str):
    if level not in {"11", "12"}:
        raise HTTPException(status_code=404)
    with engine.connect() as conn:
        items = conn.execute(
            select(content_table)
            .where(and_(content_table.c.published == 1, content_table.c.class_level == level, content_table.c.content_type != "announcement"))
            .order_by(func.lower(content_table.c.chapter), content_table.c.updated_at.desc())
        ).mappings().all()
    chapters: dict[str, list] = {}
    for item in items:
        chapters.setdefault(item["chapter"] or "Other", []).append(item)
    return templates.TemplateResponse("class.html", {"request": request, "settings": get_settings(), "level": level, "chapters": chapters})


@app.get("/lesson/{slug}", response_class=HTMLResponse)
def lesson(request: Request, slug: str):
    with engine.connect() as conn:
        item = conn.execute(
            select(content_table).where(and_(content_table.c.slug == slug, content_table.c.published == 1))
        ).mappings().first()
    if not item:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("lesson.html", {"request": request, "settings": get_settings(), "item": item})


@app.get("/videos", response_class=HTMLResponse)
def videos(request: Request):
    with engine.connect() as conn:
        items = conn.execute(
            select(content_table)
            .where(and_(content_table.c.published == 1, content_table.c.content_type == "video"))
            .order_by(content_table.c.updated_at.desc())
        ).mappings().all()
    return templates.TemplateResponse("listing.html", {"request": request, "settings": get_settings(), "title": "Video Library", "subtitle": "Teacher-led lessons and reaction walkthroughs.", "items": items})


@app.get("/resources", response_class=HTMLResponse)
def resources(request: Request):
    with engine.connect() as conn:
        items = conn.execute(
            select(content_table)
            .where(and_(content_table.c.published == 1, content_table.c.content_type.in_(["note", "resource"])))
            .order_by(content_table.c.updated_at.desc())
        ).mappings().all()
    return templates.TemplateResponse("listing.html", {"request": request, "settings": get_settings(), "title": "Notes & Resources", "subtitle": "Revision notes, PDFs, worksheets and exam-focused material.", "items": items})


@app.get("/announcements", response_class=HTMLResponse)
def announcements(request: Request):
    with engine.connect() as conn:
        items = conn.execute(
            select(content_table)
            .where(and_(content_table.c.published == 1, content_table.c.content_type == "announcement"))
            .order_by(content_table.c.updated_at.desc())
        ).mappings().all()
    return templates.TemplateResponse("listing.html", {"request": request, "settings": get_settings(), "title": "Announcements", "subtitle": "The latest updates from your teacher.", "items": items})


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request, "settings": get_settings()})


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = ""):
    q = q.strip()
    items = []
    if q:
        pattern = f"%{q}%"
        with engine.connect() as conn:
            items = conn.execute(
                select(content_table)
                .where(
                    and_(
                        content_table.c.published == 1,
                        content_table.c.content_type != "announcement",
                        or_(
                            content_table.c.title.ilike(pattern),
                            content_table.c.chapter.ilike(pattern),
                            content_table.c.summary.ilike(pattern),
                            content_table.c.body.ilike(pattern),
                        ),
                    )
                )
                .order_by(content_table.c.updated_at.desc())
                .limit(50)
            ).mappings().all()
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
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=COOKIE_SECURE, samesite="strict", max_age=12 * 3600)
    return response


@app.get("/admin/logout")
def admin_logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    session = require_admin(request)
    with engine.connect() as conn:
        items = conn.execute(select(content_table).order_by(content_table.c.updated_at.desc())).mappings().all()
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
    with engine.begin() as conn:
        slug = unique_slug(conn, title)
        conn.execute(
            insert(content_table).values(
                class_level=class_level,
                chapter=chapter.strip(),
                title=title.strip(),
                slug=slug,
                content_type=content_type,
                summary=summary.strip(),
                body=body.strip(),
                video_url=video_url.strip(),
                upload_path=upload_path,
                published=1 if published else 0,
                featured=1 if featured else 0,
                created_at=now,
                updated_at=now,
            )
        )
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
    if class_level not in {"11", "12", "All"}:
        class_level = "All"
    if content_type not in {"concept", "video", "note", "resource", "announcement"}:
        content_type = "concept"

    with engine.connect() as conn:
        existing = conn.execute(select(content_table).where(content_table.c.id == item_id)).mappings().first()
    if not existing:
        raise HTTPException(status_code=404)

    old_upload_path = existing["upload_path"] or ""
    new_upload = await save_upload(upload)
    upload_path = new_upload or old_upload_path

    with engine.begin() as conn:
        slug = unique_slug(conn, title, exclude_id=item_id)
        conn.execute(
            update(content_table)
            .where(content_table.c.id == item_id)
            .values(
                class_level=class_level,
                chapter=chapter.strip(),
                title=title.strip(),
                slug=slug,
                content_type=content_type,
                summary=summary.strip(),
                body=body.strip(),
                video_url=video_url.strip(),
                upload_path=upload_path,
                published=1 if published else 0,
                featured=1 if featured else 0,
                updated_at=utc_now(),
            )
        )

    if new_upload and old_upload_path:
        await delete_upload(old_upload_path)
    await broadcast_update()
    return RedirectResponse("/admin?status=updated", status_code=303)


@app.post("/admin/content/{item_id}/delete")
async def delete_content(request: Request, item_id: int, csrf: str = Form(...)):
    require_admin(request, csrf)
    with engine.begin() as conn:
        existing = conn.execute(select(content_table.c.upload_path).where(content_table.c.id == item_id)).mappings().first()
        if existing:
            conn.execute(delete(content_table).where(content_table.c.id == item_id))
    if existing and existing["upload_path"]:
        await delete_upload(existing["upload_path"])
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
    with engine.begin() as conn:
        for key, value in values.items():
            exists = conn.execute(select(settings_table.c.key).where(settings_table.c.key == key)).first()
            if exists:
                conn.execute(update(settings_table).where(settings_table.c.key == key).values(value=value))
            else:
                conn.execute(insert(settings_table).values(key=key, value=value))
    await broadcast_update()
    return RedirectResponse("/admin?status=settings", status_code=303)
