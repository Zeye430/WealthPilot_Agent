#!/usr/bin/env bash
# 删除服务器与固定 IP，停止计费。删除前先导出数据库并下载到 deploy/backups/。
# 用法：./deploy/destroy.sh      演练：DRY_RUN=1 ./deploy/destroy.sh
source "$(dirname "$0")/lib.sh"
load_state

echo "将删除 Lightsail 服务器「${INSTANCE}」与固定 IP（区域 ${REGION}）。服务器上的数据库会一并删除。"
if [ "$DRY_RUN" != 1 ]; then
  read -r -p "确认请输入服务器名称 ${INSTANCE}：" answer
  [ "$answer" = "$INSTANCE" ] || die "已取消"
fi

info "导出数据库并下载到本机"
mkdir -p "$DEPLOY_DIR/backups"
out="$DEPLOY_DIR/backups/wealthpilot-final-$(date +%Y%m%d-%H%M).sql.gz"
if [ "$DRY_RUN" = 1 ]; then
  echo "  [演练] ssh ubuntu@$IP 'sudo docker exec wealthpilot-prod-db-1 pg_dump … | gzip' > ${out}" >&2
elif remote "set -o pipefail; sudo docker exec wealthpilot-prod-db-1 pg_dump -U wealthpilot --no-owner wealthpilot | gzip" > "$out"; then
  note "已保存到 ${out}"
else
  rm -f "$out"
  # 当场导出失败（例如数据库已停止）时，退而下载服务器上最近一份每日备份
  latest="$(remote "ls -t /opt/wealthpilot/backups/*.sql.gz 2>/dev/null | head -1" || true)"
  if [ -n "$latest" ]; then
    scp -q -i "$KEY_FILE" "ubuntu@$IP:$latest" "$DEPLOY_DIR/backups/" && note "已保存最近一份每日备份：deploy/backups/$(basename "$latest")"
  else
    read -r -p "无法备份数据库，仍要删除服务器吗？输入 yes 继续：" answer
    [ "$answer" = "yes" ] || die "已取消"
  fi
fi

info "删除服务器与固定 IP"
aws_ls "" delete-instance --instance-name "$INSTANCE" >/dev/null
aws_ls "" release-static-ip --static-ip-name "$STATIC_IP_NAME" >/dev/null
[ "$DRY_RUN" = 1 ] || rm -f "$STATE"
note "SSH 密钥对保留（AWS 中的 $KEY_NAME 与本机 ${KEY_FILE}），下次部署可直接复用"
echo "✓ 已删除，不再产生服务器费用"
