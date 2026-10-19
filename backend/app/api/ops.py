"""运维看板 API：只对运维角色开放；只返回汇总指标与审计编号，不返回对话内容和客户资料。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_now, get_ops_user
from app.api.health import readiness
from app.auth.service import CurrentUser
from app.db.session import get_session
from app.ops.turns import overview

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])


@router.get("/overview")
def ops_overview(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    db: Session = Depends(get_session),
    now: datetime = Depends(get_now),
    _: CurrentUser = Depends(get_ops_user),
):
    return {**overview(db, now, hours), "health": readiness()}
