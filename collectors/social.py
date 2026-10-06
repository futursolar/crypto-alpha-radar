"""社媒 / 注意力趋势分析：回答"为什么涨"。

免费代理指标（无需 key）：聪明钱买卖比 + 成交量突增 + 小市值 + holder 基础。
真·社媒量：LunarCrush Galaxy Score（需 key，可选）。
"""
from __future__ import annotations

import os

import requests

LUNACRUSH_KEY = os.getenv("LUNARCRUSH_API_KEY", "")
BASE = "https://lunarcrush.com/api4"


def _lunarcrush_galaxy(symbol: str) -> float | None:
    if not LUNACRUSH_KEY or not symbol:
        return None
    try:
        r = requests.get(f"{BASE}/public/coins/{symbol}/time-series/v1",
                         params={"key": LUNACRUSH_KEY, "data": "galaxy_score"},
                         timeout=20)
        j = r.json()
        items = (j.get("data") or {}).get("data") or []
        return float(items[0].get("galaxy_score")) if items else None
    except Exception as e:  # noqa: BLE001
        print(f"[social] lunarcrush 失败: {e}")
        return None


def analyze(chain: str, token: dict) -> dict:
    reasons: list[str] = []
    smart_buy = float(token.get("smart_buy") or 0)
    smart_sell = float(token.get("smart_sell") or 0)
    mcap = float(token.get("market_cap") or 0)
    volume = float(token.get("volume") or 0)
    holders = float(token.get("holder_count") or 0)

    sm_ratio = smart_buy / (smart_sell + 1)
    if sm_ratio >= 3:
        reasons.append(f"聪明钱净买入强（买{smart_buy}/卖{smart_sell}，比{sm_ratio:.1f}）")
    elif sm_ratio > 1:
        reasons.append(f"聪明钱小幅净流入（买{smart_buy}/卖{smart_sell}）")

    vol_mcap = volume / mcap if mcap else 0
    if vol_mcap >= 1:
        reasons.append(f"量能突增（量/市值={vol_mcap:.1f}）")
    elif vol_mcap >= 0.3:
        reasons.append(f"成交量中等（量/市值={vol_mcap:.2f}）")

    if 0 < mcap < 300000:
        reasons.append(f"小市值（${mcap / 1000:.0f}K），注意力未充分定价")

    if holders >= 300:
        reasons.append(f"holder {holders:.0f}，有社区基础")

    attention_proxy = sm_ratio * 10 + vol_mcap * 20 + (15 if 0 < mcap < 300000 else 0)
    galaxy = _lunarcrush_galaxy(token.get("symbol"))
    if galaxy is not None:
        reasons.append(f"LunarCrush Galaxy={galaxy:.0f}")
        attention_proxy = max(attention_proxy, galaxy)

    return {
        "attention_proxy": round(attention_proxy, 2),
        "reasons": reasons,
    }
