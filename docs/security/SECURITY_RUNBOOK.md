# Security Runbook — Operations, Deployment, Rollback

**Document type:** Runbook · **Version:** 1.1

Values in `<ANGLE_BRACKETS>` must be discovered on the real deployment; they were not present in
the repository. Never paste secrets into tickets, chat, or this document.

## 0. Placeholders to fill in (deployment facts)

| Placeholder | Meaning | How to discover |
|---|---|---|
| `<FRONTEND_DOMAIN>` | Cloudflare Pages domain | Cloudflare dashboard → Pages |
| `<API_DOMAIN>` | Public API hostname | Cloudflare DNS records |
| `<ORIGIN_IP>` | Oracle VM public IP | OCI console → instance |
| `<OCI_REGION>`, `<OCI_VM_SHAPE>` | Region and shape | OCI console |
| `<OCI_VM_OS>` | OS and version | `cat /etc/os-release` |
| `<ADMIN_SSH_PORT>` | SSH port | `sshd -T` on the VM |
| `<ADMIN_IP>` | Your administrative source IP | `curl ifconfig.me` from admin host |
| `<SSH_USER>` | Admin login user | existing access path |

## 1. Required production environment (root `.env` next to compose file)

Copy `.env.prod.example` → `.env`, fill every `CHANGE_ME`, then `chmod 600 .env`.

| Variable | Rule |
|---|---|
| `SECRET_KEY` | ≥ 32 random bytes hex (`python -c "import secrets; print(secrets.token_hex(32))"`); rotating it invalidates all JWTs |
| `POSTGRES_PASSWORD` | Long random; changing it after first boot requires `ALTER USER` inside the DB (volume keeps the old one) |
| `CORS_ORIGINS` | Exact `https://…` frontend origins, comma-separated, never `*` |
| `ALLOWED_HOSTS` | Optional; set to `<API_DOMAIN>` to enforce Host header once DNS is stable |
| `HSTS_ENABLED` | `false` until §5 verification is complete |

Compose **refuses to start** when any required variable is missing — that is intentional.

## 2. Host baseline (Ubuntu example; adapt to `<OCI_VM_OS>`)

```bash
sudo apt update && sudo apt -y upgrade            # then enable unattended security updates
sudo dpkg-reconfigure --priority=low unattended-upgrades
sudo timedatectl set-ntp true
sudo apt -y install ufw fail2ban
```

Enable `unattended-upgrades` only for the security pocket; schedule reboots in a window you can
monitor. `fail2ban` protects SSH (jail `sshd` default).

## 3. Origin protection (Cloudflare → OCI)

1. Cloudflare DNS: `<API_DOMAIN>` proxied (orange cloud); SSL mode **Full (strict)** once an
   origin certificate exists, otherwise **Full** with a Cloudflare Origin CA certificate on
   nginx (see §5).
2. OCI: add NSG/security-list ingress **only** from Cloudflare ranges
   (`https://www.cloudflare.com/ips-v4`, `ips-v6`) to ports 80/443; SSH only from `<ADMIN_IP>`
   to `<ADMIN_SSH_PORT>`; **no rule** for 5432 or 8000.
3. UFW (host level, mirrors NSG):

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from <ADMIN_IP> to any port <ADMIN_SSH_PORT> proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable          # keep the SSH session open until you verify a second login!
```

   Recovery: OCI serial console is the break-glass path if SSH locks out.

4. Verify: NET-004 from an external host — direct `<ORIGIN_IP>:80` should now be refused.
5. Optional hardening: Cloudflare **Authenticated Origin Pulls** (mutual TLS) — requires nginx
   `ssl_verify_client on` with the Cloudflare CA; do not enable without a maintenance window.

## 4. SSH hardening (after confirming key-based login works)

`/etc/ssh/sshd_config.d/99-hardening.conf`:

```
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
MaxAuthTries 4
```

`sudo sshd -t && sudo systemctl reload ssh`. Keep one root-capable session open while verifying.

## 5. HTTPS and HSTS enablement

1. Confirm `https://<API_DOMAIN>/health` works and `http://` redirects (Cloudflare "Always Use
   HTTPS").
