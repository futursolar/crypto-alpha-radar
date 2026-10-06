"""编排：多链抓聪明钱代币 -> 过滤 -> 评分 -> 社媒分析 -> 去重 -> 邮箱推送。

用法:
  python main.py                 # 全链、按 settings.json 跑，达到阈值推邮箱
  python main.py --dry-run       # 只打印不推送
  python main.py --chain sol eth # 只跑指定链
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import collectors.smart_money as sm  # noqa: E402
import collectors.social as social  # noqa: E402
import scorer.engine as engine  # noqa: E402
import scorer.jev_scorer as jev_scorer  # noqa: E402
import alerts.email_sender as email_sender  # noqa: E402
import storage.store as store  # noqa: E402

SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
SCORER = jev_scorer.JevScorer(SETTINGS)  # 无 TYPESAFE_API_KEY 时 available=False，自动降级


def run(dry_run: bool = False, chains: list[str] | None = None) -> None:
    chains = chains or SETTINGS["chains"]
    periods = SETTINGS["periods"]
    seen = store.load()
    alerts: list[dict] = []

    if SCORER.available:
        print(f"[main] Jev 裁决已启用（model={SCORER.model}, 门控={SCORER.allow_verdicts}, "
              f"min_conf={SCORER.min_confidence}）")
    else:
        print("[main] Jev 未启用/无 key：使用启发式引擎（仅达阈值即推送）")

    for chain in chains:
        for period in periods:
            tokens = sm.fetch_smartmoney_tokens(
                chain, period, limit=SETTINGS["rank_limit"], filters=SETTINGS["filters"])
            for tk in tokens:
                addr = tk.get("address")
                if not addr:
                    continue
                mcap = float(tk.get("market_cap") or 0)
                if mcap < SETTINGS["min_market_cap"] or mcap > SETTINGS["max_market_cap"]:
                    continue
                if float(tk.get("smart_buy") or 0) < SETTINGS["min_smart_buy"]:
                    continue
                if not store.is_new(seen, chain, addr):
                    continue
                soc = social.analyze(chain, tk)
                sc = engine.score(tk, soc, SETTINGS["scoring"]["weights"],
                                  SETTINGS["min_market_cap"], SETTINGS["max_market_cap"])
                if sc["score"] < SETTINGS["scoring"]["alert_threshold"]:
                    continue
                # Jev 最终裁决（若启用且有 key）
                jr = None
                if SCORER.available:
                    jr = SCORER.score(tk, soc, SETTINGS)
                    if jr is None:
                        continue  # 调用失败，保守丢弃，避免误报
                    if jr["decision"] != "pass":
                        continue  # Jev 说 avoid 或置信度不足
                alerts.append({"token": tk, "social": soc, "score": sc, "jev": jr})
                store.mark(seen, chain, addr, sc["score"])

    store.save(seen)
    if not alerts:
        print("[main] 本轮无达到阈值的信号。")
        return
    alerts.sort(key=lambda x: x["score"]["score"], reverse=True)
    print(f"[main] 命中 {len(alerts)} 个信号：")
    for a in alerts:
        jev_txt = (f" jev={a['jev']['verdict']}(conf={a['jev']['confidence']},"
                   f"conv={a['jev']['conviction']})") if a["jev"] else ""
        print(f"  {a['token']['chain']} {a['token']['symbol']} "
              f"分={a['score']['score']}{jev_txt} 原因={a['social']['reasons']}")
    if not dry_run:
        email_sender.send(alerts, SETTINGS["email"])


def main() -> None:
    p = argparse.ArgumentParser(description="多链聪明钱 + 社媒确定性雷达")
    p.add_argument("--dry-run", action="store_true", help="只打印不推送邮箱")
    p.add_argument("--chain", nargs="*", help="只跑指定链，如 sol eth")
    args = p.parse_args()
    run(dry_run=args.dry_run, chains=args.chain)


if __name__ == "__main__":
    main()
