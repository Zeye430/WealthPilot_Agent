# WealthPilot AI — 部署手册（AWS Lightsail）

> 目标：需要公开演示时，填好配置、执行一条命令，约 15 分钟得到一个带 HTTPS 的线上地址；不用时一条命令删除、停止计费。
> 演示环境是一台云主机上的完整系统（数据库、后端、前端、HTTPS、每日备份）。银行生产环境的部署形态不同，见 [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)。

## 1. 会创建什么

```text
互联网 ──443──▶ Caddy（自动 HTTPS 证书）──┬─▶ 前端 Next.js ──/api──▶ 后端 FastAPI ──▶ PostgreSQL + pgvector
                 /metrics → 404            └─▶ /health* 直接到后端              ▲
                                                                  每日备份 ──────┘（保留 7 天）
```

| 资源 | 说明 |
|---|---|
| Lightsail 服务器 | Ubuntu 24.04，美国东部（`us-east-1`），默认 2 GB 内存 / $12 每月；`RAM_GB=4` 为 4 GB / $24 每月 |
| 固定 IP | 绑定在服务器上时免费；服务器删除时一并释放 |
| 防火墙 | 只开放 22（SSH）、80、443；数据库、后端、前端不对外 |
| 访问地址 | 不填域名时使用 `<IP>.sslip.io`（免费，同样有正式 HTTPS 证书）；也可用自有域名 |
| SSH 密钥 | 自动创建，私钥保存在本机 `~/.ssh/wealthpilot-lightsail.pem` |

**机型选择**：2 GB 足够演示（脚本会加 2 GB 交换空间；语音识别模型按需加载）。如果多人同时试用或经常用语音，选 4 GB。

## 2. 一次性准备

### 2.1 AWS 访问密钥（不是账号密码）

部署脚本通过 AWS CLI 调用 Lightsail 接口，使用 **IAM 用户的访问密钥**。不要用 AWS 根账号或账号密码，也不要把密钥发给任何人或写进仓库。

1. 登录 AWS 控制台 → IAM → 用户 → 创建用户（如 `wealthpilot-deployer`），不需要控制台登录权限；
2. 给该用户添加内联策略（只允许部署脚本用到的 Lightsail 操作）：

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": [
         "lightsail:GetBundles", "lightsail:GetBlueprints",
         "lightsail:CreateKeyPair",
         "lightsail:CreateInstances", "lightsail:GetInstanceState", "lightsail:DeleteInstance",
         "lightsail:PutInstancePublicPorts",
         "lightsail:AllocateStaticIp", "lightsail:AttachStaticIp", "lightsail:GetStaticIp", "lightsail:ReleaseStaticIp"
       ],
       "Resource": "*"
     }]
   }
   ```

3. 该用户 → 安全凭证 → 创建访问密钥（用途选「命令行界面」）；
4. 本机安装 AWS CLI v2（macOS：`brew install awscli`），然后：

   ```bash
   aws configure            # 填入访问密钥 ID 与私有访问密钥；区域填 us-east-1；输出格式 json
   aws sts get-caller-identity   # 能显示账号编号即配置成功
   ```

密钥保存在本机 `~/.aws/credentials`。不再部署时，可在 IAM 中停用或删除该密钥。

### 2.2 填写生产配置

```bash
cp deploy/.env.production.example deploy/.env.production
openssl rand -hex 32     # 生成密钥用，每个密钥单独生成一次
```

| 配置项 | 填写 |
|---|---|
| `DOMAIN` | 留空使用 sslip.io；有自有域名时见 §4 |
| `LLM_API_KEY` | Kimi（Moonshot 国际站）API Key；`LLM_MODEL` 等保持默认 |
| `POSTGRES_PASSWORD`、`APP_TICKET_SECRET`、`METRICS_TOKEN` | 分别用 `openssl rand -hex 32` 生成 |
| `DEMO_PASSWORD` | 演示账号的统一密码，**不能用默认的 `wealthpilot-demo`** |
| `DEMO_ACCESS_CODE` | 访问码：登录时额外输入，防止陌生人消耗模型额度；发给面试官 |
| `DEMO_LOGIN_HINT` / `_EN` | 登录页提示（可写「账号 wang，密码见邮件」）；留空不显示 |
| `VOICE_ENABLED` | `true` 时首次部署下载语音模型（约 240 MB） |

`deploy/.env.production` 已在 `.gitignore` 中。部署脚本会检查必填项、默认密码与密钥长度，不合格时直接停止。

## 3. 部署

```bash
DRY_RUN=1 ./deploy/deploy.sh    # 演练：只打印将执行的 AWS 与服务器命令，不创建资源、不产生费用
./deploy/deploy.sh              # 正式部署（2 GB）；4 GB：RAM_GB=4 ./deploy/deploy.sh
```

脚本依次：检查配置 → 创建 SSH 密钥 → 选择机型与系统镜像 → 创建服务器（初始化脚本安装 Docker、加交换空间）→ 分配并绑定固定 IP → 开放 22 / 80 / 443 → 上传当前提交的代码与配置 → 构建并启动 → 等待 `https://<地址>/health/ready` 就绪。首次约 10–15 分钟，结束时打印访问地址。

