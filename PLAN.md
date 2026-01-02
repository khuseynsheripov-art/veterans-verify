# Veterans Verify - 开发计划

> 整体方向、数据标准、流程说明、更新日志

**最后更新**: 2026-01-02 09:25 UTC+8

---

## 更新日志

### 2026-01-02 09:25 完善账号密码逻辑，支持多密码检测和尝试

**问题发现**：
- 邮箱池和数据库中的密码不一致（10/12 个账号）
- 前期测试时数据保存逻辑不统一
- `get_account_password()` 只返回单个密码，登录失败时无法尝试备选密码

**完善内容**：

1. **新增函数** `get_password_candidates()` (run_verify.py:788-858)：
   - 返回所有可能的密码候选列表
   - 检测邮箱池和数据库密码是否一致
   - 不一致时记录警告日志
   - 格式：`[{"password": "xxx", "source": "邮箱池", "priority": 1}, ...]`

2. **保留函数** `get_account_password()` (run_verify.py:861-869)：
   - 向后兼容，返回优先级最高的密码
   - 内部调用 `get_password_candidates()`

3. **修改 CDP 全自动登录逻辑** (run_verify.py:2061-2083)：
   - 获取所有密码候选
   - 依次尝试每个密码
   - 记录成功的密码来源
   - 失败时自动尝试下一个密码

4. **新增账号验证脚本** `scripts/verify_account_passwords.py`：
   - `--check-only`: 检查密码一致性（推荐，快速安全）
   - `--verify-login`: 实际登录验证（慢，有风控风险）
   - 生成详细报告：`data/password_check_results.json`

**验证结果**（12 个账号）：
```
✓ 密码一致:         0 个
⚠️ 密码不一致:       10 个
ℹ️ 仅邮箱池有密码:   2 个
```

**⚠️ 重要更正**：
- 旧账号：数据库密码才是 ChatGPT 真实密码 ✅
- 邮箱池密码：后来批量生成的，不是真实密码 ❌
- 所以优先级：**数据库 > 邮箱池**（已修正）

**最佳实践（最终版）**：

1. **密码轮换策略** - 数据库优先 > 邮箱池其次
2. **自动同步机制** - 登录成功后同步正确密码到两边
3. **验证脚本** - 实际登录验证并自动更新
4. **新账号策略** - 邮箱池生成密码，同步保存

**后续步骤**：
1. ✅ 代码已完善（密码轮换 + 自动同步）
2. ⏳ 测试 CDP 全自动模式
3. ⏳ 运行验证脚本修复旧账号

---

### 2026-01-02 08:50 logout_chatgpt 简化为 Cookie 清除（v2）

**问题**：
- 原 120 行代码找菜单、点按钮、处理弹窗，太脆弱
- 第一版 `clear_cookies()` 清除所有域名，包括 Flask Session 导致日志断开

**修复** (run_verify.py:711-783)：
```python
# 只清除 chatgpt/openai 相关 cookies，保留其他域名
all_cookies = await context.cookies()
cookies_to_keep = [c for c in all_cookies
    if 'chatgpt.com' not in c['domain']
    and 'openai.com' not in c['domain']]
await context.clear_cookies()
await context.add_cookies(cookies_to_keep)
```

**测试结果**：
- ✅ 清除 32 个 ChatGPT cookies，保留 1 个 Flask Session
- ✅ 日志持续输出，WebSocket 没断开
- ✅ 退出登录成功，自动登录流程正常

### 2026-01-02 08:25 修复 logout_chatgpt 退出失败问题

**问题**：
- `logout_chatgpt()` 反复输出 "未找到个人资料菜单，可能未登录"
- 但实际账号是登录状态
- 脚本没有正确退出上一个账号，导致切换账号失败

**根因**：
- 脚本在 veterans-claim 页面执行退出操作
- 但 veterans-claim 是简化页面，**没有侧边栏和个人资料菜单**
- 只有 chatgpt.com 主页才有完整的侧边栏

**修复** (run_verify.py:759-798)：
1. 导航到 `chatgpt.com/` 后验证 URL 不是 veterans-claim
2. 如果被重定向到 veterans-claim，重试导航（最多3次）
3. 增加等待时间确保页面完全加载（2秒）
4. 个人资料菜单查找增加重试逻辑（3次，每次等待2秒）

---

