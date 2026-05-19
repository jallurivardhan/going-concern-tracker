# Deployment Guide

## Architecture

- **Frontend**: Vercel (Next.js)
- **Backend API**: Render (FastAPI)
- **Database**: Neon (Serverless PostgreSQL)
- **Scheduling**: GitHub Actions (free tier)

## Deployment URLs

| Service | URL |
|---|---|
| Frontend | https://going-concern-tracker.vercel.app *(placeholder — update after deploy)* |
| Backend API | https://going-concern-tracker-api.onrender.com *(placeholder — update after deploy)* |
| API docs | https://going-concern-tracker-api.onrender.com/api/docs |

## Deploy Frontend (Vercel)

1. Go to [vercel.com](https://vercel.com) and import the GitHub repository
2. Set **Root Directory** to `apps/web`
3. Add environment variable:
   - `NEXT_PUBLIC_API_BASE_URL` = `https://going-concern-tracker-api.onrender.com/api`
4. Deploy — Vercel auto-detects Next.js and uses `vercel.json`

After the first deploy, copy the Vercel URL and update:
- `apps/api/src/gct/main.py` CORS `_allowed_origins` list
- `FRONTEND_URL` secret in Render dashboard

## Deploy Backend (Render)

1. Go to [render.com](https://render.com) and create a new Web Service
2. Connect the GitHub repository
3. Render reads `render.yaml` for build/start commands automatically
4. Set these environment variables in the Render dashboard:

| Key | Where to get it |
|---|---|
| `DATABASE_URL` | Neon dashboard → Connection string |
| `ANTHROPIC_API_KEY` | Anthropic console |
| `LANGFUSE_PUBLIC_KEY` | Langfuse project settings |
| `LANGFUSE_SECRET_KEY` | Langfuse project settings |
| `LANGFUSE_HOST` | Langfuse project settings |
| `SEC_USER_AGENT_EMAIL` | Your email address |
| `FRONTEND_URL` | Vercel deployment URL |

5. Deploy and wait for the health check at `/api/health` to pass

### Render free-tier cold-start

The Render free tier spins down services after 15 minutes of inactivity. The first request after spin-down may take **30–60 seconds** to respond. This is expected. If you need always-on availability, upgrade to the Starter plan ($7/month).

Mitigation: The Next.js frontend uses `cache: "no-store"` for API calls, so users see loading states during cold starts rather than stale data.

## GitHub Actions Secrets

Configure these in **Settings → Secrets and variables → Actions** for the continuous ingestion pipeline:

| Secret | Value |
|---|---|
| `DATABASE_URL` | Same as Render |
| `ANTHROPIC_API_KEY` | Same as Render |
| `LANGFUSE_PUBLIC_KEY` | Same as Render |
| `LANGFUSE_SECRET_KEY` | Same as Render |
| `LANGFUSE_HOST` | Same as Render |
| `SEC_USER_AGENT_EMAIL` | Same as Render |

## First-Deploy Checklist

- [ ] Neon database provisioned, `DATABASE_URL` obtained
- [ ] `alembic upgrade head` run against Neon (from local or Render shell)
- [ ] Render service deployed, health check passing
- [ ] Vercel frontend deployed, `NEXT_PUBLIC_API_BASE_URL` set correctly
- [ ] CORS updated in `main.py` with actual Vercel URL and redeployed
- [ ] GitHub Actions secrets configured
- [ ] Manually trigger the Actions workflow once to confirm end-to-end pipeline
- [ ] Visit the live site and verify the footer shows "Last refreshed X ago"

## Updating the Watchlist Post-Deployment

```bash
# Add new CIK to watchlist
echo "  - cik: \"0001234567\"\n    note: \"Company Name\"" >> apps/api/data/watchlist.yaml

# Commit and push — the next scheduled run picks it up
git add apps/api/data/watchlist.yaml
git commit -m "Add Company Name to watchlist"
git push
```

Or trigger a manual run immediately: Actions tab → "Refresh going-concern data" → "Run workflow".
