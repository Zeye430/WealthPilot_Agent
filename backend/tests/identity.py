"""Identity double for tests and offline evaluation: the X-Demo-User header sets the identity,
replacing the get_current_user dependency.

Production code has a single authentication path, the session cookie (see app/api/deps.py); this
double is injected only in tests and evaluation scripts
via app.dependency_overrides; real authentication is tested separately in tests/test_auth.py.
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
