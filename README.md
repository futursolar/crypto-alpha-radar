# crypto-alpha-radar · 多链聪明钱 + 社媒确定性雷达

> 不做 meme 农学。只抓**高确定性**信号：**链上聪明钱在买 + 社媒注意力起来 + 市值还低 + 合约安全**。
> 策略内核：注意力/聪明钱强、市值低、流动性够、合约安全 = 小亏大赚。

## 一、从哪抓「庄地址 + 聪明钱」

数据源统一用 **[GMGN](https://gmgn.ai)**（覆盖 `sol` / `eth` / `bsc` / `base` / `tron`）：

| 路径 | 是否需要 key | 拿到什么 |
|------|-------------|---------|
| `rank/{chain}/swaps/{period}?orderby=smartmoney` | 否（主路径） | 哪些代币正被聪明钱买入（核心 alpha） |
| `/user/smartmoney` | 免费 key | 聪明钱成交流 → **钱包地址 + 买什么** |
| `/token/{chain}/{address}/traders?tag=smart_degen` | 免费 key | 某代币的聪明钱/庄交易员**钱包地址** |

- **免费 key 申请**：https://gmgn.ai/ai （Ed25519 公钥对，无需私钥，填 `GMGN_API_KEY`）。
- 没 key 也能跑：只用第一条路径，拿到"代币级"聪明钱信号；有 key 才能抓到**钱包地址**本身。
- 官方 OpenAPI 规范：`GMGNAI/gmgn-skills`（可 `npx skills add GMGNAI/gmgn-skills` 直接当工具用）。

社媒注意力（"为什么涨"）：
- 免费代理指标：聪明钱买卖比 + 量能突增 + 小市值 + holder 数（代码内 `collectors/social.py`）。
- 真·社媒量（可选）：LunarCrush Galaxy Score，填 `LUNARCRUSH_API_KEY`。

## 二、目录结构

```
crypto-alpha-radar/
├── collectors/
│   ├── smart_money.py   # 多链聪明钱 / 庄地址抓取（GMGN）
│   └── social.py        # 社媒趋势 / "为什么涨" 分析
├── scorer/
│   ├── engine.py        # 聪明钱 + 注意力 vs 市值 -> 0-100 评分（启发式）
│   └── jev_scorer.py    # Jev (TypeSafe) 决策模型做最终裁决（可选，需 key）
├── alerts/
│   └── email_sender.py  # 邮箱推送（推到你的邮箱）
├── storage/
│   └── store.py         # 本地去重，避免重复推送
├── config/
│   ├── settings.json                  # 链/周期/阈值/评分权重/邮箱
│   └── smart_money_wallets.example.json  # 可选的已知庄/聪明钱地址
├── main.py             # 编排：抓取 -> 过滤 -> 评分 -> 分析 -> 去重 -> 推送
├── requirements.txt
├── .env.example
└── .github/workflows/scheduled.yml   # 每 30 分钟定时跑
```

## 三、本地运行

```bash
pip install -r requirements.txt
cp .env.example .env        # 填入 AI_GATEWAY_API_KEY（Jev 裁决）、EMAIL_TO、SMTP_*；GMGN_API_KEY 可选（抓地址用）
python main.py --dry-run    # 先空跑看输出
python main.py              # 正式跑（达到阈值推邮箱）
python main.py --chain sol eth   # 只跑指定链
```

## 四、部署到 GitHub Actions（零成本、无服务器）

1. 把仓库设为 **Public**（或 Private 也行，Actions 免费额度有限）。
2. Settings → Secrets → 添加：`AI_GATEWAY_API_KEY`、`EMAIL_TO`、`SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASS`（可选 `GMGN_API_KEY`、`TYPESAFE_API_KEY`、`LUNARCRUSH_API_KEY`、`JEV_BASE_URL`）。
3. 已内置 `.github/workflows/scheduled.yml`，每 30 分钟自动跑并推邮箱。

## 五、评分逻辑（贴合"小亏大赚"）

`总分 = 0.35×聪明钱比 + 0.30×注意力vs市值 + 0.20×量能突增 + 0.15×合约安全`，0-100。

- 聪明钱比：买/卖 ≥5 满分。
- 注意力vs市值：市值越低、注意力越高，分越高 —— 就是你要的"注意力高、市值低"。
- 合约安全：rank 已过滤 `not_honeypot/verified/renounced`，默认满分。
- 达到 `alert_threshold`（默认 60）才推送，避免噪音。

权重和阈值都在 `config/settings.json` 里调。

## 五（续）、Jev 决策模型裁决（可选增强，强烈建议）

启发式评分（0-100）是「粗筛」，Jev 是「精筛裁决」。它来自 [TypeSafe](https://typesafe.ai) 的 **Jev / System One** 决策模型——你喂结构化状态 + 带类型的问题，它返回**带概率的判断**，不写一句话。这里只用它做三类判断，不预测涨跌：

- `verdict`：`ape` / `watch` / `avoid`（吃 / 看 / 躲）
- `conviction`：0-10 强度
- `high_conviction`：是否高确定性（0~1 概率）

**为什么用 Jev 而不用启发式硬权重**：Jev 在「对结构化特征做分类」上更稳（社媒多空、合约安全、是否 bait），回测也证明它**不是方向预测器**（方向命中率 ~0.49、过度自信），所以定位是「过滤器/评级器」，不是水晶球——正好贴合「小亏大赚」：帮挡噪音、给确定性打分，不替你 call 顶底。

**接入方式（两种，请求/响应格式完全兼容，只改 endpoint / model / key）**：
- **推荐 · Vercel AI Gateway（免费）**：注册 Vercel → AI Gateway → API Keys，拿 `AI_GATEWAY_API_KEY`。Jev 是 Gateway 的 **free-tier 模型**，每月免费 credits 直接覆盖（本项目跑一个月也就几美分级别）。`config/settings.json` 已默认 `provider: "vercel"`，model 自动用 `typesafe-ai/jev`。
- **备选 · TypeSafe 直连**：https://console.typesafe.ai 拿 `TYPESAFE_API_KEY`（注意：2026-09-22 起新注册暂停送额度，需自行充值或作 Vercel BYOK）。把 `provider` 改为 `"typesafe"` 即用直连（`jev-1.13.0`）。

2. 把 key 填进 `.env` 的 `AI_GATEWAY_API_KEY`（Actions 里填 Secret `AI_GATEWAY_API_KEY`）。成本极低（input $0.042/百万 token、output 免费）。
3. `config/settings.json` 的 `jev` 段：
   - `enabled`：true 即启用（已默认）。
   - `provider`：`vercel`（默认，走 Gateway）或 `typesafe`（直连）。
   - `min_confidence`：裁决置信度阈值（默认 0.7）。
   - `allow_verdicts`：允许推送的裁决（默认 `["ape","watch"]`，即 avoid 不推）。
   - `n_samples`：同请求采样次数取平均（Jev 非确定性，差可达 0.07；默认 1，想更稳设 3）。
4. **降级保障**：不填 key 或 `enabled=false` 时，`JevScorer.available=False`，main 自动退回纯启发式（达阈值即推），不报错。填了 key 但某次调用失败，该 token 本轮回退丢弃（保守，防误报）。

> 注意：Jev 仅文本、**英文最佳**，状态已统一翻成英文 label；中文直接喂效果差。

## 六、重要声明

本项目仅做**链上数据聚合与信号提示**，不构成任何投资建议。加密资产波动极大，务必自行研究、只用亏得起的钱。

> 注：本仓库在隔离环境编写，GMGN 端点结构来自其官方 OpenAPI 与开发者文档；首次运行请在本机/VPS/Action 内验证返回字段，若 GMGN 调整字段名，改 `collectors/smart_money.py` 里的映射即可。
