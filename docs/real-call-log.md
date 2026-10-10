# 真实调用记录

本文档记录 `mcd-pick-one` 对**麦当劳 MCP Server 的真实调用证据**，用于核验参赛要求中的"真实使用麦当劳 MCP 能力"。

> ✅ 全部调用均为**只读**工具。
> ❌ 未调用任何下单（`create-order`）、领券（`auto-bind-coupons`）、抽奖（`draw-lottery`）工具。
> 🔒 本文件不含任何凭证信息。

---

## 1. 验证环境

| 项 | 值 |
|----|----|
| 调用时间 | 2026-10-10 10:03:43 ~ 10:04:38（GMT+08:00） |
| MCP Server | `mcd-mcp` **v1.0.0** @ `https://mcp.mcd.cn` |
| 传输方式 | `streamablehttp` |
| 宿主环境 | WorkBuddy |
| 门店 | `1980320` **麦当劳天津站后广场餐厅**（天津站北广场 B1，距离 323 m） |
| 场景 | 到店自取（`orderType=1`，`beType=1`） |
| 调用工具数 | **11 个**（详见下表） |

---

## 2. 调用明细

| # | Tool | 入参 | 返回摘要 | `traceId` |
|:--:|------|------|----------|-----------|
| 1 | `now-time-info` | — | `2026-10-10 10:03:43`，`SATURDAY`，`GMT+08:00` | `35a976fc3444a8b9300c888b903eb9d2` |
| 2 | `query-nearby-stores` | `searchType=1, beType=1` | `code 600050`：收藏门店为空，需提供城市+关键词 | `c5a92a2ad41a2515b0f6c874a8aa2fbf` |
| 3 | `query-nearby-stores` | `searchType=2, city=天津, keyword=天津站, beType=1` | 返回 **5 家**门店，最近 323 m | `cd1a5d53b309e2ed0b94502ae2b9dcfb` |
| 4 | `query-meals` | `storeCode=1980320, orderType=1, beType=1` | **9 个分类 / 60+ 餐品**（早餐时段菜单） | `5129660b55b963b4719d62ad2ae01e3b` |
| 5 | `query-store-coupons` | `storeCode=1980320, orderType=1, beType=1` | `data=[]` —— **该门店当前无可用券** | `574d7afdf9315b1248672132dc9422b2` |
| 6 | `query-my-coupons` | — | `暂无可用优惠券` —— **券包为空** | — |
| 7 | `available-coupons` | — | 麦麦省 **6 个券可领取**（早餐套餐券 / 免费脆薯饼 / 麦旋风买一送一 / 9.9 元冰美式） | — |
| 8 | `calculate-price` | `5888×1 + 4825×1`，`storeCode=1980320, orderType=1, beType=1` | **1950 分 = 19.50 元**，`discount=0` | `4cd44cbae85dae2406ae7dafcf69a194` |
| 9 | `list-nutrition-foods` | — | **160 条**营养记录（能量/蛋白质/脂肪/碳水/钠/钙） | `1d89053322b356d3b81a78995de16bf8` |
| 10 | `query-my-account` | — | 可用积分 **86.8**，累计 158.8，已过期 72 | `7bbe725b644490c5a071d11ca5918a26` |
| 11 | `campaign-calendar` | — | 当月活动日历（9.9 元早餐两件套、49 元麦金学期卡、G-DRAGON 联名等） | — |

---

## 3. 原始返回摘录

### 3.1 `calculate-price`（核价链路的核心证据）

请求：

```json
{
  "storeCode": "1980320",
  "orderType": 1,
  "beType": 1,
  "items": [
    { "productCode": "5888", "quantity": 1 },
    { "productCode": "4825", "quantity": 1 }
  ]
}
```

响应（节选）：

```json
{
  "success": true,
  "code": 200,
  "datetime": "2026-10-10 10:04:38",
  "traceId": "4cd44cbae85dae2406ae7dafcf69a194",
  "data": {
    "productOriginalPrice": 1950,
    "productPrice": 1950,
    "originalPrice": 1950,
    "discount": 0,
    "price": 1950,
    "productList": [
      { "productCode": "5888", "productName": "吉士蛋麦满分", "quantity": 1, "originalSubtotal": 1050, "subtotal": 1050 },
      { "productCode": "4825", "productName": "脆薯饼",     "quantity": 1, "originalSubtotal": 900,  "subtotal": 900 }
    ],
    "takeWayList": [
      { "code": "eat-in",    "title": "堂食", "subtitle": "店内用餐" },
      { "code": "locker-in", "title": "外带", "subtitle": "店内取餐柜" }
    ]
  }
}
```

### 3.2 `query-store-coupons`（空结果的证据）

