#!/usr/bin/env bash
# 更新代码：上传当前提交，在服务器上重新构建并滚动重启（数据保留）。
# 用法：./deploy/update.sh      演练：DRY_RUN=1 ./deploy/update.sh
# GitHub Actions 中通过 DEPLOY_HOST / DEPLOY_DOMAIN / KEY_FILE 环境变量调用（见 .github/workflows/deploy.yml）
source "$(dirname "$0")/lib.sh"
load_state
check_env_file
ship
wait_ready
echo "✓ 已更新：https://$DOMAIN"
