"""账号登录状态定义与状态机。

状态语义：

| 状态 | 含义 |
| --- | --- |
| `unknown` | 尚未检测（刚导入或服务重启后的初始态） |
| `logging_in` | 正在登录中（其它请求应等待，不要重复登录） |
| `active` | 已登录，会话可用 |
| `expired` | 会话已过期（收到 401），需要重新登录 |
| `error` | 登录失败（密码错误、风控、网络异常等） |

状态迁移：

    unknown ──登录开始──▶ logging_in ──成功──▶ active
                             │                  │
                             └──失败──▶ error   ├──收到401──▶ expired
                                                │                │
                                                └────────────────┘
                                                     重新登录
"""

from __future__ import annotations

UNKNOWN = "unknown"
LOGGING_IN = "logging_in"
ACTIVE = "active"
EXPIRED = "expired"
ERROR = "error"

ALL_STATES = (UNKNOWN, LOGGING_IN, ACTIVE, EXPIRED, ERROR)

# 会话可用的状态（可直接复用令牌）
USABLE_STATES = (ACTIVE,)

# 需要重新登录的状态
NEEDS_LOGIN_STATES = (UNKNOWN, EXPIRED, ERROR)

_STATE_TEXT = {
    UNKNOWN: "未检测",
    LOGGING_IN: "登录中",
    ACTIVE: "登录成功",
    EXPIRED: "登录过期",
    ERROR: "登录失败",
}


def state_text(state: str) -> str:
    """状态的中文描述。"""
    return _STATE_TEXT.get(state, state)


def can_use_session(state: str) -> bool:
    return state in USABLE_STATES


def needs_login(state: str) -> bool:
    return state in NEEDS_LOGIN_STATES