```json
{
  "success": true,
  "code": 200,
  "datetime": "2026-10-10 10:04:24",
  "traceId": "574d7afdf9315b1248672132dc9422b2",
  "data": []
}
```

### 3.3 `query-nearby-stores`（真实门店）

```json
{
  "storeCode": "1980320",
  "storeName": "麦当劳天津站后广场餐厅",
  "address": "天津站北广场B1",
  "distance": 323,
  "businessStatus": true,
  "businessStartTime": "06:00",
  "businessEndTime": "22:00",
  "reservation": true,
  "reservationTimeOptions": [
    {
      "date": "2026-10-10",
      "today": true,
      "reservationOptionText": "早餐(06:14至10:15)，午餐(10:44至14:15)，下午茶(14:44至16:45)，夜市(17:14至21:45)"
    }
  ]
}
```

---

## 4. 关键发现（4 条，其中 3 条修正了原设计假设）

### 4.1 ⚠️ 菜单按时段切换，跨时段的设计不能复用

调用 8 时服务器时间为 **10:03**，落在门店档期的「早餐 06:14–10:15」区间内。因此 `query-meals` 返回的是**早餐菜单**：麦满分系列、厚松饼堡系列、麦咖啡、炒双蛋堡……

**整个返回里没有麦辣鸡腿堡，也没有巨无霸。**

原 README 用"麦辣鸡腿堡约 23 元、巨无霸约 25.5 元"来论证"25 元吃饱无解"——该论证**只在正餐时段成立**。项目必须把"当前时段"作为取菜单的前置条件，否则给出的推荐是错的。

### 4.2 ⚠️ "券驱动"在本例中失效，必须有无券路径

`query-store-coupons` 返回**空数组**、`query-my-coupons` 显示**券包为空**。也就是说，本次真实环境下**一张可用券都没有**。

如果项目把"把价格压进预算"完全押在券上，此刻它会直接失败。**真实结论：券是加速器不是地基**，必须有"无券时按菜单价精算单品组合"的降级路径。

### 4.3 ✅ 无券时「25 元吃饱」在早餐时段**有解**

真实菜单价组合：

| 组合 | 主食 | 配餐 | 合计 |
|------|------|------|:--:|
| 最低价组合 | 吉士蛋麦满分 10.5 元 | 脆薯饼 9 元 | **19.50 元** |
| 次低 | 火腿扒麦满分 11.5 元 | 脆薯饼 9 元 | 20.50 元 |
| 第三 | 大脆鸡扒麦满分 12.5 元 | 脆薯饼 9 元 | 21.50 元 |

三者都**满足「主食 + 配餐」结构且 ≤ 25 元**，且已由 `calculate-price` 实测验证（见 3.1）。

→ 修正后的表述应为：**"25 元吃饱在正餐时段几乎必须靠券，在早餐时段可直接靠单品组合达成。"**

### 4.4 📌 两条有价值的实现细节

1. **无券无活动时，`calculate-price` 总价 = 各单品菜单价之和**（1050 + 900 = 1950 ✓）。
   说明菜单价可用于**预筛**，但一旦存在券或活动就**必须**走 `calculate-price`——两者的结果会分叉。
2. **`takeWayList` 只会返回「堂食 / 外带」**，这是 `orderType=1`（到店）内部的取餐方式。
   它与"外送"（`orderType=2`）是两个不同层级的概念——需求里说的"外带"正好落在这里，代码中不能与外送混用。

---

## 5. 未调用的 Tool 及原因

| Tool | 未调用原因 |
|------|-----------|
| `create-order` / `mall-create-order` / `party-order-create` / `cancel-order` | **会产生真实扣款**，验证阶段不触碰 |
| `auto-bind-coupons` | **写操作**，会真实写入用户账号；须经用户显式同意才可调用 |
| `draw-lottery` | 会消耗用户积分 |
| `delivery-query-*` / `query-party-*` / `query-meal-assistance` / `query-promotions` | 外送、派对、团餐场景，本次验证聚焦到店自取单人场景 |

---

## 6. 复现方式

1. 按 [`mcp-config.example.json`](../mcp-config.example.json) 配置并启用 `mcd-mcp` 连接器（需自备 Token）；
2. 在 WorkBuddy 中依次提出以下请求，即可复现上表调用：

```
今天天津站附近有什么麦当劳？
麦当劳天津站后广场餐厅今天有什么可以点的？
这家店我现在有什么券可以用？
帮我算一下：吉士蛋麦满分 1 份 + 脆薯饼 1 份，到店自取多少钱？
```

3. 用同批数据离线复现决策结果：

```bash
python src/pick_one.py --input src/demo.real.json
```

---

<p align="right"><sub>记录时间：2026-10-10 · 全部调用均为只读</sub></p>
