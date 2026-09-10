# Organic Chemistry Academy — Public Live Teacher-Managed Website

A Class 11 & 12 organic chemistry learning portal with a teacher dashboard and live student updates.

## Production architecture

- FastAPI application on Render
- Supabase PostgreSQL through `DATABASE_URL` for persistent lessons/settings
- Supabase Storage bucket (`course-media`) for persistent teacher files
- Server-Sent Events (SSE) so open student pages refresh after teacher changes

The app still falls back to local SQLite and local uploads when run on a laptop without cloud environment variables.

## Render environment variables

Set these in Render, not in GitHub:

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `SITE_SECRET_KEY`
- `DATABASE_URL` — Supabase Session Pooler URI; URL-encode special characters in the password
- `SUPABASE_URL` — project URL such as `https://project-ref.supabase.co`
- `SUPABASE_SECRET_KEY` — server-only Supabase secret key (`sb_secret_...`); never commit or expose it
- `SUPABASE_STORAGE_BUCKET=course-media`

## Supabase Storage

Create a bucket named `course-media` and make it public so students can view teacher attachments. Uploads are performed only by the protected server-side teacher dashboard using the secret key.

On Supabase Free, an individual file is limited to 50 MB. For a larger teaching video, use the dashboard's `Video link` field instead.

## Local run

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Without `DATABASE_URL`, local development uses `app/data/site.db` automatically.