2. If the origin needs TLS (Cloudflare Full strict): install a Cloudflare Origin CA certificate
   on nginx, listen 443 with it, redirect 80→443; keep the ACME `/.well-known/` location.
3. Burn-in CSP: keep `Content-Security-Policy-Report-Only`, exercise the SPA, then rename the
   header in `nginx.conf` to `Content-Security-Policy` and redeploy.
4. Enable HSTS gradually: set `HSTS_ENABLED=true` with `HSTS_MAX_AGE=300`, deploy, verify no
   breakage; raise to 86400 → 604800 → 15552000. Leave `HSTS_INCLUDE_SUBDOMAINS=false` until
   every subdomain is HTTPS.
5. Record the TLS tests (TLS-001…005) with `openssl s_client` output.

## 6. Logging and alerting (zero-cost baseline)

- All containers log to stdout with rotation (`json-file`, 10 MB × 3). Application security
  events carry `request_id` and are emitted by the `security` logger.
- Collect: `docker compose logs -f api` for live view; for persistence use OCI Logging
  (free tier) or `journald` with `docker-compose` log driver change.
- Minimum alerts (any log sink or a cron `grep`→mail script):
  - `rate_limit_exceeded` bursts (≥ 20/min)
  - `login_failed` spikes (≥ 50/min)
  - `admin_access_denied` > 0
  - container restarts (`docker events`)
  - disk > 85 % (`df` cron)
- Retention: keep security logs ≥ 30 days; rotate and restrict access to the VM account only.

## 7. Backups and restore (RPO 24 h / RTO 2 h baseline)

Create (daily cron on the VM):

```bash
cd /opt/infyexchange   # compose project path
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > /var/backups/infy_$(date +%F).dump
age -r <BACKUP_PUBKEY> -o /var/backups/infy_$(date +%F).dump.age /var/backups/infy_$(date +%F).dump
rm /var/backups/infy_$(date +%F).dump
```

- Store `.age` files off-host (OCI Object Storage free tier or an admin workstation). The private
  key stays **off the VM**.
- Monthly restore test into a scratch container:

```bash
docker run --rm -e POSTGRES_PASSWORD=scratch -p 127.0.0.1:55432:5432 -d --name pgtest postgres:17-alpine
age -d -i <BACKUP_KEY> infy_<date>.dump.age > /tmp/restore.dump
docker exec -i pgtest pg_restore -U postgres -d postgres -C < /tmp/restore.dump   # adapt DB name
docker exec pgtest psql -U postgres -c "select count(*) from users;"
docker rm -f pgtest
```

Record outcome (REC-001…003). A backup never restored is not a recovery mechanism.

## 8. Deploy, verify, rollback (change management)

Pre-deploy: `git status` clean; `docker compose -f docker-compose.prod.yml config -q` passes;
`pytest` green; `bandit` clean.

Deploy:

```bash
cd backend   # or project root depending on where you build
npm run build                     # refresh dist/ for the web container
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -fsS http://127.0.0.1/health || echo "API unhealthy"
```

Post-deploy smoke: login with a synthetic account → 200; `PUT` another user's listing → 403;
`curl -sI /api/...` shows the security headers; `docker compose logs api | grep service_started`.

Rollback per change of this iteration:

| Change | Rollback |
|---|---|
| App middleware/headers/limits | `git revert <commit>` of backend changes; rebuild api (`up -d --build api`). No DB migration involved. |
| Compose hardening | Restore previous `docker-compose.prod.yml` from git; `docker compose up -d`. Networks are recreated; data volume untouched. If a container fails to start due to `cap_drop`/`read_only`, remove those two keys for that service. |
| nginx hardening | Restore previous `nginx.conf`; `docker compose restart web`. If CSP breaks the SPA, it is report-only by default; if you already enforced it, switch the header name back to `-Report-Only`. |
| Pinned requirements | Restore previous `requirements.txt`; rebuild api. |
| Env template changes | `.env` untouched by this iteration except new optional keys (`HSTS_ENABLED`, `ALLOWED_HOSTS`) with safe defaults. |