## 项目目标

自动化完成 ChatGPT Veterans 验证，获取 1 年免费 ChatGPT Plus。

---

## 四种操作模式（2025-12-29 最终版）

| 模式 | 账号来源 | 浏览器 | 验证码 | 成功后 |
|------|---------|--------|--------|--------|
| 邮箱池管理 | - | - | - | - |
| 全自动批量 | 邮箱池选择 | Camoufox 无头 | 自动获取 | 退出登录，下一个 |
| 可视化调试 | 邮箱池选择 | **Camoufox 有窗口** | 自动获取 | 保持登录 |
| 自有账号 | 手动输入 | Camoufox 有窗口 | 需手动输入 | 保持登录 |

### 为什么用 Camoufox 可视化而不是 CDP？

| 特性 | CDP (固定 Chrome) | Camoufox 可视化 |
|------|------------------|-----------------|
| 指纹 | ❌ 固定，容易被标记 | ✅ 每次自动生成新指纹 |
| 启动 | ❌ 需手动启动脚本 | ✅ 自动启动 |
| 可视化 | ✅ 有窗口 | ✅ `headless=False` |
| 反检测 | ❌ 普通 Chrome | ✅ C++ 级伪装 |

**结论**：Camoufox 可视化模式是最优解。

### 关键注意事项

- **登录/退出必须在 chatgpt.com 主页进行**
- **Status 字段动态显示**，有些页面有有些没有，需要检测
- **新任务启动时自动检测并退出上一个账号**
- **所有模式都消耗临时邮箱**（用于接收 SheerID 验证链接）

---

## 验证流程

