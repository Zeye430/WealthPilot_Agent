#!/bin/bash
# 在服务器上执行（由 lib.sh 的 ship 通过 ssh 调用）：解压新版本、构建启动、下载语音模型、清理旧版本。
# 每个版本放在 /opt/wealthpilot/releases/<提交号>/，current 指向正在运行的版本；数据在 Docker 卷中，不随版本删除。
set -euo pipefail
: "${DOMAIN:?}" "${GIT_SHA:?}"

APP=/opt/wealthpilot
RELEASE="$APP/releases/$GIT_SHA"
sudo mkdir -p "$RELEASE" "$APP/backups"
sudo tar -xzf /tmp/wealthpilot-app.tar.gz -C "$RELEASE"
sudo install -m 600 /tmp/wealthpilot.env "$RELEASE/deploy/.env.production"
# 把本次部署的实际参数写入服务器上的配置：之后在服务器上手动执行 docker compose（如恢复备份）时无需再传
# shellcheck disable=SC1003  # '$a\' 是 sed 的「末尾追加」命令，不是转义单引号
sudo sed -i -e '/^\(DOMAIN\|GIT_SHA\|BACKUP_DIR\)=/d' -e '$a\' "$RELEASE/deploy/.env.production"   # 删除旧值；补齐末尾换行
printf 'DOMAIN=%s\nGIT_SHA=%s\nBACKUP_DIR=%s\n' "$DOMAIN" "$GIT_SHA" "$APP/backups" \
  | sudo tee -a "$RELEASE/deploy/.env.production" >/dev/null
rm -f /tmp/wealthpilot-app.tar.gz /tmp/wealthpilot.env

cd "$RELEASE/deploy"
COMPOSE=(sudo docker compose --env-file .env.production -f docker-compose.prod.yml)

"${COMPOSE[@]}" build
if [ "${VOICE_ENABLED:-true}" != "false" ]; then
  # 语音模型存入 Docker 卷，只在第一次下载
  "${COMPOSE[@]}" run --rm --no-deps backend uv run --no-dev python -m app.speech.download
fi
# 更新前先备份：新版本可能带数据库迁移，出问题时可恢复到更新前（首次部署时数据库尚未运行，跳过）
if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx db; then
  "${COMPOSE[@]}" exec -T db pg_dump -U wealthpilot --no-owner wealthpilot | gzip \
    | sudo tee "$APP/backups/pre-deploy-$GIT_SHA.sql.gz" >/dev/null
  echo "✓ 更新前备份：$APP/backups/pre-deploy-$GIT_SHA.sql.gz"
  # shellcheck disable=SC2012
  ls -t "$APP"/backups/pre-deploy-*.sql.gz | tail -n +6 | xargs -r sudo rm -f
fi
"${COMPOSE[@]}" up -d --remove-orphans

sudo ln -sfn "$RELEASE" "$APP/current"
# 保留最近 3 个版本，便于回滚
# 版本目录名是提交号（字母数字），按修改时间排序即可
# shellcheck disable=SC2012
ls -dt "$APP"/releases/* | tail -n +4 | xargs -r sudo rm -rf
sudo docker image prune -f >/dev/null
echo "✓ 已启动版本 $GIT_SHA"
