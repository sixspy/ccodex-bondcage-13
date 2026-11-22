"""入金冲正写路径（甲路径·同事务回滚，2026-11-22 锁死）。

规则来源：docs/入金冲正纪要_2026-11-22.md，口径裁决见 reversal_policy。
- 抢 bond:{party_key} 账户锁；后到者只留争用痕（contention_log），零业务写。
- 锁内全部校验先于任何业务写；不过则整笔回滚、余额零改。
- 通过后同一事务：deposit_reversals 流水 + deposit_ledger 负额账 + 扣 balance（frozen 不动）+ 审计。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import available_of, connect, now_iso, write_audit
from locks import release, try_acquire
from models import DepositReversalIn
from reversal_policy import (
    DEVIATION_AUDIT_ACTION,
    REVERSAL_AUDIT_ACTION,
    REVERSAL_PATH_LOCKED,
    REVERSAL_STATUS,
    is_locked_path,
    policy_snapshot,
)

router = APIRouter(tags=["reversal"])


@router.get("/api/reversal-policy")
def get_policy(authorization: AuthHeader = None):
    require_user(authorization)
    return policy_snapshot()


@router.get("/api/bonds/reversals")
def list_reversals(authorization: AuthHeader = None, party_key: str | None = None):
    require_user(authorization)
    with connect() as conn:
        if party_key:
            rows = conn.execute(
                "SELECT * FROM deposit_reversals WHERE party_key=? ORDER BY id DESC LIMIT 200",
                (party_key,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM deposit_reversals ORDER BY id DESC LIMIT 200"
            ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/bonds/deposit/reversal")
def reverse_deposit(body: DepositReversalIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    lock_key = f"bond:{body.party_key}"
    amount = round(float(body.amount), 6)
    if amount <= 0:
        raise HTTPException(400, "冲正金额须大于 0")

    # 偏航裁决先于一切：非甲口径只记偏航审计并拒写，不抢锁、不碰业务
    if not is_locked_path(body.path_mode):
        with connect() as dev_conn:
            write_audit(
                dev_conn,
                user,
                DEVIATION_AUDIT_ACTION,
                body.party_key,
                {
                    "requested_path": body.path_mode,
                    "locked_path": REVERSAL_PATH_LOCKED,
                    "deposit_id": body.deposit_id,
                    "amount": amount,
                    "reason": body.reason,
                    "note": "偏离入金冲正纪要，拒写",
                },
            )
            dev_conn.commit()
        raise HTTPException(400, "冲正偏航：本仓当日锁死甲路径（同事务回滚），影子晋升未启用")

    with connect() as conn:
        # 争用痕必须独立提交，否则随 409 回滚而消失
        if not try_acquire(conn, lock_key, user):
            conn.commit()
            raise HTTPException(409, "争用：后到只留争用痕，不写冲正业务")
        try:
            acct = conn.execute(
                "SELECT * FROM bond_accounts WHERE party_key=?",
                (body.party_key,),
            ).fetchone()
            if not acct:
                raise HTTPException(404, "保证金户不存在")
            if acct["status"] != "正常":
                raise HTTPException(409, "账户状态禁止冲正")

            deposit = conn.execute(
                "SELECT * FROM deposit_ledger WHERE id=?",
                (body.deposit_id,),
            ).fetchone()
            if not deposit or deposit["party_key"] != body.party_key:
                raise HTTPException(404, "关联入金流水不存在或不属于该当事人")
            if float(deposit["amount"]) <= 0:
                raise HTTPException(409, "该入金账不是正向入金，不可冲正")

            already = conn.execute(
                "SELECT COALESCE(SUM(amount),0) s FROM deposit_reversals WHERE deposit_id=?",
                (body.deposit_id,),
            ).fetchone()["s"]
            if float(already) + amount > float(deposit["amount"]) + 1e-9:
                raise HTTPException(409, "累计冲正超过该入金流水原额，整笔回滚")

            # 甲路径红线：扣后可用为负则整笔回滚——已冻结部分永不被误伤
            free_before = available_of(acct)
            if amount > free_before + 1e-9:
                raise HTTPException(409, "冲正额超过可用保证金，扣后可用将为负，整笔回滚")

            now = now_iso()
            stamp = now.replace("-", "").replace(":", "").replace("T", "-")
            ref = f"REV-DEP{body.deposit_id}-{stamp}-{uuid.uuid4().hex[:6]}"
            cur = conn.execute(
                """INSERT INTO deposit_reversals
                   (reversal_ref,party_key,deposit_id,amount,reason,path_mode,status,actor,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    ref,
                    body.party_key,
                    body.deposit_id,
                    amount,
                    body.reason,
                    REVERSAL_PATH_LOCKED,
                    REVERSAL_STATUS,
                    user,
                    now,
                ),
            )
            # 入金账负额冲正条：入金账可据此轧平
            conn.execute(
                """INSERT INTO deposit_ledger(party_key,amount,memo,created_at,actor)
                   VALUES (?,?,?,?,?)""",
                (body.party_key, -amount, f"入金冲正 {ref}", now, user),
            )
            # 只扣余额，frozen 不动
            conn.execute(
                "UPDATE bond_accounts SET balance = balance - ? WHERE party_key=?",
                (amount, body.party_key),
            )
            balance_before = round(float(acct["balance"]), 6)
            row = conn.execute(
                "SELECT * FROM bond_accounts WHERE party_key=?",
                (body.party_key,),
            ).fetchone()
            balance_after = round(float(row["balance"]), 6)
            write_audit(
                conn,
                user,
                REVERSAL_AUDIT_ACTION,
                ref,
                {
                    "reversal_id": cur.lastrowid,
                    "party_key": body.party_key,
                    "deposit_id": body.deposit_id,
                    "amount": amount,
                    "reason": body.reason,
                    "path_mode": REVERSAL_PATH_LOCKED,
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                    "frozen_untouched": round(float(row["frozen"]), 6),
                    "available_after": available_of(row),
                },
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "reversal_ref": ref,
                "party_key": body.party_key,
                "deposit_id": body.deposit_id,
                "amount": amount,
                "reason": body.reason,
                "path_mode": REVERSAL_PATH_LOCKED,
                "status": REVERSAL_STATUS,
                "actor": user,
                "created_at": now,
                "balance_before": balance_before,
                "balance_after": balance_after,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            release(conn, lock_key, user)
            conn.commit()