```
┌─────────────────────────────────────────────────────────────┐
│                    完整验证流程                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 创建临时邮箱 ─────────────────────────────────────────►  │
│                                                              │
│  2. 打开 chatgpt.com/veterans-claim ─────────────────────►  │
│                                                              │
│  3. 点击"登录" → 输入邮箱 → 创建密码 ────────────────────►  │
│                                                              │
│  4. 等待 ChatGPT 验证码邮件 → 输入验证码 ────────────────►  │
│                                                              │
│  5. 登录成功 → 自动跳转 SheerID 验证页面 ────────────────►  │
│                                                              │
│  6. 填写表单（BIRLS 真实数据 + 随机退伍日期）───────────►   │
│                                                              │
│  7. 点击 "Verify My Eligibility" ───────────────────────►   │
│                                                              │
│  8. 等待 SheerID 验证邮件（链接）→ 点击链接 ────────────►   │
│                                                              │
│  9. 检查结果：                                               │
│     ├─ 成功 → 跳转 chatgpt.com，获得 1 年 Plus              │
│     ├─ 已验证 → 换下一条数据重试                             │
│     └─ 其他错误 → 止损冷却                                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 数据来源：BIRLS 数据库

### 在线搜索

**网站**: https://www.birls.org/

- **19.5M+ 已故美国退伍军人**公开数据库
- 2024年12月上线，2025年9月更新 150万条新记录

### 本地数据

**文件**: `data/birls_update.csv` (199MB)
**处理后**: `data/veterans_processed.json` (19,605 条)

| 字段 | 来源 | 说明 |
|------|------|------|
| First name | BIRLS 真实数据 | 已故军人公开信息 |
| Last name | BIRLS 真实数据 | |
| Birth date | BIRLS 真实数据 | 筛选 1980-2005 年生 |
| Branch | BIRLS 真实数据 | 5 种军种 |
| Discharge date | **随机生成** | 过去 1-11 个月内 |
| Email | **临时邮箱** | API 创建 |

### 军种分布

```
Army:         10,247 (52.3%)
Marine Corps:  3,759 (19.2%)
Navy:          3,098 (15.8%)
Air Force:     2,326 (11.9%)
Coast Guard:     175 (0.9%)
```

---

## SheerID 表单字段标准

| 字段 | 类型 | 选项/格式 |
|------|------|----------|
| Status | 下拉 | Active Duty / **Military Veteran or Retiree** / Reservist |
| Branch of service | 下拉 | Air Force / Army / Coast Guard / Marine Corps / Navy / Space Force |
| First name | 文本 | |
| Last name | 文本 | |
| Date of birth | 日期 | Month(下拉) + Day + Year |
| Discharge date | 日期 | **必须在过去12个月内！** |
| Email address | 文本 | 接收验证链接 |

---

## 错误类型枚举

```python
RESULT_TYPES = {
    # === 成功 ===
    "SUCCESS": "You've been verified + Continue 按钮",

    # === 消耗类（换下一条数据继续）===
    "VERIFICATION_LIMIT_EXCEEDED": "军人数据已被验证过",
    "NOT_APPROVED": "邮件验证后被拒绝",
    "INVALID_DISCHARGE_DATE": "退伍日期无效（超过12个月）",
    "UNABLE_TO_VERIFY": "信息无法验证",

    # === 需要操作 ===
    "CHECK_EMAIL": "等待邮件验证",
    "PLEASE_LOGIN": "需要登录 ChatGPT",

    # === 错误 ===
    "FORM_FILL_ERROR": "表单填写失败",
    "NETWORK_ERROR": "网络错误",
}
```

---

## 核心模块

| 模块 | 状态 | 说明 |
|------|------|------|
| `app.py` | ✅ | Flask 主应用 |
| `run_verify.py` | ✅ | CDP 模式脚本 |
| `automation/camoufox_verify.py` | ✅ | Camoufox 模式 |
| `database.py` | ✅ | PostgreSQL 数据库 |
| `email_manager.py` | ✅ | 邮箱验证码/链接 |
| `email_pool.py` | ✅ | 邮箱池管理 |
| `proxy_manager.py` | ✅ | 代理池管理 |
| `profile_manager.py` | ✅ | Profile 持久化 |
| `veteran_data.py` | ✅ | BIRLS 军人数据 |

---

## 已验证成功的账号

| 邮箱 | 密码 | 军人信息 |
|------|------|---------|
| vethuxntarz@009025.xyz | 5NJNzOIW4GNQhJ7p | Eriqioel Aquino (Marine Corps) |
| nsey68qkv@009025.xyz | (待查询) | (待查询) |

**临时邮箱登录**: https://one.009025.xyz/ → 输入邮箱地址

---

## 开发阶段

### Phase 1: 基础框架 ✅

- [x] BIRLS 数据处理
- [x] 邮箱服务集成
- [x] Flask API

### Phase 2: 测试调优（当前）

- [x] 手动测试流程
- [x] 选择器收集
- [ ] Camoufox 可视化测试
- [ ] 代理轮换

### Phase 3: 批量运行

- [ ] 任务队列
- [ ] 成功/失败统计
- [ ] Web 界面监控

---

## 当前各模式状态（2025-12-31）

| 模式 | 状态 | Tag | 说明 |
|------|------|-----|------|
| 邮箱池管理 | ✅ 可用 | - | 独立操作，创建/管理临时邮箱 |
| CDP 手动登录 | ✅ 可用 | `v0.1-cdp-manual` | 用户手动登录后，脚本自动验证 |
| CDP 全自动 | 🔧 开发中 | `feature/cdp-auto` | 自动退出+登录+验证，前端 session 问题待修复 |
| Camoufox 无头 | ⏸️ 待测试 | - | 完整自动化，需要 CDP 全自动稳定后测试 |
| Camoufox 可视化 | ⏸️ 待测试 | - | 调试模式 |

### 模式使用指南

#### 推荐：CDP 手动登录模式

**适用场景**：调试、单个账号验证

**操作步骤**：
```
1. 启动 Chrome: scripts\start-chrome-devtools.bat
2. 在 Chrome 中手动登录 ChatGPT
3. 确保登录成功后，访问 chatgpt.com/veterans-claim
4. 前端选择 "🔑 CDP 手动登录" 模式
5. 选择临时邮箱 → 点击"开始验证"
6. 脚本接管，自动填写 SheerID 表单
```

**优点**：
- 登录由用户控制，避免登录问题
- 脚本只负责验证核心逻辑
- 调试时可随时介入

#### CDP 全自动模式（开发中）

**当前问题**：
- 前端 session 可能过期，显示 "Session 过期"
- 脚本实际可能还在后台运行

**临时解决方案**：
- 如果前端报错，检查 Chrome 窗口
- 如果脚本卡住，停止任务，切换到 CDP 手动模式

---

## 后续开发方向（待定）

### 方向 1：链接模式

**目标**：直接访问 SheerID 验证链接，无需登录 ChatGPT

**待验证**：
- [ ] 验证失败后，链接是否可复用？
- [ ] 同一个链接能否多次提交不同数据？
- [ ] 链接有效期多久？

**测试方法**：
1. 获取一个 SheerID 验证链接
2. 第一次提交失败数据
3. 刷新页面，再次提交
4. 观察是否能继续

**如果可复用**：
```
link_verify.py
  → 输入: SheerID 链接 + 军人数据
  → 无需登录，直接填表验证
  → 失败换数据，循环直到成功
