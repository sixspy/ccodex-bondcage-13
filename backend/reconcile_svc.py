"""对账互证：笼面可用 + 已拨付 + 已罚没 须等于笼面金额（同代口径）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from db import available_of, connect

router = APIRouter(tags=["reconcile"])

LIVE_CAGE_STATUS = (
    "已冻结",
    "核验通过",
    "核验违约",
    "部分解笼",
    "部分罚没",
)


def _account_reconcile(conn, party_key: str) -> dict:
    """账户侧轧平：净入金（含负额冲正）− 已拨付 − 已罚没 == 账面余额；冻结 == 活笼可用。"""
    acct = conn.execute(
        "SELECT * FROM bond_accounts WHERE party_key=?", (party_key,)
    ).fetchone()
    if not acct:
        raise HTTPException(404, "保证金户不存在")
    gross_deposit = conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM deposit_ledger WHERE party_key=? AND amount>0",
        (party_key,),
    ).fetchone()["s"]
    reversed_total = conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM deposit_reversals WHERE party_key=?",
        (party_key,),
    ).fetchone()["s"]
    net_deposit = conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM deposit_ledger WHERE party_key=?",
        (party_key,),
    ).fetchone()["s"]
    released = conn.execute(
        """SELECT COALESCE(SUM(r.amount),0) s FROM releases r
           JOIN cages c ON c.id=r.cage_id
           WHERE c.party_key=? AND r.status='已拨付'""",
        (party_key,),
    ).fetchone()["s"]
    forfeited = conn.execute(
        """SELECT COALESCE(SUM(f.amount),0) s FROM forfeits f
           JOIN cages c ON c.id=f.cage_id
           WHERE c.party_key=? AND f.status='已罚没'""",
        (party_key,),
    ).fetchone()["s"]
    live_frozen = conn.execute(
        """SELECT COALESCE(SUM(available),0) s FROM cages
           WHERE party_key=? AND status IN (?,?,?,?,?)""",
        (party_key, *LIVE_CAGE_STATUS),
    ).fetchone()["s"]
    balance = float(acct["balance"])
    frozen = float(acct["frozen"])
    identity_left = round(float(net_deposit) - float(released) - float(forfeited), 6)
    balance_identity_ok = abs(identity_left - round(balance, 6)) < 1e-6
    frozen_matches = abs(frozen - float(live_frozen)) < 1e-6
    return {
        "party_key": party_key,
        "account": dict(acct),
        "available": available_of(acct),
        "gross_deposit": float(gross_deposit),
        "reversed_total": float(reversed_total),
        "net_deposit": float(net_deposit),
        "released_total": float(released),
        "forfeited_total": float(forfeited),
        "balance_identity_left": identity_left,
        "balance_identity_right": round(balance, 6),
        "balance_identity_ok": balance_identity_ok,
        "account_frozen": frozen,
        "live_cage_available": float(live_frozen),
        "frozen_matches_live": frozen_matches,
        "balanced": balance_identity_ok and frozen_matches,
        "proof": {
            "balance_formula": "净入金(入金−冲正) − 已拨付 − 已罚没 == 账户余额",
            "frozen_formula": "账户冻结 == 活笼可用合计",
        },
    }


def _reconcile_cage(conn, cage) -> dict:
    cage_id = cage["id"]
    gen = int(cage["generation"])
    amount = float(cage["amount"])
    available = float(cage["available"])
    released = conn.execute(
        """SELECT COALESCE(SUM(amount),0) s FROM releases
           WHERE cage_id=? AND status='已拨付' AND cage_generation=?""",
        (cage_id, gen),
    ).fetchone()["s"]
    forfeited = conn.execute(
        """SELECT COALESCE(SUM(amount),0) s FROM forfeits
           WHERE cage_id=? AND status='已罚没' AND cage_generation=?""",
        (cage_id, gen),
    ).fetchone()["s"]
    accounted = round(float(available) + float(released) + float(forfeited), 6)
    ok = abs(accounted - amount) < 1e-6
    # 账户侧：该当事人冻结额应覆盖所有仍冻结/核验中的笼可用
    party = cage["party_key"]
    acct = conn.execute(
        "SELECT balance, frozen FROM bond_accounts WHERE party_key=?",
        (party,),
    ).fetchone()
    live_frozen = conn.execute(
        """SELECT COALESCE(SUM(available),0) s FROM cages
           WHERE party_key=? AND status IN (?,?,?,?,?)""",
        (party, *LIVE_CAGE_STATUS),
    ).fetchone()["s"]
    return {
        "cage_id": cage_id,
        "cage_code": cage["cage_code"],
        "party_key": party,
        "contract_no": cage["contract_no"],
        "generation": gen,
        "status": cage["status"],
        "amount": amount,
        "available": available,
        "released": float(released),
        "forfeited": float(forfeited),
        "accounted": accounted,
        "balanced": ok,
        "gap": round(amount - accounted, 6),
        "account_balance": float(acct["balance"]) if acct else None,
        "account_frozen": float(acct["frozen"]) if acct else None,
        "live_cage_available": float(live_frozen),
        "proof": {
            "formula": "available + released + forfeited == amount（同笼代）",
            "left": accounted,
            "right": amount,
        },
    }


@router.get("/api/reconcile")
def reconcile_all(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        cages = conn.execute("SELECT * FROM cages ORDER BY id").fetchall()
        items = [_reconcile_cage(conn, c) for c in cages]
        bad = [i for i in items if not i["balanced"]]
        return {
            "items": items,
            "summary": {
                "total": len(items),
                "balanced": len(items) - len(bad),
                "unbalanced": len(bad),
            },
        }


@router.get("/api/reconcile/{cage_code}")
def reconcile_one(cage_code: str, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        cage = conn.execute(
            "SELECT * FROM cages WHERE cage_code=?", (cage_code,)
        ).fetchone()
        if not cage:
            raise HTTPException(404, "笼不存在")
        return _reconcile_cage(conn, cage)


@router.get("/api/reconcile/accounts/{party_key}")
def reconcile_account(party_key: str, authorization: AuthHeader = None):
    """账户侧轧平：冲正后余额回正、冻结不被误伤的同源证据。"""
    require_user(authorization)
    with connect() as conn:
        return _account_reconcile(conn, party_key)


@router.get("/api/proof/{party_key}")
def party_proof(party_key: str, authorization: AuthHeader = None):
    """当事人级互证：账户冻结 vs 活笼可用 + 余额轧平式（含冲正）。"""
    require_user(authorization)
    with connect() as conn:
        rec = _account_reconcile(conn, party_key)
        return {
            "party_key": party_key,
            "account": rec["account"],
            "live_cage_available": rec["live_cage_available"],
            "released_total": rec["released_total"],
            "forfeited_total": rec["forfeited_total"],
            "frozen_matches_live": rec["frozen_matches_live"],
            "gross_deposit": rec["gross_deposit"],
            "reversed_total": rec["reversed_total"],
            "net_deposit": rec["net_deposit"],
            "balance_identity_ok": rec["balance_identity_ok"],
            "proof": {
                "formula": "account.frozen == sum(live cage available)",
                "left": rec["account_frozen"],
                "right": rec["live_cage_available"],
                "balance_formula": rec["proof"]["balance_formula"],
                "balance_left": rec["balance_identity_left"],
                "balance_right": rec["balance_identity_right"],
            },
        }
