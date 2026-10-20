#!/bin/bash
# Runs on the server (called over ssh by ship in lib.sh): unpack the new release, build and start, download the speech model, clean up old releases.
# Each release lives in /opt/wealthpilot/releases/<commit>/, with current pointing at the running one; data lives in Docker volumes and isn't deleted with releases.
set -euo pipefail
: "${DOMAIN:?}" "${GIT_SHA:?}"

APP=/opt/wealthpilot
RELEASE="$APP/releases/$GIT_SHA"
sudo mkdir -p "$RELEASE" "$APP/backups"
sudo tar -xzf /tmp/wealthpilot-app.tar.gz -C "$RELEASE"
sudo install -m 600 /tmp/wealthpilot.env "$RELEASE/deploy/.env.production"
# Write this deploy's actual parameters into the server config, so running docker compose by hand later (e.g. to restore a backup) needs no extra arguments
# shellcheck disable=SC1003  # '$a\' is sed's append-at-end command, not an escaped single quote
sudo sed -i -e '/^\(DOMAIN\|GIT_SHA\|BACKUP_DIR\)=/d' -e '$a\' "$RELEASE/deploy/.env.production"   # remove old values; ensure a trailing newline
printf 'DOMAIN=%s\nGIT_SHA=%s\nBACKUP_DIR=%s\n' "$DOMAIN" "$GIT_SHA" "$APP/backups" \
  | sudo tee -a "$RELEASE/deploy/.env.production" >/dev/null
rm -f /tmp/wealthpilot-app.tar.gz /tmp/wealthpilot.env

cd "$RELEASE/deploy"
COMPOSE=(sudo docker compose --env-file .env.production -f docker-compose.prod.yml)

"${COMPOSE[@]}" build
if [ "${VOICE_ENABLED:-true}" != "false" ]; then
  # The speech model is stored in a Docker volume and downloaded only the first time
  "${COMPOSE[@]}" run --rm --no-deps backend uv run --no-dev python -m app.speech.download
fi
# Back up before updating: a new release may include migrations, so we can restore the pre-update state (skipped on first deploy, when no database is running yet)
if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx db; then
  "${COMPOSE[@]}" exec -T db pg_dump -U wealthpilot --no-owner wealthpilot | gzip \
    | sudo tee "$APP/backups/pre-deploy-$GIT_SHA.sql.gz" >/dev/null
  echo "✓ 更新前备份：$APP/backups/pre-deploy-$GIT_SHA.sql.gz"
  # shellcheck disable=SC2012
  ls -t "$APP"/backups/pre-deploy-*.sql.gz | tail -n +6 | xargs -r sudo rm -f
fi
"${COMPOSE[@]}" up -d --remove-orphans

sudo ln -sfn "$RELEASE" "$APP/current"
# Keep the last 3 releases for rollback
# Release directories are named by commit (alphanumeric), so sorting by modification time is enough
# shellcheck disable=SC2012
ls -dt "$APP"/releases/* | tail -n +4 | xargs -r sudo rm -rf
sudo docker image prune -f >/dev/null
echo "✓ 已启动版本 $GIT_SHA"