```

### 方向 2：Telegram 机器人

**场景**：用户通过 Telegram 提交验证请求

**可能的模式**：
| 模式 | 输入 | 流程 |
|------|------|------|
| 链接模式 | SheerID 链接 | 直接验证 |
| 自有账号 | ChatGPT 邮箱+密码 | 登录后验证 |
| 全自动 | 无 | 创建临时邮箱，完整流程 |

**待参考**：用户的类似 Telegram 机器人项目

---

## 更新日志

### 2026-01-03 02:00 UTC+8

**修复切换账号未退出 bug**

#### ✅ auto_login_chatgpt() 账号验证

修复切换邮箱时未退出上一个账号的关键 bug：
- `run_verify.py:997-1012` - 在 veterans-claim 页面检测到已登录时，验证当前账号是否是目标邮箱
- 如果不是目标账号，调用 `logout_chatgpt()` 退出后重新登录

**问题原因**：
```
任务1 (pbtb15ocb) 登录成功 → 验证
任务1 结束，但没有退出登录
任务2 (mzlr81fos) 启动
auto_login_chatgpt() 检测到 veterans-claim 有验证按钮 → 直接返回成功
结果：用的还是 pbtb15ocb 的账号！
```

**修复后**：调用 `get_logged_in_account()` 检查当前登录的邮箱，不匹配则退出重登。

---

### 2026-01-03 01:30 UTC+8

**全面中英双语支持**

#### ✅ logout_chatgpt() 中英双语

修复退出登录函数只支持中文的问题：
- `run_verify.py:687-780` - 重构为支持中英双语选择器
- 新增 `find_and_click()` 辅助函数，自动尝试多个名称

```python
PROFILE_MENU_NAMES = ['打开"个人资料"菜单', 'Open profile menu', 'Profile']
LOGOUT_MENUITEM_NAMES = ['退出登录', 'Log out', 'Sign out']
SWITCH_ACCOUNT_NAMES = ['登录至另一个帐户', 'Log in to another account']
```

#### ✅ 登录检测中英双语

修复 `run_verify_loop()` 中检测登录状态的选择器：
- `run_verify.py:1990-2012` - 支持中英双语

---

### 2026-01-03 00:30 UTC+8

**脚本自动化完善**

#### ✅ spinbutton 多语言支持

修复 about-you 页面日期填写，支持中英双语：
- `run_verify.py:908-930` - 更新为中英双语匹配
- `camoufox_verify.py:424-451` - 更新为中英双语匹配

```python
# 现在支持中英双语 aria-label
await fill_spinbutton(["年", "Year", "year"], birth_year, "年份")
await fill_spinbutton(["月", "Month", "month"], birth_month, "月份")
await fill_spinbutton(["日", "Day", "day"], birth_day, "日期")
```

#### ✅ 前端密码显示修复

修复账号列表密码被邮箱池覆盖的问题：
- `app.py:266-280` - 列表接口只有数据库密码为空时才用邮箱池补充
- `app.py:305-314` - 详情接口不覆盖数据库密码，只补充 JWT

**原因**：数据库中的密码是实际注册使用的正确密码，邮箱池的是预生成的旧密码。

---

### 2026-01-02 23:00 UTC+8

**模式设计确定（六种模式）+ 记录已知问题**

#### ✅ 六种操作模式确定

| 模式 | 浏览器 | 账号来源 | 登录方式 | 说明 |
|------|--------|---------|---------|------|
| 邮箱池管理 | - | - | - | 独立功能 |
| Camoufox 批量 | 无头 | 临时邮箱 | 脚本自动 | 自动创建邮箱→注册→验证→下一个 |
| Camoufox 可视化 | 有窗口 | 临时/自有 | 脚本自动 | 调试用 |
| Camoufox 无头全自动 | 无头 | 临时邮箱 | 脚本自动 | 单个临时邮箱 |
| Camoufox 无头自有 | 无头 | 自有账号 | 脚本自动 | 单个自有账号 |
| CDP 手动 | CDP Chrome | 临时/自有 | 用户手动 | **保底机制** |

#### ✅ 自动退出/登录逻辑

- 所有模式（除 CDP 手动）：新任务开始 → 自动退出上一个账号 → 自动登录当前账号
- 自有账号：使用前端输入的账号密码，脚本处理验证码
- CDP 手动：用户手动登录，需区分账号类型用于持久化

#### 🔴 记录已知问题

1. **前端密码显示不一致**：账号列表 vs 详情页密码不同
2. **任务控制按钮失效**：重启/停止有时不起作用
3. **脚本热重载问题**：更新脚本需重启应用

---

### 2026-01-02 22:30 UTC+8

**模式设计确定 + 持久化逻辑完善**

#### ✅ 四种操作模式确定

| 模式 | 浏览器 | 账号来源 | 登录方式 | 消耗邮箱 | 定位 |
|------|--------|---------|---------|---------|------|
| CDP 手动 | CDP Chrome | 临时/自有 | 用户手动 | 同/额外 | **保底机制** |
| CDP 全自动 | CDP Chrome | 临时邮箱 | 脚本自动 | 同一个 | 单个临时邮箱 |
| Camoufox 可视化 | 有窗口 | 临时/自有 | 脚本自动 | 同/额外 | 调试 + 反检测 |
| Camoufox 批量 | 无头 | 临时邮箱 | 脚本自动 | 同一个 | 批量无人值守 |

#### ✅ 账号来源类型

| 类型 | 说明 | 消耗邮箱 |
|------|------|---------|
| 临时邮箱 | 从邮箱池选择 | 同一个邮箱（自己就是消耗邮箱） |
| 自有账号 | 手动输入邮箱+密码 | 额外选择邮箱池邮箱 |

#### ✅ 持久化数据结构扩展

新增字段：
```python
{
    "is_own_account": False,      # 是否自有账号
    "consuming_email": None,      # 消耗邮箱（自有账号时必填）
    "consuming_email_jwt": None,  # 消耗邮箱的 JWT
}
```

#### ✅ 前端账号来源交互

下拉切换设计：
- 选择邮箱池 → 显示邮箱池下拉
- 手动输入自有账号 → 显示邮箱+密码输入框 + 消耗邮箱选择

#### ⚠️ 待开发

1. spinbutton 多语言支持（中英双语）
2. 前端账号来源下拉切换

---

### 2025-12-31 17:00 UTC+8

**模块化架构设计 + 文档更新**

#### ✅ CLAUDE.md 新增内容

| 新增章节 | 内容 |
|---------|------|
| 模块化架构（核心设计原则） | 容错设计、可组合模块、复用关系 |
| 模式切换指南 | 一个模式出问题时如何切换 |
| 禁止重复造轮子 | 修改前必须搜索现有实现 |
| 后续扩展方向 | 链接模式、Telegram 机器人 |

#### ✅ 核心设计原则

```
一个模式出问题，还能用其他模式继续！

