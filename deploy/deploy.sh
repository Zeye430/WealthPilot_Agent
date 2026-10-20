#!/usr/bin/env bash
# One-command deploy to AWS Lightsail (US): create server → static IP → open ports → upload code → start → wait until ready.
#
# Prerequisites (see Deployment in the README):
#   1. AWS CLI v2 installed and aws configure run with an IAM access key limited to Lightsail
#   2. deploy/.env.production filled in
# Usage:
#   ./deploy/deploy.sh                 # 2 GB server ($12/month)
#   RAM_GB=4 ./deploy/deploy.sh        # 4 GB server ($24/month)
#   DRY_RUN=1 ./deploy/deploy.sh       # dry run: print the commands without creating anything
source "$(dirname "$0")/lib.sh"

info "检查本机环境与配置"
command -v git >/dev/null || die "需要 git"
check_env_file
if [ "$DRY_RUN" != 1 ]; then
  command -v aws >/dev/null || die "需要 AWS CLI v2：https://aws.amazon.com/cli/"
  aws sts get-caller-identity --query Account --output text >/dev/null \
    || die "AWS 凭证不可用：请先运行 aws configure（使用 IAM 访问密钥，不要用账号密码）"
fi
[ ! -f "$STATE" ] || die "已有部署记录（deploy/.state）。更新代码请用 deploy/update.sh；重新部署请先运行 deploy/destroy.sh"

info "准备 SSH 密钥"
if [ -f "$KEY_FILE" ]; then
  note "使用已有密钥 $KEY_FILE"
else
  mkdir -p "$(dirname "$KEY_FILE")"
  key="$(aws_ls "DRY-RUN-KEY" create-key-pair --key-pair-name "$KEY_NAME" --query privateKeyBase64 --output text)" \
    || die "无法创建密钥对 ${KEY_NAME}（若 AWS 中已存在同名密钥而本机没有私钥，请先在 Lightsail 控制台删除它）"
  if [ "$DRY_RUN" != 1 ]; then
    umask 077; printf '%s\n' "$key" > "$KEY_FILE"; chmod 600 "$KEY_FILE"
  fi
  note "已保存私钥：${KEY_FILE}（只在本机，不要提交或分享）"
fi

info "选择机型：${RAM_GB} GB 内存"
BUNDLE="$(aws_ls "small_3_0" get-bundles --output text \
  --query "sort_by(bundles[?ramSizeInGb==\`${RAM_GB}.0\` && isActive && contains(supportedPlatforms, 'LINUX_UNIX') && !contains(bundleId, 'ipv6')], &price)[0].bundleId")"
if [ -z "$BUNDLE" ] || [ "$BUNDLE" = "None" ]; then die "没有找到 ${RAM_GB} GB 的 Lightsail 机型"; fi
BLUEPRINT="$(aws_ls "ubuntu_24_04" get-blueprints --output text \
  --query "blueprints[?type=='os' && platform=='LINUX_UNIX' && starts_with(blueprintId, 'ubuntu_24')].blueprintId | [0]")"
if [ -z "$BLUEPRINT" ] || [ "$BLUEPRINT" = "None" ]; then die "没有找到 Ubuntu 24 系统镜像"; fi
note "机型 ${BUNDLE}，系统 ${BLUEPRINT}，区域 $REGION"

info "创建服务器 $INSTANCE"
aws_ls "" create-instances --instance-names "$INSTANCE" --availability-zone "${REGION}a" \
  --blueprint-id "$BLUEPRINT" --bundle-id "$BUNDLE" --key-pair-name "$KEY_NAME" \
  --user-data "file://$DEPLOY_DIR/server-init.sh" --tags key=project,value=wealthpilot >/dev/null
for _ in $(seq 1 60); do
  state="$(aws_ls "running" get-instance-state --instance-name "$INSTANCE" --query state.name --output text)"
  [ "$state" = "running" ] && break
  sleep 5
done
[ "$state" = "running" ] || die "服务器未能启动（状态：${state}）"

info "分配固定 IP 并开放端口 22 / 80 / 443"
aws_ls "" allocate-static-ip --static-ip-name "$STATIC_IP_NAME" >/dev/null
aws_ls "" attach-static-ip --static-ip-name "$STATIC_IP_NAME" --instance-name "$INSTANCE" >/dev/null
IP="$(aws_ls "203.0.113.10" get-static-ip --static-ip-name "$STATIC_IP_NAME" --query staticIp.ipAddress --output text)"
aws_ls "" put-instance-public-ports --instance-name "$INSTANCE" --port-infos \
  "fromPort=22,toPort=22,protocol=tcp" "fromPort=80,toPort=80,protocol=tcp" "fromPort=443,toPort=443,protocol=tcp" >/dev/null

DOMAIN="$(env_value DOMAIN)"
if [ -z "$DOMAIN" ]; then
  DOMAIN="${IP//./-}.sslip.io"
  note "未设置域名，使用免费地址 ${DOMAIN}（同样有 HTTPS）"
else
  note "自有域名 ${DOMAIN}：请确认 DNS 的 A 记录已指向 ${IP}，否则无法签发 HTTPS 证书"
fi

if [ "$DRY_RUN" != 1 ]; then
  cat > "$STATE" <<STATE_EOF
REGION=$REGION
INSTANCE=$INSTANCE
STATIC_IP_NAME=$STATIC_IP_NAME
KEY_NAME=$KEY_NAME
KEY_FILE=$KEY_FILE
IP=$IP
DOMAIN=$DOMAIN
STATE_EOF
fi

info "等待服务器完成初始化（安装 Docker、配置交换空间）"
if [ "$DRY_RUN" != 1 ]; then
  for _ in $(seq 1 60); do remote true 2>/dev/null && break; sleep 5; done
  remote "cloud-init status --wait >/dev/null" || die "服务器初始化失败：ssh -i $KEY_FILE ubuntu@$IP 'sudo cat /var/log/cloud-init-output.log'"
fi

ship
wait_ready

cat <<DONE

✓ 部署完成
  访问地址：      https://$DOMAIN
  客户入口：      https://$DOMAIN/bank（模拟手机银行）
  运维看板：      https://$DOMAIN/ops
  访问码：        见 deploy/.env.production 中的 DEMO_ACCESS_CODE（发给面试官）
  登录服务器：    ssh -i $KEY_FILE ubuntu@$IP
  更新代码：      ./deploy/update.sh
  停止计费：      ./deploy/destroy.sh（先导出数据库到本机，再删除服务器与固定 IP）
DONE