注意：
- 上传的是**最近一次提交**（`git archive HEAD`），未提交的修改不会上线；
- 部署信息（IP、地址）写入 `deploy/.state`（不提交），之后的更新、删除都读取它；
- 已有 `deploy/.state` 时脚本拒绝重复创建，防止多开一台服务器。

## 4. 使用自有域名（可选）

1. 先用默认配置部署一次，记下输出的固定 IP；
2. 在域名服务商处添加 A 记录：`wealthpilot.example.com → <固定 IP>`，等待生效（`dig +short wealthpilot.example.com` 返回该 IP）；
3. 在 `deploy/.env.production` 填写 `DOMAIN=wealthpilot.example.com`，并修改 `deploy/.state` 中的 `DOMAIN`；
4. 运行 `./deploy/update.sh`。Caddy 会自动为新域名申请证书。

## 5. 更新与回滚

```bash
git commit ...           # 先提交要上线的修改
./deploy/update.sh       # 上传、构建、重启；数据保留
```

每次更新：
- 构建新镜像后、切换前，先导出一份数据库到服务器的 `/opt/wealthpilot/backups/pre-deploy-<提交号>.sql.gz`（保留最近 5 份），因为新版本可能带数据库迁移；
- 服务器保留最近 3 个版本的代码（`/opt/wealthpilot/releases/<提交号>`），`current` 指向正在运行的版本。

**回滚**：本机 `git checkout <上一个提交>` 后运行 `./deploy/update.sh`，再 `git checkout main` 回到开发分支。如果出问题的版本执行过数据库迁移，先按 §6 用该版本的更新前备份恢复数据库，再回滚代码（旧代码不认识新迁移建的表结构）。

服务器上的 `.env.production` 由部署脚本补上了本次的 `DOMAIN`、`GIT_SHA` 与备份目录，所以在服务器上可以直接执行 `docker compose`（如 §6 的恢复步骤），不必再传参数。

## 6. 备份与恢复

- **每日备份**：`backup` 容器每天导出一次数据库到服务器 `/opt/wealthpilot/backups/wealthpilot-<日期>.sql.gz`，保留 7 天；
- **更新前备份**：见 §5；
- **删除前备份**：`destroy.sh` 删除服务器前，当场导出数据库并下载到本机 `deploy/backups/`。

恢复（在服务器上执行；已在本机按同样步骤演练：删库 → 恢复 → 数据条数一致 → 服务正常）：

```bash
cd /opt/wealthpilot/current/deploy
C="sudo docker compose --env-file .env.production -f docker-compose.prod.yml"
$C stop backend frontend backup
$C exec -T db psql -U wealthpilot -d postgres \
  -c 'DROP DATABASE wealthpilot WITH (FORCE)' -c 'CREATE DATABASE wealthpilot OWNER wealthpilot'
gunzip -c /opt/wealthpilot/backups/<备份文件>.sql.gz | $C exec -T db psql -q -U wealthpilot -d wealthpilot -v ON_ERROR_STOP=1
$C start backend frontend backup
```

备份只在同一台服务器上；演示环境可以接受。生产中备份应存到另一个位置（如对象存储），并定期做恢复演练。

## 7. 删除（停止计费）

```bash
./deploy/destroy.sh      # 需输入服务器名称确认；先导出数据库到本机 deploy/backups/，再删除服务器与固定 IP
```

SSH 密钥对保留，下次部署直接复用。删除后可在 Lightsail 控制台确认没有剩余的服务器与固定 IP（未绑定的固定 IP 会收费）。

## 8. 从 GitHub 更新（可选）

服务器创建后，可以在 GitHub 页面上触发更新（`.github/workflows/deploy.yml`，Actions → Deploy → Run workflow），效果等同于本机运行 `update.sh`。