模式之间是可组合的模块：
- CDP 手动 = [用户手动登录] + [验证核心]
- CDP 全自动 = [自动退出/登录] + [验证核心]
- Camoufox = [启动浏览器] + [自动登录] + [验证核心]
```

#### ⚠️ 发现的重复实现

| 函数 | run_verify.py | camoufox_verify.py |
|------|---------------|-------------------|
| `detect_page_state` | 264行 | 471行 |
| `fill_sheerid_form` | 385行 | 546行 |
| `submit_form` | 491行 | 643行 |
| `click_try_again` | 511行 | 668行 |

**处理策略**：当前不大改，文档化记录，未来重构时统一。

---

### 2025-12-30 20:55 UTC+8

**修复验证成功后前端不自动刷新的问题**

#### ✅ 根因分析

| 问题 | 原因 |
|------|------|
| 前端不自动刷新 | 脚本验证成功后 `continue` 而不是 `return True` |
| 任务状态不变成 success | 脚本没有正确退出（退出码不是 0） |
| 邮箱池和账号列表不同步 | 前端只在 `task.status === 'success'` 时刷新 |

#### ✅ 修复内容

| 文件 | 修改 |
|------|------|
| `run_verify.py` | `state == "success"` 持久化后直接 `return True`，不再 `continue` |
| `run_verify.py` | `state == "success_claim"` 也持久化并 `return True` |
| `index.html` | 成功时同时刷新账号列表和邮箱池 |

#### 流程改进

```
验证成功检测（3 种状态都会立即持久化并返回）：
1. success: 页面显示 "You've been verified"
2. success_claim: veterans-claim 页面有 "Claim offer" 按钮
3. success_stripe: 到达 Stripe 支付页面（$0.00）

