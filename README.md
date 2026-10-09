<div align="center">

# 🍔 mcd-pick-one

**懒得想吃什么？我只给你一个答案。**

给「预算卡死 + 选择恐惧」的大学生用的麦当劳点单助手。
不列候选、不给选项，每次只推 **1 个**方案。

[![MCP](https://img.shields.io/badge/MCP-McDonald%20China-D52B1E?style=flat-square)](https://mcp.mcd.cn)
[![WorkBuddy](https://img.shields.io/badge/Built%20with-WorkBuddy-006EFF?style=flat-square)](https://www.workbuddy.cn)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white)](#依赖)
[![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen?style=flat-square)](#依赖)
[![Stars](https://img.shields.io/github/stars/zhouzhou20200/mcd-pick-one?style=flat-square&color=D52B1E&label=star)](https://github.com/zhouzhou20200/mcd-pick-one/stargazers)

<img src="./images/demo.svg" alt="mcd-pick-one 决策引擎的真实运行输出" width="880">

<sub>↑ 上图为 <code>src/pick_one.py</code> 的<strong>真实运行输出</strong>，不是设计稿。</sub>

</div>

---

## 它跟"省钱助手"不是一回事

麦当劳 MCP 赛道里已经有十几个"省钱助手"了。它们优化的是**价格**，这个项目优化的是**决策**。

| | 常见的省钱助手 | **mcd-pick-one** |
|:--|:--|:--|
| 输出 | 一列候选，让你接着挑 | **1 个答案**；追问才给备选，总数 ≤ 3 |
| 预算 | "尽量便宜" / 只报参考价 | **硬上限 25 元**，压不进去就如实说超了多少 |
| 价格口径 | 菜单价 | **券代入官方 `calculate-price` 核出的实付价** |
| 吃饱 | 一般不检查 | 强制「主食 + 配餐」结构 |
| 无解时 | 硬凑一个给你 | 如实告知「最接近的 X 元，超了 Y 元」 |
| 口味 | 无记忆 | 口味档案，按 `满足度 ÷ 实付价` 排序 |

> **一句话：便宜是门槛，治选择恐惧才是卖点。**

---

## 它解决什么

| 你的状态 | mcd-pick-one 的回应 |
|:--|:--|
| 懒得看菜单、比价、算券 | 全替你算完，只说结论 |
| 选项一多就卡住 | **只给 1 个答案**，不给你挑 |
| 一餐预算 25 元，超了难受 | **硬预算**，自动用券把价格压回来 |
| 便宜怕吃不饱 | 强制「主食 + 配餐」结构，不会给你一个孤零零的汉堡 |
| 有忌口、口味挑 | 记住你吃过什么、不吃什么 |
| 上课累，有时不想出门 | 每次问一句：自己拿还是送 |

---

## 目录

- [快速开始](#快速开始)
- [使用示例](#使用示例)
- [核心逻辑](#核心逻辑)
- [为什么价格是"算"出来的](#为什么价格是算出来的)
- [本地试跑决策引擎](#本地试跑决策引擎)
- [项目结构](#项目结构)
- [目标用户](#目标用户)
- [设计边界（明确不做）](#设计边界明确不做)
- [依赖](#依赖)
- [声明](#声明)

---

## 快速开始

### 1. 拿到麦当劳 MCP Token

到 [麦当劳 MCP Server](https://github.com/M-China/mcd-mcp-server) 用手机号登录 → 控制台 → 激活 → 复制 Token。

### 2. 在 WorkBuddy 里配置连接器

左侧边栏【专家·技能·连接器】→【连接器】→ 右上角【自定义连接器】→【配置 MCP】，填入（把 `<你的Token>` 换掉）：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer <你的Token>"
      }
    }
  }
}
```

> 脱敏示例见 [`mcp-config.example.json`](./mcp-config.example.json)，里面**只有环境变量占位符**，不含任何真实凭证。
> ⚠️ 配置保存后，请在【自定义连接器】页面把 `mcd-mcp` **启用**，配置才会生效。

### 3. 开始用

直接在对话框里说：

```
中午吃啥，帮我定一个
```

它会问你一句（取餐方式 / 忌口 / 要不要饮料，**回车就用默认值**），然后给你**唯一一个答案**。

---

## 使用示例

```
你：中午吃啥，帮我定一个

AI：问三件事（都可以直接回车走默认）
    ① 自己拿还是送？   → 默认：自己拿
    ② 今天有忌口吗？   → 默认：用档案
    ③ 配个饮料吗？     → 默认：不要

你：（回车）

AI：【今天就吃这个】
    双层吉士汉堡 + 中薯条
    用券：满 20 减 8
    实付：21.00 元（原价 29，省 8 元）
    取餐：就近门店自取
    结构达标：主食 + 配餐，能吃饱
```

当天没有满足条件的组合时——**不硬凑，直接说实话**：

```
AI：【今天没有完全符合的】
    最接近的是 麦香鱼套餐，实付 27.00 元，超了 2.00 元。
    （原因：该门店今日无可用券）
    要不要就按这个来？还是放宽预算？
```

---

## 核心逻辑

```
① 定位门店        query-nearby-stores / delivery-query-stores
② 取券           query-store-coupons / available-coupons / query-my-coupons
③ 取菜单          query-meals
④ 硬筛选          剔除忌口 → 必须「主食+配餐」→ 实付 ≤ 25 元
⑤ 算价           calculate-price
⑥ 打分           score = 口味满足度 ÷ 实付价
⑦ 只吐一个        追问才给备选，总数 ≤ 3
⑧ 组装答案        点什么 / 用哪张券 / 实付多少 / 省多少 / 去哪拿
```

共调用 **11 个**麦当劳 MCP Tool。逐项说明、调用时序、以及**为什么没用另外 24 个 Tool**，见 [`MCP_INTEGRATION.md`](./MCP_INTEGRATION.md)。

---

## 为什么价格是"算"出来的

这是本项目最关键的一个设计决定，也是它敢承诺"硬预算"的唯一底气。

麦当劳的真实单价：**麦辣鸡腿堡约 23 元、巨无霸约 25.5 元**——加一份配餐必然破 25 元。
也就是说，**无券时「25 元吃饱」在数学上几乎无解**。

所以本项目不靠"筛便宜的"，而是：

1. 把门店可用券**逐张代入**官方 `calculate-price` 真的算一遍；
2. 只认**算出来的实付价**，菜单价不作为判断依据；
3. 券撑不起预算就**如实认输**（输出"最接近的 + 超出金额"），绝不虚假满足。

> 便宜不是筛出来的，是算出来的。

---

## 本地试跑决策引擎

`src/pick_one.py` 是**纯标准库**脚本，不联网、零依赖，可直接验证决策逻辑：

```bash
python src/pick_one.py --input src/demo.json --budget 25
```

真实输出：

```
【今天就吃这个】
  双层吉士汉堡套餐
  构成：双层吉士汉堡 + 中薯条
  实付：21.00 元（预算 25.00，自取无配送费）
  满足度：4.8 / 5　性价比得分：0.2262
  备选（追问才展示）：
    - 麦辣鸡腿堡套餐（实付 24.00 元，得分 0.1875）
```

外送场景（多加 9 元配送费后预算守不住了，触发兜底）：

```bash
python src/pick_one.py --input src/demo.json --delivery-fee 9
```

```
【今天没有完全符合的】
最接近的是 双层吉士汉堡套餐，实付 30.00 元，超了 5.00 元。
要不要就按这个来？还是放宽预算？
```

加 `--json` 可输出原始结果，便于二次开发。

> 这个脚本的意义：**即使 MCP 服务不可用，决策逻辑本身依然可被独立验证**。

---

## 项目结构

```
mcd-pick-one/
├── README.md                    项目说明（本文件）
├── CONTEST_DECLARATION.md       参赛声明（官方原文，不可修改）
├── MCP_INTEGRATION.md           MCP 工具与调用流程说明
├── mcp-config.example.json      脱敏配置示例（仅环境变量占位符）
├── workbuddy.md                 WorkBuddy 开发过程记录
├── images/
│   └── demo.svg                 运行输出示意图
├── src/
│   ├── SKILL.md                 技能主逻辑（技能定义与执行指令）
│   ├── pick_one.py              决策引擎（筛选 + 打分 + 排序，可独立运行）
│   ├── profile.example.json     口味档案模板
│   └── demo.json                可直接运行的示例输入
└── 需求文档.md                   需求规格（开发内部文档）
```

---

## 目标用户

在校大学生。场景是上课间隙、宿舍、图书馆——**时间零碎、预算有限、不想做决定**。

---

## 设计边界（明确不做）

- ❌ **不真实下单**（`create-order` 会扣款，风险不可控，由用户手动操作）
- ❌ **不静默自动领券**（`auto-bind-coupons` 是写操作，必须经用户明确同意）
- ❌ **不碰抽奖 / 积分商城**（`draw-lottery` 会扣积分）
- ❌ **不做健身 / 营养管理**（该赛道已饱和）

---

## 依赖

| 依赖 | 说明 |
|:--|:--|
| 麦当劳 MCP Server | `https://mcp.mcd.cn`，需自备 Token |
| WorkBuddy | 推荐宿主环境（本项目的开发与运行环境） |
| Python 3.8+ | 仅 `src/pick_one.py` 需要，纯标准库，零第三方依赖 |

---

## 声明

本项目为**麦当劳程序员创意开发大赛参赛作品**，由参赛者独立开发，**非麦当劳官方产品**。
项目输出仅供参考，不构成医疗、营养或其他专业建议；餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。

---

<div align="center">

**如果这个东西让你少纠结了一次午饭，点个 ⭐ 就是最好的反馈。**

</div>
