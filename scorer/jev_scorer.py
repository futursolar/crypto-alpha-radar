"""Jev 评分模块：用 TypeSafe 的 Jev (System One) 决策模型做最终裁决。

设计原则（贴合"亏小的、赚大的"）：
  - Jev 不是涨跌预测器（TradeRank 142天回测：方向命中率 ~0.49，且过度自信），
    强项是「对结构化特征做分类/判断」。所以这里只让它做：
      1) verdict：ape / watch / avoid（吃还是看还是躲）
      2) conviction：0-10 置信强度
      3) high_conviction：是不是高确定性机会（0~1 概率）
  - 它当「过滤器/评级器」，不当水晶球。代码负责算特征，Jev 负责判。
  - 无 TYPESAFE_API_KEY 时 available=False，main 自动降级回启发式引擎，不报错。
  - 非确定性（同请求概率差可达 0.07），可配 n_samples 多次取平均。

端点（多源实测 2026-09）：POST https://api.typesafe.ai/v1/systemone
Auth: Bearer $TYPESAFE_API_KEY
"""
from __future__ import annotations

import os
import time

import requests

DEFAULT_BASE_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-1.13.0"  # 固定版本，不用 latest（别名会变，破坏可复现）


def _bucket_mcap(mcap: float) -> str:
    if mcap <= 0:
        return "unknown"
    if mcap < 100_000:
        return "micro (<100k)"
    if mcap < 1_000_000:
        return "small (100k-1m)"
    if mcap < 5_000_000:
        return "mid (1m-5m)"
    return "large (>5m)"


def _social_label(social: dict) -> str:
    """把社媒注意力 vs 市值 翻成英文 label（Jev 英文最佳）。"""
    att = float(social.get("attention_proxy") or 0)
    if att >= 2:
        return "social_attention_leading_mcap_flat"  # 注意力起、市值没动 = 背离早期
    if att >= 1:
        return "social_attention_rising"
    if att > 0:
        return "neutral"
    return "social_quiet"


