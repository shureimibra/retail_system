# Deploying Retail OS on a VPS (Netcup)

For whoever puts Retail OS on a server: the owner, or a developer they hire. Written for one Ubuntu VPS, such as the owner's Netcup server. Status: **a plan**. Nothing here has been run on the server yet. Section 9 lists the small code changes to make on the day.

## 1. Why a VPS, and not Vercel

Retail OS is a Django app with parts that must run all the time:
- **A background worker** (Celery) sends WhatsApp, SMS and email, and retries failed ones.
- **A scheduler** (Celery beat) runs follow-ups, expiry and lapsed holds every 15 minutes.
- **A database** (PostgreSQL) and **Redis** for the worker's queue.
- **Webhooks:** Twilio, Meta and Safaricom call the site back at any time and expect a quick answer.
- **Uploaded photos and logos** stored on disk.

Vercel and similar "serverless" hosts run code only for the length of one request, and have no always-on worker, scheduler or disk. Retail OS would lose messages and reminders there. A VPS runs all the parts on one machine, at a fixed monthly price.

Netcup's servers are in Europe (Germany and Austria), which is fine for speed from Kenya. Customer phone numbers would then be stored outside Kenya. **Before taking real customers, check the Kenya Data Protection Act's rules on storing personal data abroad** with someone who knows them; a Kenyan or African host is the alternative if needed.

## 2. What the server needs

| Part | Choice | Notes |
|---|---|---|
| OS | Ubuntu 24.04 LTS | Netcup offers it as an image |
| Size | 2 vCPU, 4 GB RAM, 40 GB+ disk is plenty to start | One shop or many: the app is light |
| Web | Nginx in front, Gunicorn running Django | Nginx serves `/static/` and `/media/` itself |
| Database | PostgreSQL 16 | On the same server |
| Queue | Redis | On the same server, not open to the internet |
| Worker and scheduler | Celery worker + Celery beat | Run as services, restart on failure |
| HTTPS | Let's Encrypt (certbot), free | Required: webhooks and the offline app need https |
| Domain | e.g. `app.yourbrand.co.ke` | An A record pointing to the VPS's IP |

## 3. Before you start

- [ ] A domain, with an **A record** for the app's address pointing to the VPS IP.
- [ ] SSH access to the VPS with a **key**, not a password.
- [ ] The repository URL, and access to it from the server (a deploy key on GitHub).
- [ ] The production `.env` values (section 6), kept in a password manager, never in Git.

## 4. Set up the server, once

```bash
# As root on a fresh server: a normal user, updates, firewall
adduser retail && usermod -aG sudo retail
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv python3-pip git nginx postgresql redis-server certbot python3-certbot-nginx ufw fail2ban
ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw enable
# Then: SSH keys only, no root login (in /etc/ssh/sshd_config: PasswordAuthentication no, PermitRootLogin no)
```

```bash
# Database
sudo -u postgres createuser retail --pwprompt
sudo -u postgres createdb retail_system --owner retail
```

Redis listens only on 127.0.0.1 by default on Ubuntu; keep it that way. If the Python 3.11 packages aren't in the Ubuntu 24.04 repositories, use the "deadsnakes" PPA, or check the app on Ubuntu's own Python 3.12 first; the code has only been tested on 3.11.

## 5. Install the app

```bash
sudo mkdir -p /srv/retail && sudo chown retail: /srv/retail
cd /srv/retail
git clone <repository> app && cd app
python3.11 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env        # fill in section 6
python manage.py migrate
python manage.py collectstatic --no-input
python manage.py createsuperuser          # platform operator account, for /ops/
```

## 6. The production `.env`

| Key | Value |
|---|---|
| `DEBUG` | `False` |
| `SECRET_KEY` | A new long random value: `python -c "import secrets; print(secrets.token_urlsafe(50))"`. Never reuse the development one |
| `ALLOWED_HOSTS` | `app.yourbrand.co.ke` |
| `SITE_URL` | `https://app.yourbrand.co.ke` (this also sets the trusted origin for forms) |
| `DATABASE_URL` | `postgresql://retail:<password>@localhost:5432/retail_system` |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://127.0.0.1:6379/0` |
| `ADMIN_URL` | Something not guessable, e.g. `ops-7f3k/` |
| `SIMULATOR_ENABLED` | `False` |
| Messaging and M-Pesa keys | See `docs/going-live-messaging.md` |

