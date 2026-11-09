# Deploying for testers (Render + Neon)

```
Tester's browser ──https──► Render (runs the app container) ──TLS──► Neon (Postgres)
                                      ▲
                     GitHub repo (Render rebuilds on every push to main)
```

- **Render** runs the Docker image built from this repo (see `Dockerfile` and `render.yaml`).
- **Neon** stores the data. Render's free disk is wiped on every restart, so the database can't live there.
- **Cost:** both have free plans that are enough for a small beta.

## 1. Neon: create the database
1. Go to <https://console.neon.tech>, then **New project**.
   - Name: `statement-whisperer`
   - Region: **AWS Asia Pacific (Singapore)**, the same region as the Render service
   - Postgres version: the default
2. Open **Connect** and copy the connection string. It looks like `postgresql://USER:PASSWORD@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`.
   - **This is a password. Don't paste it in chats, commit it, or share it.** If it leaks, reset the role's password in Neon.
3. *(Optional, recommended)* Create a second, empty database to test against: **Databases → New database → `ledger_test`**. Its URL is the same string with `/ledger_test` in place of `/neondb`.

## 2. *(Optional)* Test against Postgres before deploying
Add a line to your local `.env`, which git never commits, pointing at the **empty test database**:
```
TEST_POSTGRES_URL=postgresql://USER:PASSWORD@ep-xxxx.../ledger_test?sslmode=require
```
Then run:
```powershell
.\scripts\dev.ps1 test tests/test_postgres.py -rs
```
- **What it does:** migrates the database, checks the schema, signs up two users, imports a statement, checks the dashboard and isolation, then removes every table again.
- **Safety:** it refuses to run against a database that already has tables.

## 3. Render: create the service
1. Go to <https://dashboard.render.com> and choose **New → Blueprint**.
2. Connect GitHub and pick **Aditya-MC/statement-whisperer**. Render reads `render.yaml`.
3. It asks for the two secret values:
   - `DATABASE_URL`: the Neon string from step 1.2. This is the **main** database (`neondb`), not `ledger_test`.
   - `ADMIN_EMAIL`: your own email. Only this address can create the first account.
4. Click **Apply**. The first build takes about 5–10 minutes. In **Logs** you should see:
   - `Running upgrade ... -> 0006, multi-user ...` (the database tables being created)
   - `Uvicorn running on http://0.0.0.0:...`
5. Open the service URL (`https://statement-whisperer-xxxx.onrender.com`) and sign up with **ADMIN_EMAIL**. You're the admin.

Already set by `render.yaml`:

| Variable | Value | Why |
|---|---|---|
| `COOKIE_SECURE` | `true` | the session cookie is only sent over HTTPS |
| `LLM_PROVIDER` | `none` | no AI for testers, so no API key or cost |
| `DEMO_MODE` | `false` | real accounts |

## 4. Invite testers
1. Click your email in the header to open **Account → Invite testers**, then **Create invite**. The code is copied to your clipboard.
2. Send the tester the site URL and their code. Each code works once.
3. Tell them how privacy works. The **Privacy** link is on the sign-in screen: their data is private within the app, but you, as the operator, could technically read the database. Suggest they try a sample statement first.

## Updating
Every `git push` to `main` makes Render rebuild and redeploy automatically. Migrations run on start-up, so the database schema updates itself. Before pushing a new migration, test it on a copy of the data or with `test_postgres.py`.

## Free-plan behaviour
- **Render free sleeps after about 15 minutes idle.** The next visit waits roughly 30–60 seconds, then it's fast. The paid "Starter" plan stays awake.
- **Neon free** has 0.5 GB of storage and suspends the database when idle. The app reconnects automatically (`pool_pre_ping`).
- **Rate limits are in memory** (10 login or sign-up attempts per 15 minutes per IP, 60 uploads per hour per user). They reset when the service restarts.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| Build fails at `npm ci` | `frontend/package-lock.json` out of date. Run `npm install` locally and commit. |
| Logs: `password authentication failed` | wrong `DATABASE_URL`. Copy it again from Neon. |
| "This app isn't open for sign-ups yet" | you signed up with a different email than `ADMIN_EMAIL` |
| Every request returns 401 after signing in | `COOKIE_SECURE=true` but you're on plain `http://`. Use the `https://` Render URL. |
