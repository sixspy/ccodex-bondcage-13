"""入金冲正：假绿事故夹具 + 两条必须先红的失败测。

纪律（docs/入金冲正纪要_2026-11-22.md）：
1. 先造「错入金无法冲正」的假绿事故夹具；
2. 冲正无效失败测、双人同冲正争用失败测先红；
3. 见红后才准改账户/对账/审计/入笼服务与账户页。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from db import FIXTURES, connect, init_db

INCIDENT = json.loads(
    (Path(FIXTURES) / "incident_wrong_deposit.json").read_text(encoding="utf-8")
)[0]


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "t.db")
    init_db()
    yield


def _auth(c: TestClient, user: str = "admin") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": "123456"}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _build_incident(c: TestClient, h: dict) -> int:
    """复刻假绿事故：真实入金 240000，错记 80000 虚高，随后两笼建立在错数上。"""
    party = INCIDENT["party_key"]
    r = c.post(
        "/api/bonds",
        headers=h,
        json={
            "party_key": party,
            "party_name": INCIDENT["party_name"],
            "initial_deposit": INCIDENT["real_balance"],
        },
    )
    assert r.status_code == 200
    r = c.post(
        "/api/bonds/deposit",
        headers=h,
        json={
            "party_key": party,
            "amount": INCIDENT["wrong_deposit"],
            "memo": "错入金-虚高80000",
        },
    )
    assert r.status_code == 200
    # 后续入笼都建立在错数上：冻结 150000
    for idx, amt in enumerate((90000, 60000), start=1):
        fr = c.post(
            "/api/cages/freeze",
            headers=h,
            json={
                "party_key": party,
                "contract_no": f"HT-INC-{idx}",
                "amount": amt,
                "beneficiary": "事故受益人",
                "cage_code": f"CG-INC-{idx:03d}",
            },
        )
        assert fr.status_code == 200
    detail = c.get(f"/api/bonds/{party}", headers=h).json()
    acct = detail["account"]
    assert acct["balance"] == INCIDENT["booked_balance"]
    assert acct["frozen"] == INCIDENT["frozen"]
    wrong = next(d for d in detail["deposits"] if d["memo"] == "错入金-虚高80000")
    return wrong["id"]


def test_incident_fixture_is_fake_green_without_reversal_path():
    """事故夹具：账面对账全绿，却没有任何冲正写口（404），只能私下改库。"""
    c = TestClient(app)
    h = _auth(c)
    _build_incident(c, h)
    # 既有笼口径对账仍是绿的——假绿
    recon = c.get("/api/reconcile", headers=h).json()
    assert recon["summary"]["unbalanced"] == 0
    # 冲正写口不存在
    r = c.post(
        "/api/bonds/deposit/reversal",
        headers=h,
        json={
            "party_key": INCIDENT["party_key"],
            "deposit_id": 1,
            "amount": INCIDENT["wrong_deposit"],
            "reason": "冲正错入金",
            "path_mode": "A_same_txn",
        },
    )
    assert r.status_code == 404


def test_reversal_a_path_restores_balance_and_protects_frozen():
    """红测①：甲路径冲正无效——余额无法回正（端点尚不存在）。"""
    c = TestClient(app)
    h = _auth(c)
    wrong_id = _build_incident(c, h)
    party = INCIDENT["party_key"]

    r = c.post(
        "/api/bonds/deposit/reversal",
        headers=h,
        json={
            "party_key": party,
            "deposit_id": wrong_id,
            "amount": INCIDENT["wrong_deposit"],
            "reason": "入金金额记错，全额冲正",
            "path_mode": "A_same_txn",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "已冲正"
    assert body["path_mode"] == "A_same_txn"
    assert body["balance_before"] == INCIDENT["booked_balance"]
    assert body["balance_after"] == INCIDENT["real_balance"]

    detail = c.get(f"/api/bonds/{party}", headers=h).json()
    acct = detail["account"]
    # 余额回正
    assert acct["balance"] == INCIDENT["real_balance"]
    # 已冻结部分不被误伤
    assert acct["frozen"] == INCIDENT["frozen"]
    assert acct["balance"] - acct["frozen"] == 90000
    # 冲正流水：专表一条 + 入金账一条负额
    with connect() as conn:
        rev = conn.execute(
            "SELECT * FROM deposit_reversals WHERE party_key=? ORDER BY id",
            (party,),
        ).fetchall()
        assert len(rev) == 1
        assert rev[0]["amount"] == INCIDENT["wrong_deposit"]
        assert rev[0]["deposit_id"] == wrong_id
        neg = conn.execute(
            "SELECT * FROM deposit_ledger WHERE party_key=? AND amount < 0", (party,)
        ).fetchall()
        assert len(neg) == 1
        assert abs(neg[0]["amount"]) == INCIDENT["wrong_deposit"]
        assert rev[0]["reversal_ref"] in neg[0]["memo"]
        audit = conn.execute(
            "SELECT * FROM audit_trail WHERE action='deposit_reversal' ORDER BY id"
        ).fetchall()
        assert len(audit) == 1
    # 笼与对账不受影响，仍全绿
    recon = c.get("/api/reconcile", headers=h).json()
    assert recon["summary"]["unbalanced"] == 0
    proof = c.get(f"/api/proof/{party}", headers=h).json()
    assert proof["frozen_matches_live"] is True
    # 账户侧轧平：净入金 − 拨付 − 罚没 == 余额
    assert proof["balance_identity_ok"] is True
    assert proof["net_deposit"] == INCIDENT["real_balance"]

    # 扣后可用为负：整笔回滚，余额零改
    before = c.get(f"/api/bonds/{party}", headers=h).json()["account"]["balance"]
    bad = c.post(
        "/api/bonds/deposit/reversal",
        headers=h,
        json={
            "party_key": party,
            "deposit_id": wrong_id,
            "amount": before - INCIDENT["frozen"] + 1,
            "reason": "超额冲正应回滚",
            "path_mode": "A_same_txn",
        },
    )
    assert bad.status_code == 409
    after = c.get(f"/api/bonds/{party}", headers=h).json()["account"]
    assert after["balance"] == before
    assert after["frozen"] == INCIDENT["frozen"]
    with connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) c FROM deposit_reversals WHERE party_key=?", (party,)
        ).fetchone()["c"] == 1

    # 同一入金流水累计冲正不得超过原额：第二次全额 → 409 回滚
    again = c.post(
        "/api/bonds/deposit/reversal",
        headers=h,
        json={
            "party_key": party,
            "deposit_id": wrong_id,
            "amount": 1,
            "reason": "超额累计冲正",
            "path_mode": "A_same_txn",
        },
    )
    assert again.status_code == 409

    # 偏航：指定乙路径（影子晋升）→ 记偏航审计并拒写，余额零改
    dev = c.post(
        "/api/bonds/deposit/reversal",
        headers=h,
        json={
            "party_key": party,
            "deposit_id": wrong_id,
            "amount": 1,
            "reason": "试图走影子单",
            "path_mode": "B_shadow_promote",
        },
    )
    assert dev.status_code == 400
    with connect() as conn:
        dev_rows = conn.execute(
            "SELECT * FROM audit_trail WHERE action='deposit_reversal_deviation'"
        ).fetchall()
        assert len(dev_rows) == 1
        assert conn.execute(
            "SELECT COUNT(*) c FROM deposit_reversals"
        ).fetchone()["c"] == 1
    final = c.get(f"/api/bonds/{party}", headers=h).json()["account"]
    assert final["balance"] == INCIDENT["real_balance"]
    assert final["frozen"] == INCIDENT["frozen"]


def test_concurrent_reversal_only_one_wins_with_contention_trace():
    """红测②：双人同冲正同一当事人——抢账户锁，后到只留争用痕、零业务写。"""
    c = TestClient(app)
    h1 = _auth(c, "admin")
    h2 = _auth(c, "clerk")
    wrong_id = _build_incident(c, h1)
    party = INCIDENT["party_key"]

    # 确定性争用：admin 持账户锁，clerk 冲正必须 409 且只留争用痕
    held = c.post(
        "/api/locks/acquire", headers=h1, json={"lock_key": f"bond:{party}"}
    )
    assert held.status_code == 200
    blocked = c.post(
        "/api/bonds/deposit/reversal",
        headers=h2,
        json={
            "party_key": party,
            "deposit_id": wrong_id,
            "amount": INCIDENT["wrong_deposit"],
            "reason": "后到冲正",
            "path_mode": "A_same_txn",
        },
    )
    assert blocked.status_code == 409
    with connect() as conn:
        traces = conn.execute(
            "SELECT * FROM contention_log WHERE lock_key=? AND actor='clerk'",
            (f"bond:{party}",),
        ).fetchall()
        assert len(traces) == 1
        # 后到者零业务写
        assert conn.execute(
            "SELECT COUNT(*) c FROM deposit_reversals"
        ).fetchone()["c"] == 0
        acct = conn.execute(
            "SELECT * FROM bond_accounts WHERE party_key=?", (party,)
        ).fetchone()
        assert acct["balance"] == INCIDENT["booked_balance"]
        assert acct["frozen"] == INCIDENT["frozen"]
    c.post(
        "/api/locks/release", headers=h1, json={"lock_key": f"bond:{party}"}
    )

    # 真实并发：两人同时全额冲正，恰一人成功，另一人 409 争用
    barrier = threading.Barrier(2)
    outcomes: list[tuple[str, int]] = []

    def worker(user: str) -> None:
        cc = TestClient(app)
        hh = _auth(cc, user)
        barrier.wait()
        rr = cc.post(
            "/api/bonds/deposit/reversal",
            headers=hh,
            json={
                "party_key": party,
                "deposit_id": wrong_id,
                "amount": INCIDENT["wrong_deposit"],
                "reason": f"{user}并发冲正",
                "path_mode": "A_same_txn",
            },
        )
        outcomes.append((user, rr.status_code))

    t1 = threading.Thread(target=worker, args=("admin",))
    t2 = threading.Thread(target=worker, args=("clerk",))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert sorted(s for _, s in outcomes) == [200, 409]
    with connect() as conn:
        revs = conn.execute(
            "SELECT * FROM deposit_reversals WHERE party_key=?", (party,)
        ).fetchall()
        assert len(revs) == 1
        acct = conn.execute(
            "SELECT * FROM bond_accounts WHERE party_key=?", (party,)
        ).fetchone()
        # 只扣了一次虚高额，冻结原样
        assert acct["balance"] == INCIDENT["real_balance"]
        assert acct["frozen"] == INCIDENT["frozen"]
        cont = conn.execute(
            "SELECT COUNT(*) c FROM contention_log WHERE lock_key=?",
            (f"bond:{party}",),
        ).fetchone()["c"]
        assert cont >= 1