The `.env` file should be readable only by the app user: `chmod 600 .env`.

## 7. Services

Three systemd services, each restarting on failure. Example for the web app (`/etc/systemd/system/retail-web.service`):

```ini
[Unit]
Description=Retail OS web
After=network.target postgresql.service redis-server.service

[Service]
User=retail
WorkingDirectory=/srv/retail/app
ExecStart=/srv/retail/app/venv/bin/gunicorn core.wsgi --bind 127.0.0.1:8000 --workers 3 --timeout 60
Restart=always

[Install]
WantedBy=multi-user.target
```

The worker and the scheduler are the same, with:
- `retail-worker`: `ExecStart=/srv/retail/app/venv/bin/celery -A core worker --loglevel=info`
- `retail-beat`: `ExecStart=/srv/retail/app/venv/bin/celery -A core beat --loglevel=info`

Run **exactly one** beat service, or reminders go out twice. Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now retail-web retail-worker retail-beat
```

## 8. Nginx and HTTPS

`/etc/nginx/sites-available/retail`:

```nginx
server {
    server_name app.yourbrand.co.ke;
    client_max_body_size 10M;               # photo, logo and stock-file uploads

    location /static/ { alias /srv/retail/app/staticfiles/; expires 30d; }
    location /media/  { alias /srv/retail/app/media/; }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/retail /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d app.yourbrand.co.ke     # free certificate, renews itself
```

`/sw.js` (the offline helper) must be served by Django, not Nginx. It is, since only `/static/` and `/media/` are handled by Nginx.

## 9. Code changes to make on deployment day

Small, and kept out of the code until now so local testing over plain http keeps working:
- [ ] **Behind Nginx's https:** `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`.
- [ ] **Secure cookies when the site is https:** `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and HSTS (`SECURE_HSTS_SECONDS`, starting low, e.g. one hour, then a year once all is well). Switch them on from a `.env` value such as `SECURE_SITE=True`.
- [ ] **Logging** to a file or journald that keeps errors, without customer messages in plain text.
- [ ] Run `python manage.py check --deploy` and clear what it reports.
- [ ] **Remove the legacy root `services/` package** if it's still there (see CLAUDE.md).

## 10. After it's up

- **Point the providers at the server:**
  - the Twilio and Meta webhooks: `https://app.yourbrand.co.ke/notifications/webhook/` and `/notifications/webhooks/whatsapp/`;
  - the Daraja callback (built from `SITE_URL`).
  
  No more tunnel.
- **Smoke test:**
  - sign in, log a missed sale, receive stock;
  - see the WhatsApp arrive, reply, and see the reply arrive;
  - wait 15 minutes and check that the scheduler ran: `journalctl -u retail-beat`.

## 11. Backups and updates

- **Database:** a nightly `pg_dump` to a file, kept 14 days, **copied off the server** (another provider's storage, or Netcup's snapshot feature as a second layer).
- **Photos:** back up `/srv/retail/app/media/` with the database.
- **Test a restore** once, before relying on it.
- **Updating the app:**

```bash
cd /srv/retail/app && git pull && . venv/bin/activate
pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --no-input
sudo systemctl restart retail-web retail-worker retail-beat
```

- Security updates: `sudo apt update && sudo apt upgrade` monthly, or turn on `unattended-upgrades`.
- **Uptime:** a free uptime checker (e.g. UptimeRobot) on `https://app.yourbrand.co.ke/api/health/`.

## 12. Later, when there are many shops

One VPS is enough for a good while. Signs it's time to grow: slow pages at busy times, or the worker falling behind. The usual next steps are, in order:
1. a bigger VPS;
2. the database on its own server;
3. photos on object storage.

None needs a code rewrite.
