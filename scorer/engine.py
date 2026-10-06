"""评分引擎：把聪明钱 + 社媒注意力 vs 市值 -> 0-100 分。

北星指标（贴合"亏小的、赚大的"）：
  注意力/聪明钱信号强 + 市值还低 + 流动性够 + 合约安全 = 高分。
"""
from __future__ import annotations


def score(token: dict, social: dict, weights: dict,
          min_mcap: float, max_mcap: float) -> dict:
    mcap = float(token.get("market_cap") or 0)
    smart_buy = float(token.get("smart_buy") or 0)
    smart_sell = float(token.get("smart_sell") or 0)
    volume = float(token.get("volume") or 0)

    # 1) 聪明钱比（买/卖，>=5 满分）
    sm_ratio = smart_buy / (smart_sell + 1)
    smart_money_score = min(sm_ratio / 5, 1.0) * 100

    # 2) 注意力 vs 市值（市值越低、注意力越高 -> 越高）
    if mcap > 0:
        att_vs_mcap = social.get("attention_proxy", 0) / (mcap / 1_000_000 + 1)
    else:
        att_vs_mcap = 0
    att_score = min(att_vs_mcap / 3, 1.0) * 100

    # 3) 量能突增
    vol_surge = volume / mcap if mcap else 0
    vol_score = min(vol_surge / 2, 1.0) * 100

    # 4) 安全（rank 已过滤 not_honeypot/verified/renounced，默认满分）
    safety_score = 100.0

    total = (
        weights["smart_money_ratio"] * smart_money_score
        + weights["attention_vs_mcap"] * att_score
        + weights["volume_surge"] * vol_score
        + weights["safety"] * safety_score
    )
    return {
        "score": round(total, 1),
        "breakdown": {
            "smart_money": round(smart_money_score, 1),
            "attention_vs_mcap": round(att_score, 1),
            "volume_surge": round(vol_score, 1),
            "safety": round(safety_score, 1),
        },
    }