在仓库 Settings → Environments 中创建 `production` 环境（建议勾选「需要审批」），添加 Secrets：

| Secret | 内容 |
|---|---|
| `DEPLOY_HOST` | 固定 IP（`deploy/.state` 中的 `IP`） |
| `DEPLOY_DOMAIN` | 访问地址（`deploy/.state` 中的 `DOMAIN`） |
| `DEPLOY_SSH_KEY` | `~/.ssh/wealthpilot-lightsail.pem` 的全部内容 |
| `DEPLOY_KNOWN_HOSTS` | `ssh-keygen -F <固定 IP>` 的输出（部署时本机已记录的服务器指纹，防止连接到冒充的主机） |
| `DEPLOY_ENV_FILE` | `deploy/.env.production` 的全部内容 |

GitHub 的 Secrets 加密保存，日志中自动遮盖。workflow 结束时删除运行机上的密钥与配置文件。

## 9. 本机验证生产配置

不创建云服务器，在本机运行同一套生产编排（Caddy 使用本机签发的证书）。项目名与端口和开发环境分开：

```bash
cd deploy
cp .env.production.example .env.production   # 填写；可设 LLM_PROVIDER=fake 不调用模型
export DOMAIN=localhost PUBLIC_ORIGIN=https://localhost:8443 HTTP_PORT=8080 HTTPS_PORT=8443 GIT_SHA=$(git rev-parse --short HEAD)
docker compose -p wealthpilot-prodtest --env-file .env.production -f docker-compose.prod.yml up -d --build --wait
curl -k https://localhost:8443/health/ready
# 浏览器打开 https://localhost:8443/bank（忽略证书提示）
docker compose -p wealthpilot-prodtest --env-file .env.production -f docker-compose.prod.yml down -v   # 结束后删除容器与数据
```

`PUBLIC_ORIGIN` 只在非 443 端口时需要（浏览器的来源带端口号，需加入允许的来源）。CI 的 `deploy-config` 任务每次提交都用假模型启动这套编排并检查：就绪检查、`/metrics` 对外 404、HSTS、未输入访问码时登录被拒、镜像中有演示数据但没有 `data/reference/` 与 `.env`。

## 10. 安全要点

| 风险 | 措施 |
|---|---|
| 陌生人登录消耗模型额度 | 访问码 + 非默认密码；登录与对话限流（每用户每分钟 20 次、每天 300 次） |
| 伪造 IP 绕过登录限流 | Caddy 用真实来源 IP 覆盖 `X-Forwarded-For` |
| 指标外泄 | `/metrics` 在 Caddy 返回 404，后端另有令牌保护 |
| 会话被窃取 | HTTPS + HSTS；Cookie 为 `Secure`、`HttpOnly` |
| 密钥泄露 | `.env.production` 不提交、上传后权限 600；镜像构建排除 `.env` 与 `data/reference/`（CI 检查） |
| 服务器被入侵 | 只开放 22 / 80 / 443；SSH 只允许密钥登录（Lightsail 默认）；数据库不对外 |

完整威胁模型见 [SECURITY.md](SECURITY.md)。

## 11. 费用

| 项目 | 每月 |
|---|---|
| Lightsail 2 GB（或 4 GB） | $12（$24） |
| 固定 IP（绑定中） | $0 |
| 域名 | sslip.io 免费；自有域名约 $10–15 / 年 |
| 模型调用 | 每轮约 $0.011（[COST_ESTIMATE.md](COST_ESTIMATE.md)）；面试演示用量通常每月不到 $10 |

Lightsail 按小时计费：只在投递简历、面试期间开着，其余时间删除，即可把费用控制在几美元。

## 12. 常见问题

- **证书申请失败**：sslip.io 或自有域名需要能从公网访问 80 / 443 端口；检查 `sudo docker compose ... logs caddy`。Let's Encrypt 对同一域名有签发频率限制，证书保存在 `caddy-data` 卷中，重启不会重新申请。
- **就绪检查一直不通过**：`ssh -i ~/.ssh/wealthpilot-lightsail.pem ubuntu@<IP>`，进入 `/opt/wealthpilot/current/deploy` 查看 `docker compose ... ps` 与 `logs backend`。常见原因：`LLM_API_KEY` 无效（就绪检查中 `llm` 项失败）。
- **内存不足**：`free -h` 查看；换 4 GB 机型需 `destroy.sh` 后用 `RAM_GB=4` 重新部署（先保存好备份）。
- **AWS 报权限不足**：检查 §2.1 的 IAM 策略是否包含报错中的操作。
