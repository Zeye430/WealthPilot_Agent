"""测试与离线评估用的身份替身：用 X-Demo-User 请求头指定身份，替换 get_current_user 依赖。

生产代码只有会话 Cookie 一条认证路径（见 app/api/deps.py）；这个替身只在测试和评估脚本中
通过 app.dependency_overrides 注入，真实认证由 tests/test_auth.py 单独测试。
"""

from fastapi import Header, HTTPException

from app.auth.service import CUSTOMER, OPS, RM, CurrentUser
from app.customers.base import get_customer_info_system

TEST_RMS = {"rm_li": "RM001", "rm_zhou": "RM002"}


def header_identity(x_demo_user: str | None = Header(default=None)) -> CurrentUser:
    if not x_demo_user:
        raise HTTPException(status_code=401, detail="请先登录")
    if x_demo_user == "ops_oncall":
        return CurrentUser(id=x_demo_user, username=x_demo_user, display_name="运维值班", role=OPS)
    if rm_id := TEST_RMS.get(x_demo_user):
        return CurrentUser(
            id=x_demo_user, username=x_demo_user, display_name=x_demo_user, role=RM, rm_id=rm_id
        )
    if get_customer_info_system().get(x_demo_user) is None:
        raise HTTPException(status_code=403, detail="未知的测试身份")
    return CurrentUser(
        id=x_demo_user,
        username=x_demo_user,
        display_name=x_demo_user,
        role=CUSTOMER,
        customer_id=x_demo_user,
    )
