#!/usr/bin/env bash
# Update the code: upload the current commit, rebuild on the server and restart (data is kept).
# Usage: ./deploy/update.sh      Dry run: DRY_RUN=1 ./deploy/update.sh
# In GitHub Actions it's called with the DEPLOY_HOST / DEPLOY_DOMAIN / KEY_FILE environment variables (see .github/workflows/deploy.yml)
source "$(dirname "$0")/lib.sh"
load_state
check_env_file
ship
wait_ready
echo "✓ 已更新：https://$DOMAIN"