class JevScorer:
    def __init__(self, settings: dict):
        jev_cfg = settings.get("jev", {})
        self.enabled = bool(jev_cfg.get("enabled", False))
        self.model = jev_cfg.get("model", DEFAULT_MODEL)
        self.base_url = os.getenv("JEV_BASE_URL") or jev_cfg.get("base_url", DEFAULT_BASE_URL)
        self.min_confidence = float(jev_cfg.get("min_confidence", 0.7))
        self.allow_verdicts = jev_cfg.get("allow_verdicts", ["ape", "watch"])
        self.n_samples = int(jev_cfg.get("n_samples", 1))
        self.timeout = int(jev_cfg.get("timeout_seconds", 20))
        self.api_key = os.getenv("TYPESAFE_API_KEY", "")
        # 没有 key 就不可用，main 会降级；不抛异常。
        self.available = bool(self.api_key) and self.enabled

    # ------------------------------------------------------------------
    def _build_state(self, token: dict, social: dict) -> dict:
        mcap = float(token.get("market_cap") or 0)
        smart_buy = float(token.get("smart_buy") or 0)
        smart_sell = float(token.get("smart_sell") or 0)
        volume = float(token.get("volume") or 0)
        sm_ratio = smart_buy / (smart_sell + 1)
        vol_surge = volume / mcap if mcap else 0
        att_vs_mcap = (float(social.get("attention_proxy") or 0) / (mcap / 1_000_000 + 1)) if mcap else 0
        contract = "verified_renounced" if "renounced" in (token.get("tags", []) or []) else (
            "verified" if token.get("verified") else "unverified")
        return {
            "chain": token.get("chain", ""),
            "symbol": token.get("symbol", ""),
            "market_cap_usd": round(mcap, 2),
            "market_cap_tier": _bucket_mcap(mcap),
            "smart_buy": smart_buy,
            "smart_sell": smart_sell,
            "smart_buy_ratio": round(sm_ratio, 3),
            "volume_usd": round(volume, 2),
            "volume_to_mcap": round(vol_surge, 3),
            "attention_vs_mcap": round(att_vs_mcap, 3),
            "social_signal": _social_label(social),
            "contract_status": contract,
        }

    def _questions(self) -> dict:
        return {
            "verdict": {
                "type": "choice",
                "instructions": (
                    "Given this token's on-chain smart-money flow, social attention vs "
                    "market cap, liquidity and contract status, which action fits best?"
                ),
                "criteria": {
                    "ape": "Strong, high-conviction setup worth buying now (smart money buying, social leading mcap, safe contract, decent liquidity).",
                    "watch": "Interesting but not yet actionable; monitor for confirmation.",
                    "avoid": "Weak or risky: low/negative smart money, no social edge, thin liquidity, or unsafe contract.",
                },
            },
            "conviction": {
                "type": "score",
                "instructions": "How strong is the overall setup conviction, from weakest to exceptional?",
                "criteria": [
                    "very weak", "weak", "below average", "neutral", "above average",
                    "good", "strong", "very strong", "high", "very high", "exceptional",
                ],
            },
            "high_conviction": {
                "type": "noul",
                "instructions": "Is this a high-conviction setup worth acting on right now?",
                "criteria": {"true": "high conviction", "false": "not high conviction"},
            },
        }

    def _call_once(self, state: dict) -> dict:
        """单次调用 System One，含 429/529 指数退避（最多 4 次）。"""
        payload = {"model": self.model, "state": state, "questions": self._questions()}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        backoff = 1.0
        for attempt in range(4):
            try:
                r = requests.post(self.base_url, json=payload, headers=headers, timeout=self.timeout)
            except requests.RequestException as e:
                raise RuntimeError(f"Jev 请求异常: {e}") from e
            if r.status_code == 401:
                raise RuntimeError("Jev 401: API key 无效（检查 TYPESAFE_API_KEY）")
            if r.status_code == 422:
                raise RuntimeError(f"Jev 422: 请求格式错误 {r.text[:300]}")
            if r.status_code in (429, 529):
                if attempt == 3:
                    raise RuntimeError(f"Jev 限流/过载 {r.status_code}，重试耗尽")
                time.sleep(backoff)
                backoff *= 2
                continue
            if r.status_code != 200:
                raise RuntimeError(f"Jev 意外状态码 {r.status_code}: {r.text[:300]}")
            return r.json()
        raise RuntimeError("Jev 调用失败（不应到达此处）")

    def score(self, token: dict, social: dict, settings: dict | None = None) -> dict | None:
        """返回 Jev 裁决；不可用或调用失败返回 None（main 据此降级/丢弃）。"""
        if not self.available:
            return None
        state = self._build_state(token, social)
        samples = []
        for _ in range(max(1, self.n_samples)):
            try:
                samples.append(self._call_once(state))
            except RuntimeError as e:
                # 单次失败：保守处理，本轮回退该 token，避免误报
                print(f"[jev] 调用失败，丢弃该 token：{e}")
                return None
        # 多次取平均
        verdict_probs: dict[str, float] = {}
        conv_sum = 0.0
        conf_sum = 0.0
        hc_sum = 0.0
        for resp in samples:
            ans = resp.get("answers", {})
            vp = ans.get("verdict", {}).get("probabilities", {})
            for k, v in vp.items():
                verdict_probs[k] = verdict_probs.get(k, 0.0) + v
            conv = ans.get("conviction", {})
            # score = Σ level * prob on 0..max scale
            probs = conv.get("probabilities", {})
            lvl = 0
            s = 0.0
            for _lvl_txt, p in probs.items():
                s += lvl * p
                lvl += 1
            conv_sum += s
            conf_sum += float(conv.get("confidence", 0.0))
            hc_sum += float(ans.get("high_conviction", {}).get("noul", 0.0))
        n = len(samples)
        for k in verdict_probs:
            verdict_probs[k] /= n
        verdict = max(verdict_probs, key=verdict_probs.get)
        confidence = verdict_probs[verdict]
        conviction = round(conv_sum / n, 2)
        high_conviction = round(hc_sum / n, 3)
        avg_conf = round(conf_sum / n, 3)
        decision = "pass" if (verdict in self.allow_verdicts and avg_conf >= self.min_confidence) else "drop"
        return {
            "available": True,
            "model": self.model,
            "verdict": verdict,
            "verdict_probs": {k: round(v, 3) for k, v in verdict_probs.items()},
            "conviction": conviction,
            "confidence": round(confidence, 3),
            "avg_confidence": avg_conf,
            "high_conviction": high_conviction,
            "decision": decision,
            "state": state,
        }
