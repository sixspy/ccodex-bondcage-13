"""入金冲正口径裁决（当日锁死，唯一来源）。

锁死结论见 docs/入金冲正纪要_2026-11-22.md：
只启用甲路径 A_same_txn（同事务写冲正流水+扣余额+审计，扣后可用为负整笔回滚）。
乙路径 B_shadow_promote 不实现；任何非甲口径请求记冲正偏航并拒写。
"""
from __future__ import annotations

from db import PRODUCT_META

# 当日锁死的唯一正确性口径
REVERSAL_PATH_LOCKED = PRODUCT_META["deposit_reversal"]["locked_path"]  # A_same_txn
REVERSAL_PATH_LABELS = {
    "A_same_txn": "甲路径·同事务回滚",
    "B_shadow_promote": "乙路径·影子冲正单晋升（未启用）",
}
# 偏航审计动作名；偏离纪要的请求只落此痕，不落业务
DEVIATION_AUDIT_ACTION = "deposit_reversal_deviation"
REVERSAL_AUDIT_ACTION = "deposit_reversal"
REVERSAL_STATUS = "已冲正"


def is_locked_path(path_mode: str | None) -> bool:
    return path_mode == REVERSAL_PATH_LOCKED


def policy_snapshot() -> dict:
    """供五页同源展示：页面只读接口返回，不允许自选口径。"""
    return {
        "locked_path": REVERSAL_PATH_LOCKED,
        "locked_label": REVERSAL_PATH_LABELS[REVERSAL_PATH_LOCKED],
        "locked_date": PRODUCT_META["deposit_reversal"]["locked_date"],
        "memo": PRODUCT_META["deposit_reversal"]["memo"],
        "shadow_enabled": False,
    }
