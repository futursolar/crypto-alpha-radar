"""多链聪明钱 / 庄地址抓取（数据源：GMGN，覆盖 sol/eth/bsc/base/tron）。

两条路：
1) 无 key（主路径）: rank/{chain}/swaps/{period}?orderby=smartmoney
   -> 直接拿到"哪些代币正在被聪明钱买入"（核心 alpha 信号）。
2) 免费 key（gmgn.ai/ai 申请）: /user/smartmoney 聪明钱成交流 + token traders(tag=smart_degen)
   -> 直接拿到钱包地址，以及他们在买什么。

注：本沙箱直连不到 gmgn.ai，代码在你本机/VPS/GitHub Actions 里跑（那里能直连）。
端点结构来自 GMGN 官方 OpenAPI（GMGNAI/gmgn-skills）与开发者文档。
"""
from __future__ import annotations

import os
import time

import requests

BASE_URL = os.getenv("GMGN_BASE_URL", "https://gmgn.ai/defi/quotation/v1")
API_KEY = os.getenv("GMGN_API_KEY", "")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept": "application/json",
    "Referer": "https://gmgn.ai/",
})
if API_KEY:
    session.headers["Authorization"] = f"Bearer {API_KEY}"


def _get(path: str, params: dict | None = None) -> dict:
    """带重试/限流的 GET。返回解析后的 JSON，失败返回 {}。"""
    url = BASE_URL + path
    for attempt in range(3):
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 429:
                reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(5, reset - int(time.time()))
                print(f"[rate-limit] 等 {wait}s 后重试")
                time.sleep(min(wait, 300))
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("code") not in (0, None):
                print(f"[gmgn] code={data.get('code')} msg={data.get('message')}")
            return data
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                print(f"[gmgn] 请求失败 {url}: {e}")
                return {}
            time.sleep(2 ** attempt)
    return {}


def fetch_smartmoney_tokens(chain: str, period: str = "24h", limit: int = 50,
                            filters: list[str] | None = None) -> list[dict]:
    """无 key 主路径：按聪明钱活跃度排序拿代币列表。返回归一化 dict。"""
    params: dict = {
        "orderby": "smartmoney",
        "direction": "desc",
        "limit": limit,
    }
    for f in (filters or ["not_honeypot", "verified", "renounced"]):
        params[f"filters[]"] = f
    data = _get(f"/rank/{chain}/swaps/{period}", params)
    rank = (data.get("data") or {}).get("rank") or []
    out = []
    for t in rank:
        out.append({
            "chain": chain,
            "address": t.get("address") or t.get("token_address"),
            "symbol": t.get("symbol"),
            "name": t.get("name"),
            "price": t.get("price"),
            "market_cap": t.get("market_cap") or t.get("fdv"),
            "volume": t.get("volume"),
            "holder_count": t.get("holder_count"),
            "smart_buy": t.get("smart_buy_24h") or t.get("smart_buy"),
            "smart_sell": t.get("smart_sell_24h") or t.get("smart_sell"),
            "url": f"https://gmgn.ai/{chain}/token/{t.get('address')}",
        })
    return out


def fetch_smartmoney_feed(chain: str = "sol", limit: int = 50) -> list[dict]:
    """需 key：聪明钱成交流，直接给钱包地址 + 买入的代币。返回带 wallet 的记录。"""
    if not API_KEY:
        print("[smartmoney] 需要 GMGN_API_KEY 才能抓钱包地址，跳过（去 gmgn.ai/ai 免费申请）。")
        return []
    data = _get("/user/smartmoney", {"chain": chain, "limit": limit})
    return (data.get("data") or {}).get("trades") or (data.get("data") or {}).get("list") or []


def fetch_token_traders(chain: str, address: str, tag: str = "smart_degen",
                        limit: int = 20) -> list[str]:
    """需 key（或公开）：某代币的聪明钱/庄交易员钱包地址。tag=smart_degen|renowned。"""
    data = _get(f"/token/{chain}/{address}/traders",
                {"limit": limit, "tag": tag, "order_by": "amount_percentage", "direction": "desc"})
    traders = (data.get("data") or {}).get("traders") or (data.get("data") or {}).get("list") or []
    wallets = []
    for tr in traders:
        w = tr.get("wallet") or tr.get("address") or tr.get("trader")
        if w:
            wallets.append(w)
    return wallets


def capture_smart_money_wallets(chains: list[str], periods: list[str],
                                top_tokens: int = 5) -> dict[str, float]:
    """聚合：每条链/周期拿 smartmoney 代币 -> 取 top 代币的 traders(smart_degen)
    得到钱包地址集合与出现频次（频次越高越像庄/聪明钱）。
    无 key 时只能拿到代币级信号，拿不到地址——会明确提示。"""
    score: dict[str, float] = {}
    if not API_KEY:
        print("[capture] 无 GMGN_API_KEY：仅能抓到'代币级'聪明钱信号，抓不到钱包地址。")
        print("          去 https://gmgn.ai/ai 免费申请 key 后重跑即可抓地址。")
        return score
    for chain in chains:
        for period in periods:
            tokens = fetch_smartmoney_tokens(chain, period, limit=top_tokens)
            for tk in tokens:
                if not tk.get("address"):
                    continue
                wallets = fetch_token_traders(chain, tk["address"], tag="smart_degen")
                for w in wallets:
                    score[w] = score.get(w, 0.0) + 1.0
    return score