现在：检测到任意成功状态 → 持久化 → return True → 前端刷新
之前：检测到成功 → 持久化 → continue → 等待 Stripe → 超时/失败
```

---

### 2025-12-30 15:50 UTC+8

**新增 CDP 手动登录模式 + 修复日志编码问题**

#### 新增功能

**CDP 手动登录模式**（🔥 推荐调试）：

| 步骤 | 操作 |
|------|------|
| 1 | 启动 Chrome: `scripts\start-chrome-devtools.bat` |
| 2 | **你手动登录 ChatGPT**（确保登录成功） |
| 3 | 前端选择 "🔑 CDP 手动登录" 模式 |
| 4 | 选择临时邮箱 → 点击"开始验证" |
| 5 | 脚本跳过登录，直接填写 SheerID 表单 → 验证 |

**优点**：
- 登录由你控制，避免脚本登录问题
- 脚本只负责填表验证，更稳定
- 调试时可以随时介入

#### 修复内容

| 修复项 | 文件 | 说明 |
|-------|------|------|
| 日志 UTF-8 编码 | `run_verify.py` | Windows GBK 无法编码 ✓ 等特殊字符 |
| 登录循环问题 | `run_verify.py` | 重试时不覆盖已进入的 OpenAI 登录页面 |
| 日志实时 flush | `run_verify.py` | 每条日志后立即 flush |

---

### 2025-12-30 23:45 UTC+8

**修复 CDP 模式登录逻辑 + 实现应急手动登录模式**

#### ✅ 修复内容

| 修复项 | 文件 | 说明 |
|-------|------|------|
| `logout_chatgpt()` CDP 兼容 | `run_verify.py` | 添加超时机制 + JavaScript 清除存储 |
| 登录页面来回切换 | `run_verify.py` | 添加 `wait_for_page_change()` 等待页面变化确认 |
| 应急手动登录 | `app.py` + `templates/index.html` | 脚本卡住时显示邮箱密码供手动登录 |

#### 新增功能

**应急手动登录模式**：

当脚本卡在登录步骤时，用户可以：
1. 点击"🆘 应急登录"按钮
2. 查看邮箱和密码
3. 手动登录 ChatGPT
4. 点击"我已登录，继续验证"
5. 脚本跳过登录，继续后续验证流程

**API 接口**：
- `GET /api/verify/emergency/<email>` - 获取登录凭证
- `POST /api/verify/manual-continue/<email>` - 手动登录后继续

**脚本参数**：
- `--skip-login` - 跳过登录步骤（用户已手动登录）

#### 技术细节

**`logout_chatgpt()` 改进**：
```python
# 1. JavaScript 清除（CDP 兼容）
await page.evaluate("localStorage.clear(); sessionStorage.clear(); ...")

# 2. 点击退出按钮（有超时保护）
# 3. context.clear_cookies()（有超时保护）
# 4. 访问登出 URL
```

**`register_or_login_chatgpt()` 改进**：
```python
# 每次点击后等待页面变化确认
await wait_for_page_change(page, original_url, original_text, timeout=10)

# 添加重试机制
for retry in range(max_retries):
    ...
