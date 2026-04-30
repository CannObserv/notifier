# Deployment

Single-VM setup; co-located with `watcher` for the v0 phase.

## First-time setup

```bash
# Install Python 3.12+ and uv (already present on the shared VM)
# Create the production env file
sudo mkdir -p /etc/notifier
sudo tee /etc/notifier/.env > /dev/null <<'EOF'
DATABASE_URL=postgresql+asyncpg://notifier:notifier@localhost:5432/notifier
NOTIFIER_SECRET_KEY=<paste Fernet key here>
EOF
sudo chmod 640 /etc/notifier/.env

# Provision Postgres
sudo -u postgres psql -c "CREATE USER notifier WITH PASSWORD 'notifier';"
sudo -u postgres psql -c "CREATE DATABASE notifier OWNER notifier;"
sudo -u postgres psql -c "CREATE DATABASE notifier_test OWNER notifier;"

# Install dependencies + apply migrations
cd /home/exedev/notifier
uv sync
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
uv run alembic upgrade head

# Install systemd unit
sudo cp deploy/notifier.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now notifier
```

## Routine ops

```bash
# Restart after code merge
sudo systemctl restart notifier

# Apply pending migrations then restart
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
uv run alembic upgrade head && sudo systemctl restart notifier

# Logs
sudo journalctl -u notifier -f
```

## Future: split VM

Once the v0 API has held still for a few weeks, provision a separate exe.dev VM and pg_dump → restore the `notifier` database there. Update watcher's `NOTIFY_BASE_URL` to point at the new host. Decommission the local notifier service on watcher's VM.
