#!/usr/bin/env bash
# Variables defined here are used by the scripts that source this file
# shellcheck disable=SC2034
# Shared functions for the deploy scripts. Sourced by deploy.sh / update.sh / destroy.sh, not run on its own.
# DRY_RUN=1: print the AWS and server commands instead of running them (to check the flow at no cost).
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DEPLOY_DIR/.." && pwd)"
STATE="$DEPLOY_DIR/.state"
ENV_FILE="$DEPLOY_DIR/.env.production"

REGION="${AWS_REGION:-us-east-1}"
INSTANCE="${INSTANCE_NAME:-wealthpilot}"
STATIC_IP_NAME="${INSTANCE}-ip"
KEY_NAME="${INSTANCE}-key"
KEY_FILE="${KEY_FILE:-$HOME/.ssh/${INSTANCE}-lightsail.pem}"
RAM_GB="${RAM_GB:-2}"              # 2 = $12/month; 4 = $24/month
DRY_RUN="${DRY_RUN:-0}"

info() { printf '\033[1m▶ %s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }
die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# Run an AWS Lightsail command; in dry-run mode print it and return the given placeholder (first argument)
aws_ls() {
  local placeholder="$1"; shift
  if [ "$DRY_RUN" = 1 ]; then
    echo "  [演练] aws lightsail --region $REGION $*" >&2
    [ -n "$placeholder" ] && echo "$placeholder"
    return 0
  fi
  aws lightsail --region "$REGION" "$@"
}

remote() {
  if [ "$DRY_RUN" = 1 ]; then echo "  [演练] ssh ubuntu@$IP $*" >&2; return 0; fi
  ssh -i "$KEY_FILE" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "ubuntu@$IP" "$@"
}

upload() {
  if [ "$DRY_RUN" = 1 ]; then echo "  [演练] scp $1 → ubuntu@$IP:$2" >&2; return 0; fi
  scp -q -i "$KEY_FILE" -o StrictHostKeyChecking=accept-new "$1" "ubuntu@$IP:$2"
}

env_value() { # read a value from .env.production (without executing the file)
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true
}

check_env_file() {
  [ -f "$ENV_FILE" ] || die "缺少 deploy/.env.production：请先 cp deploy/.env.production.example deploy/.env.production 并填写"
  local missing=()
  for key in LLM_API_KEY POSTGRES_PASSWORD APP_TICKET_SECRET DEMO_PASSWORD DEMO_ACCESS_CODE METRICS_TOKEN; do
    [ -n "$(env_value "$key")" ] || missing+=("$key")
  done
  [ ${#missing[@]} -eq 0 ] || die "deploy/.env.production 中这些必填项为空：${missing[*]}"
  [ "$(env_value DEMO_PASSWORD)" != "wealthpilot-demo" ] || die "公开部署请修改 DEMO_PASSWORD（不要用默认演示密码）"
  local secret; secret="$(env_value APP_TICKET_SECRET)"
  [ ${#secret} -ge 32 ] || die "APP_TICKET_SECRET 太短：请用 openssl rand -hex 32 生成"
}

load_state() {
  # Prefer environment variables (provided by Secrets in GitHub Actions), otherwise read the local deploy state
  if [ -n "${DEPLOY_HOST:-}" ]; then
    IP="$DEPLOY_HOST"; DOMAIN="${DEPLOY_DOMAIN:?DEPLOY_DOMAIN 未设置}"
    return
  fi
  [ -f "$STATE" ] || die "没有找到部署记录（deploy/.state）：请先运行 deploy/deploy.sh"
  # shellcheck disable=SC1090
  source "$STATE"
}

# Upload the current commit's code and config, then build and start on the server
ship() {
  local sha tmp
  sha="$(git -C "$ROOT" rev-parse --short HEAD)"
  if [ -n "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]; then
    note "提示：有未提交的修改；部署的是最近一次提交 ${sha}（git archive），未提交的内容不会上线"
  fi
  tmp="$(mktemp -d)"
  git -C "$ROOT" archive --format=tar.gz -o "$tmp/app.tar.gz" HEAD
  info "上传代码（${sha}）与配置"
  upload "$tmp/app.tar.gz" /tmp/wealthpilot-app.tar.gz
  upload "$ENV_FILE" /tmp/wealthpilot.env
  rm -rf "$tmp"
  info "在服务器上构建并启动（首次约 5–10 分钟：下载镜像、构建前后端、下载模型）"
  if [ "$DRY_RUN" = 1 ]; then
    echo "  [演练] ssh ubuntu@$IP DOMAIN=$DOMAIN GIT_SHA=$sha bash -s < deploy/remote-up.sh" >&2
  else
    ssh -i "$KEY_FILE" -o StrictHostKeyChecking=accept-new "ubuntu@$IP" \
      "DOMAIN='$DOMAIN' GIT_SHA='$sha' VOICE_ENABLED='$(env_value VOICE_ENABLED)' bash -s" \
      < "$DEPLOY_DIR/remote-up.sh"
  fi
}

wait_ready() {
  info "等待服务就绪：https://$DOMAIN/health/ready"
  if [ "$DRY_RUN" = 1 ]; then echo "  [演练] curl -fsS https://$DOMAIN/health/ready" >&2; return 0; fi
  for _ in $(seq 1 60); do
    if curl -fsS --max-time 10 "https://$DOMAIN/health/ready" >/dev/null 2>&1; then
      note "✓ 就绪"
      return 0
    fi
    sleep 10
  done
  die "10 分钟内未就绪：ssh -i $KEY_FILE ubuntu@$IP 'cd /opt/wealthpilot/current/deploy && sudo docker compose -f docker-compose.prod.yml logs --tail 100'"
}