```

---

### 2025-12-31 06:30 UTC+8

**发现 CDP 模式脚本卡住问题** ✅ 已修复

| 问题 | 位置 | 现象 | 原因推测 |
|------|------|------|---------|
| logout 卡住 | `run_verify.py:669` | 脚本停在 "正在退出 ChatGPT 登录..." | `context.clear_cookies()` 在 CDP 模式下可能阻塞 |
| 日志停止 | 前端日志区 | 日志停在 06:16:23 不再更新 | 脚本异常/stdout 缓冲/WebSocket 断开 |

---

### 2025-12-30 23:00 UTC+8

**修复验证成功状态检测和持久化**

| 状态 | 页面特征 | 脚本动作 |
|------|---------|---------|
| `success` | "You've been verified" + Continue | 点击 Continue → continue 循环 |
| `success_claim` | veterans-claim 有 Claim offer | 点击 Claim offer → continue 循环 |
| `success_stripe` | Stripe 支付页面 $0.00 | **真正成功** → 持久化 |

**正确的成功流程**:
```
SheerID 验证通过 → "You've been verified" (success)
  → 点击 Continue
  → veterans-claim 有 "Claim offer" (success_claim)
  → 点击 Claim offer
  → Stripe 支付页面 $0.00 (success_stripe)
  → 检测登录账号 → 持久化
```

**持久化逻辑**:
- 检测真实登录账号（`get_logged_in_account`）
- 全自动模式：登录账号 = 接收邮箱 → 标记 verified
- 半自动模式：登录账号 ≠ 接收邮箱 → 接收邮箱标记 consumed，登录账号标记 verified

**修改文件**:
- `run_verify.py`: 三个成功状态分开处理（第 1288-1412 行）
- `email_pool.py`: 添加 `update_password()` 方法

---

### 2025-12-30 22:15 UTC+8

**完善 CDP 模式自动注册/登录功能**

| 新增功能 | 说明 |
|---------|------|
| `register_or_login_chatgpt()` | 通过页面状态检测自动注册或登录 |
| `get_account_password()` | 从数据库/邮箱池获取密码，或生成新密码 |
| `get_chatgpt_verification_code()` | 自动获取 ChatGPT 登录验证码 |
| `handle_about_you_page()` | 处理 about-you 确认年龄页面 |

**关键逻辑**：
- 不依赖数据库判断注册/登录，通过页面状态检测
- 输入邮箱后系统自动显示"创建密码"（新用户）或"输入密码"（已有用户）
- 自动处理验证码、about-you 页面、OpenAI Platform 跳转等情况

**修改文件**: `run_verify.py`
- 新增 4 个函数（第 697-1009 行）
- 修改 `run_verify_loop()` 集成自动登录（第 1269-1279 行、第 1447-1458 行、第 1482-1494 行）

**更新 TODO.md 开发规则**
- MCP 用途：监控/调试，禁止手动完成验证流程
- 选择器文档：一份 `page-selectors.md` 两个模式共用
- 注册/登录判断：通过页面状态检测，不依赖持久化

---

### 2025-12-30 18:30 UTC+8

**修复验证码提取逻辑**

| 问题 | 原因 | 修复 |
|------|------|------|
| 返回 `OPENAI` | 兜底模式匹配到常见词 | 添加 `EXCLUDE_CODES` 排除列表 |
| 返回 `009025` | 邮箱域名被误识别 | 排除列表 + 发件人过滤 |
| Subject 无法解析 | Base64 编码未处理 | 新增 `_decode_subject()` 函数 |

**修改文件**: `email_manager.py`
- 新增 `_decode_subject()` 函数解码 Subject
- 添加 `EXCLUDE_CODES = {'OPENAI', 'CHATGP', '009025', '000000'}`
- 只处理 OpenAI 发件人的邮件

**完善 camoufox_verify.py**

| 修复项 | 说明 |
|--------|------|
| about-you 页面 | 使用 `get_by_role("spinbutton")` 填写生日 |
| 验证码输入 | 优先使用 `get_by_role("textbox", name="代码")` |
| Status 选择后等待 | 等待 "Verifying your military status" 加载完成 |

---

### 2025-12-30 17:45 UTC+8

**修复 Camoufox 持久化配置**

| 问题 | 原因 | 修复 |
|------|------|------|
| Camoufox 启动失败 | `user_data_dir` 参数错误 | 添加 `persistent_context=True` |
| 错误信息 | `BrowserType.launch() got an unexpected keyword argument 'user_data_dir'` | 配合使用 `persistent_context` 和 `user_data_dir` |

**修改文件**: `automation/camoufox_verify.py:140-147`

```python
config = {
    "headless": self.headless,
    "geoip": True,
    "locale": "en-US",
    "humanize": True,
    "persistent_context": True,  # 🔥 新增：启用持久化上下文
    "user_data_dir": str(profile_path),
}
```

**修正 TODO.md 固化开发流程**

- 明确：通过 7870 前端 API 启动任务，而非手动 MCP 操作
- MCP 用于监控/调试，脚本自动获取验证码

---

### 2025-12-30 06:15 UTC+8

**修复 run_verify.py 状态检测**

| 新增/修改 | 说明 |
|-----------|------|
| `veterans_claim_not_logged_in` 状态 | 检测到未登录时自动点击登录按钮 |
| `verify_btn_failures` 计数器 | 连续3次找不到验证按钮 → 退出登录 |
| 改进状态检测逻辑 | 区分已登录/未登录，检测 "Log in"/"Get started" 按钮 |

**配置 chrome-devtools MCP**

- 在 `~/.claude.json` 中为 `E:/veterans-verify` 启用 `chrome-devtools`
- 重启 Claude Code 后可用 `mcp__chrome-devtools__*` 工具直接控制浏览器
- 端口：9488，启动脚本：`scripts\start-chrome-devtools.bat`

---

### 2025-12-30 03:00 UTC+8

**修复 SheerID 表单填写逻辑**

| 修复项 | 之前 | 现在 |
|--------|------|------|
| Status 字段值 | `"Military Veteran"` ❌ | `"Military Veteran or Retiree"` ✅ |
| 下拉框定位 | ID 选择器 `#sid-xxx` | `get_by_role("combobox", name="...")` |
| Status 检测 | 无（直接操作） | 动态检测，有则选无则跳过 |
| Day/Year 定位 | 独立 ID | `.nth(0)/.nth(1)` 区分两组 |