## 9. Optional host tooling (evaluate before installing)

| Tool | Install when | Cost of running |
|---|---|---|
| Wazuh agent + manager | VM ≥ 4 GB RAM and someone reviews alerts | Manager elsewhere; agent light |
| ClamAV | Uploads may ever be stored/processed locally | Signature updates daily; RAM ~1 GB during scan |
| Suricata | Traffic is visible unencrypted at the VM and IPS is enforceable | CPU-heavy; encrypted TLS limits value |
| Trivy / OSV / pip-audit | Always (CI or weekly cron) | Negligible |
| Gitleaks | Always (pre-commit or weekly) | Negligible |

Do not install and claim protection without verifying alerts are received.

### DAST (OWASP ZAP)

`scripts/security/zap-api-scan.ps1` runs ZAP from Docker and writes HTML, Markdown and JSON
reports to `zap-reports/` (gitignored). Run it on staging before each release:

```powershell
# API scan (needs ENVIRONMENT != production so /openapi.json is served)
powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1

# SPA baseline scan
powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1 -Mode baseline `
    -Target http://host.docker.internal:5173

# Authenticated scan (context file injects the Bearer header)
powershell -ExecutionPolicy Bypass -File scripts/security/zap-api-scan.ps1 `
    -ContextFile .\zap-auth.conf
```

- The target must be reachable from inside the container: `host.docker.internal` on Docker
  Desktop, or attach the container to the compose network (`docker run --network <project>_edge`)
  on Linux.
- Production deliberately disables `/docs`, `/redoc` and `/openapi.json`. Scan staging/test
  instead of re-enabling API docs in production.
- Triage: every High alert is either fixed or entered in the THREAT_MODEL register with a
  residual-risk entry and an owner. Exit codes: 0 pass, 1 fail threshold reached, 2 scan error.

## 10. Incident response quick card

1. **Triage:** identify event type from `security` logs / Cloudflare / OCI audit.
2. **Contain:** for credential exposure — rotate `SECRET_KEY` (invalidates all tokens), rotate
   Cloudinary keys, rotate DB password (`ALTER USER` + update `.env` + restart api); for host
   compromise — snapshot disk, block NSG ingress, rotate everything, rebuild from clean image.
3. **Eradicate:** patch the vector (dependency upgrade, config fix).
4. **Recover:** restore from latest verified backup if data integrity is in doubt (§7).
5. **Learn:** update this runbook, threat model, and tests; record timeline and evidence.

Secret rotation procedures:

```bash
# SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"   # put into .env, restart api
# Cloudinary: rotate API key/secret in the Cloudinary console, update .env, restart api
# Postgres: docker compose exec postgres psql -U <user> -d <db> -c "ALTER USER <user> WITH PASSWORD '<new>';"
```

If a secret ever lands in git history: rotate first, then clean history (`git filter-repo`) —
deleting the file in a new commit is not sufficient. Current state: `.env` was **never
committed** (`git log --all -- backend/.env` empty), but the local file holds live Cloudinary
credentials — rotate them anyway if the machine or its backups were ever shared.

## 11. Maintenance calendar

| Cadence | Task |
|---|---|
| Weekly | `pip-audit`, `npm audit`, review `security` log alerts |
| Weekly | Check disk, container restarts, failed SSH attempts |
| Monthly | Restore-test a backup; review OCI/Cloudflare rules drift |
| Quarterly | Rotate DB password and Cloudinary keys; re-run full test plan; threat-model review |
| On every deploy | §8 checklist; re-run `pytest` + `bandit`; verify headers |
