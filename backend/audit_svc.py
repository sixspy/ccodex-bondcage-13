"""审计只读面。"""
from __future__ import annotations

from fastapi import APIRouter

from auth import AuthHeader, require_user
from db import connect

router = APIRouter(tags=["audit"])


@router.get("/api/audit")
def list_audit(authorization: AuthHeader = None, limit: int = 100):
    require_user(authorization)
    limit = max(1, min(int(limit), 500))
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_trail ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/audit/actions")
def list_actions(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT action, COUNT(*) c FROM audit_trail
               GROUP BY action ORDER BY c DESC"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/audit/reversals")
def list_reversal_audit(authorization: AuthHeader = None):
    """审计页冲正专面：冲正动作与偏航动作同表可溯，附冲正流水专表。"""
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM audit_trail
               WHERE action IN ('deposit_reversal','deposit_reversal_deviation')
               ORDER BY id DESC LIMIT 200"""
        ).fetchall()
        revs = conn.execute(
            "SELECT * FROM deposit_reversals ORDER BY id DESC LIMIT 200"
        ).fetchall()
        deviation_count = conn.execute(
            "SELECT COUNT(*) c FROM audit_trail WHERE action='deposit_reversal_deviation'"
        ).fetchone()["c"]
        return {
            "items": [dict(r) for r in rows],
            "reversals": [dict(r) for r in revs],
            "deviation_count": deviation_count,
        }