**新增代理模式选择**

前端单账号验证新增三种代理模式：
- 🌐 **直连**：不使用代理（推荐测试）
- 📍 **固定代理**：用户输入指定代理地址
- 🔄 **代理池轮换**：从代理池自动选择

后端 API 新增参数：
```json
{
    "proxy_mode": "none|fixed|pool",
    "fixed_proxy": "http://user:pass@ip:port"
}
```

---

### 2025-12-30 00:30 UTC+8

**Camoufox 可视化模式测试通过**

- 验证 `headless=False` 模式正常弹出浏览器窗口
- 前端 → 后端 → Camoufox 调用链正确

**代理管理完善**

| 功能 | 说明 |
|------|------|
| 前端上传自动保存 | 上传代理文件后自动保存到 `data/proxies_{protocol}.txt` |
| 粘贴保存 | 粘贴代理后点击"保存到代理池"自动保存 |
| 自动去重 | 不保存已存在的代理 |
| BOM 处理 | 上传时自动处理 UTF-8 BOM |
| 自动发现 | config.py 自动加载 `data/proxies_*.txt` |

**新增配置**

```bash
# .env.local 新增
PROXY_HTTP_FILE=./data/http美国.txt
PROXY_MODE=pool_with_fallback
```

---

### 2025-12-29 22:00 UTC+8

**文档重构**

| 文档 | 变更 |
|------|------|
| CLAUDE.md | 精简为纯规则（947 → 198 行）|
| TODO.md | 新建，动态 3 任务管理 |
| PLAN.md | 整合重要描述（本文件）|

**职责明确**：
- CLAUDE.md = 规则
- TODO.md = 动态任务（3个）
- PLAN.md = 整体方向 + 数据标准 + 流程说明

---

### 2025-12-29 11:00 UTC+8

**模式架构重新设计**

- Camoufox 可视化替代 CDP（解决固定指纹问题）
- 前端四种模式：可视化调试、全自动后台、自有账号、CDP高级

**代理解析修复**

- `'\\n'` → `'\n'`（app.py 两处）

---

### 2025-12-28 23:50 UTC+8

**Profile 持久化 + 代理管理**

- `profile_manager.py` - 每账号独立指纹
- `proxy_manager.py` - 代理池轮换
- `scripts/sync_env.py` - 环境变量同步

---

### 2025-12-28 05:50 UTC+8

**模式合并**

4 种模式 → 3 种（邮箱池、全自动批量、单账号验证）

---

### 2025-12-27 22:30 UTC+8

**脚本逻辑完善**

- 新任务启动时检测并退出上一个账号
- 半自动成功后保持登录
- 批量模式成功后退出登录

---

### 2025-12-26 UTC+8

**选择器更新**

- Status 字段动态检测
- SheerID 表单语义化选择器
- 验证邮件链接自动点击
