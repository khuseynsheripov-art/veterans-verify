# Veterans Verify - Claude Code 规则

> ⚠️ **重要**: 每次完善逻辑或更新方向时，请同步更新 `PLAN.md`

---

## 🔗 项目固定信息

| 项目 | 值 |
|------|-----|
| **GitHub 仓库** | https://github.com/khuseynsheripov-art/veterans-verify.git |
| **Veterans 验证入口** | https://chatgpt.com/veterans-claim |
| **临时邮箱前端** | https://one.009025.xyz/ |
| **本地服务端口** | 7870 |
| **开发测试账号** | `data/dev_test_account.json` |

---

## 🚀 开发测试流程（固化）

### 每次会话开始时

```
1. 阅读文档获取上下文:
   - CLAUDE.md - 项目规则
   - PLAN.md - 开发计划和进度
   - 会话记录总阶.md - 上次会话待完成任务
   - docs/page-selectors.md - 页面选择器

2. 启动开发环境:
   - 运行 scripts\start-chrome-devtools.bat（Chrome 9488 端口）
   - 运行 python app.py（Flask 7870 端口）

3. 测试自动化脚本:
   - 前端选择模式，开始验证
   - 监控日志，发现问题
   - 完善脚本逻辑

4. 更新文档:
   - 新发现的页面结构 → docs/page-selectors.md
   - 完成的任务和进度 → PLAN.md
   - 会话总结 → 会话记录总阶.md
```

### 四种模式测试目标

| 模式 | 测试目标 | 成功后行为 |
|------|---------|-----------|
| 邮箱池管理 | 批量创建邮箱 | - |
| 全自动批量 | 验证 N 个成功后暂停 | 自动退出登录，继续下一个 |
| 半自动-脚本登录 | 验证成功 | 保持登录（用户可能需要绑卡）|
| 半自动-手动登录 | 验证成功 | 保持登录（用户可能需要绑卡）|

### 关键注意事项

- **登录/退出必须在 chatgpt.com 主页进行**，不是 veterans-claim
- **Status 字段动态显示**，有些页面有有些没有，需要检测
- **新任务启动时自动检测并退出上一个账号**（Stripe/Claim offer 页面）

---

## 🔀 Git 规范（强制）

### 分支策略

| 分支 | 用途 | 保护 |
|------|------|------|
| `main` | 稳定版本，可直接运行 | 重大改动需测试后合并 |
| `dev` | 开发分支，日常开发 | 功能完成后合并到 main |
| `feature/*` | 新功能分支 | 可选 |

### 工作流程

```
1. 日常开发在 dev 分支
2. 功能完成且测试通过 → 合并到 main
3. 重大改动先在 dev 测试
4. main 分支保持可运行状态
```

### 提交规范

```bash
# 提交信息必须中文
git commit -m "修复: 验证码提取逻辑"
git commit -m "新增: SheerID Status 字段"
git commit -m "优化: 选择器更新"

# 不要添加 AI 署名
# ❌ Co-Authored-By: Claude ...
# ✅ 只写功能描述
```

### 提交类型

| 前缀 | 说明 |
|------|------|
| `新增:` | 新功能 |
| `修复:` | Bug 修复 |
| `优化:` | 代码优化 |
| `文档:` | 文档更新 |
| `重构:` | 代码重构 |

---

## 📋 文档同步规则（强制）

### 必须同步的文档

| 文档 | 更新时机 | 内容 |
|------|---------|------|
| `PLAN.md` | 每次代码修改后 | 更新日志（带时间戳）、进度状态 |
| `CLAUDE.md` | 规则变更时 | 项目规则、流程说明 |
| `docs/page-selectors.md` | **每次页面探索后（强制）** | 见下方详细规则 |

### page-selectors.md 强制更新规则

⚠️ **使用 Chrome MCP 探索页面后必须更新此文档**，记录：

1. **新发现的页面结构**
   - URL 模式
   - 页面标题/标识
   - 关键元素选择器

2. **真实网页报错**
   - 错误页面截图描述
   - 错误信息文本
   - 触发条件
   - 解决方案

3. **页面跳转关系**
   - A 页面 → B 页面的触发条件
   - 异常跳转（如跳转到 OpenAI Platform）

4. **验证码/邮件格式**
   - Subject 格式
   - 验证码提取正则

5. **账号状态问题**
   - 登录状态丢失场景
   - Cookie/Session 问题

### 时间戳格式

所有更新日志必须包含时间戳：
```
### 2025-12-25 20:27 UTC+8
```

### 上下文文档

开始新会话时，必须阅读以下文档获取上下文：
1. `CLAUDE.md` - 项目规则
2. `PLAN.md` - 开发计划和进度
3. `docs/page-selectors.md` - 页面选择器

---

## 📧 账号持久化规则（强制）

### 两种凭证区分

| 凭证类型 | 用途 | 来源 | 登录地址 |
|---------|------|------|---------|
| **ChatGPT 账号** | 登录 ChatGPT 使用 Plus | 我们生成密码 | https://chatgpt.com |
| **临时邮箱** | 查看验证码/链接 | API 返回 JWT | https://one.009025.xyz/ |

### 必须保存的信息

```python
{
    # === ChatGPT 账号（用户需要的核心信息）===
    "email": "xxx@009025.xyz",           # 邮箱地址（同时用于 ChatGPT 登录）
    "chatgpt_password": "生成的16位密码",  # ChatGPT 登录密码（我们生成）

    # === 临时邮箱凭证 ===
    "email_jwt": "eyJ...",               # 邮箱 JWT（API 返回，用于查询邮件）
    "email_login_url": "https://one.009025.xyz/",  # 前端登录地址

    # === 状态追踪 ===
    "status": "pending|registering|verifying|success|failed",
    "error_type": "",                    # 失败原因
    "error_message": "",

    # === 军人数据（BIRLS）===
    "veteran_data": {
        "first_name": "John",
        "last_name": "Smith",
        "branch": "Army",
        "birth_date": {"month": "March", "day": "15", "year": "1985"},
        "discharge_date": {"month": "June", "day": "20", "year": "2024"}
    },

    # === 时间戳 ===
    "created_at": "2025-12-25T20:27:00",
    "updated_at": "2025-12-25T20:30:00"
}
```

### 状态流转

```
pending → registering → verifying → success
                    ↘          ↘
                     failed ←←←←
```

| 状态 | 说明 | 下一步 |
|------|------|--------|
| `pending` | 等待处理 | 自动开始 |
| `registering` | 注册 ChatGPT 中 | 等待验证码 |
| `verifying` | SheerID 验证中 | 等待验证链接 |
| `success` | 验证成功，获得 1 年 Plus | 可导出 |
| `failed` | 失败 | 可重试 |

### 临时邮箱登录说明

**API 创建邮箱时**：
- 返回 `jwt`（JSON Web Token）和 `address`
- **没有传统密码**，JWT 就是认证凭证

**前端登录 https://one.009025.xyz/**：
- 输入邮箱地址即可登录
- 无需密码（服务端验证地址）
- 可查看 ChatGPT 验证码和 SheerID 链接

**给用户的信息**：
```
ChatGPT 登录：
  - 邮箱：xxx@009025.xyz
  - 密码：xxxxxxxxxx（我们生成的）

查看邮件：
  - 访问 https://one.009025.xyz/
  - 输入邮箱地址即可
```

---

## 项目概述
ChatGPT Veterans 验证自动化系统：真实公开数据 + 注册ChatGPT → SheerID表单 → 邮箱验证链接

## 开发上下文

**详细开发计划请查看 → [PLAN.md](./PLAN.md)**

包含：
- 完整流程图
- 数据来源说明
- 技术架构
- 错误类型枚举
- 开发阶段规划
- 更新日志

## 验证流程（2025-12-26 更新）

### 完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    全自动模式                                │
├─────────────────────────────────────────────────────────────┤
│ 1. 创建临时邮箱                                              │
│ 2. 打开 veterans-claim → 注册 ChatGPT                       │
│ 3. 输入验证码 → 确认年龄                                     │
│ 4. 进入 SheerID 验证                                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    半自动模式（从这里开始）                   │
│                    用户已手动登录 ChatGPT                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │               验证循环（核心）                         │   │
│  │                                                       │   │
│  │  获取军人数据 → 填写表单 → 提交 → 检查结果            │   │
│  │       ↑                              │                │   │
│  │       │         ┌────────────────────┴───────┐       │   │
│  │       │         │                            │       │   │
│  │       │   "You've been verified"      其他情况       │   │
│  │       │   + Continue 按钮             (消耗)         │   │
│  │       │         │                            │       │   │
│  │       │         ↓                            │       │   │
│  │       │    记录成功 ✅                        │       │   │
│  │       │    完成！                            │       │   │
│  │       │                                      │       │   │
│  │       └──────────────────────────────────────┘       │   │
│  │                                                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 成功标识（重要！）

**只有看到这个才算成功**：
```
标题: "You've been verified"
按钮: "Continue" → 点击后跳转 chatgpt.com
```

其他任何情况都是**消耗**，需要换下一条军人数据继续尝试。

### 四种操作模式（2025-12-26 最终版）

```
┌─────────────────────────────────────────────────────────────────────┐
│                      四种操作模式                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  📦 模式 1: 批量创建邮箱（邮箱池）                                  │
│     - 只创建临时邮箱，持久化到 data/email_pool.json                 │
│     - 状态管理: available | in_use | verified | failed              │
│     - 前端可查看、选择、删除邮箱                                    │
│                                                                      │
│  🚀 模式 2: 全自动（新账号 + 验证）                                 │
│     - 创建新邮箱（或从邮箱池选择）                                  │
│     - 注册 ChatGPT → 自动获取验证码 → 确认年龄                     │
│     - SheerID 验证循环直至成功                                      │
│     - 完全自动化，无需人工干预                                      │
│                                                                      │
│  🔧 模式 3: 半自动 - 脚本登录                                       │
│     - 输入: ChatGPT 账号密码 + 临时邮箱地址 + JWT                   │
│     - 脚本自动登录 ChatGPT（可能需要人工输入验证码）               │
│     - 登录成功后自动进入 SheerID 验证循环                          │
│     - 用 JWT 自动点击验证链接                                       │
│                                                                      │
│  👤 模式 4: 半自动 - 手动登录后接管                                 │
│     - 用户先手动登录 ChatGPT（绕过复杂登录验证）                   │
│     - 输入: 临时邮箱地址 + JWT                                      │
│     - 脚本通过 CDP 连接已打开的浏览器                               │
│     - 自动进入 SheerID 验证循环                                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

| 模式 | 登录方式 | 输入 | 自动化程度 |
|------|---------|------|-----------|
| 批量创建邮箱 | - | 数量 | 100% |
| 全自动 | 自动注册 | 无/选择邮箱 | 100% |
| 半自动-脚本登录 | 脚本登录 | 账号密码 + 邮箱JWT | 95%（可能需输入验证码）|
| 半自动-手动登录 | 用户手动登录 | 邮箱JWT | 100%（登录后）|

### 模式3和4的区别

**关键理解**：ChatGPT 账号邮箱 ≠ SheerID 表单邮箱

```
模式3（脚本登录）:
  输入:
    - ChatGPT 账号密码（自有邮箱，如 Gmail）
    - 临时邮箱 + JWT（用于 SheerID 表单，自动点击验证链接）

  流程: 脚本登录 ChatGPT → 填 SheerID 表单（邮箱填临时邮箱）→ 自动点击链接

模式4（手动登录后接管）:
  用户操作: 手动登录 ChatGPT（自有账号）
  输入: 临时邮箱 + JWT（用于 SheerID 表单）

  流程: 脚本接管浏览器 → 填 SheerID 表单（邮箱填临时邮箱）→ 自动点击链接
```

**为什么可以这样？**
- SheerID 验证只需要一个能收邮件的邮箱
- 验证链接发到哪个邮箱，ChatGPT 就给登陆账号加 Plus
- 所以用临时邮箱接收链接，自动化点击后，自有 GPT 账号获得 Plus

### 模式4 操作流程

```
步骤 1: 启动浏览器
  运行 scripts/start-browser.bat（启动带调试端口的浏览器）

步骤 2: 手动登录
  在浏览器中登录 ChatGPT（处理任何验证）

步骤 3: 前端操作
  选择模式4 → 输入临时邮箱地址 + JWT → 点击开始

步骤 4: 脚本接管
  连接浏览器 → 访问 veterans-claim → SheerID 验证循环 → 自动点击验证链接
```

### 邮箱凭证说明

**API 创建邮箱时返回：**
```json
{
  "jwt": "eyJ...",           // 程序用：API 查询邮件
  "address": "xxx@009025.xyz" // 用户用：邮箱地址
}
```

**前端登录 https://one.009025.xyz/：**
- ✅ 只需输入邮箱地址（无需密码）
- ✅ 服务端验证地址存在性
- ✅ 可查看该邮箱的所有收件

**给用户的信息：**
```
ChatGPT 登录：
  邮箱: xxx@009025.xyz
  密码: xxxxxxxxxxxxxxxx（16位，我们生成的）

查看验证邮件：
  访问 https://one.009025.xyz/
  输入邮箱地址即可登录
```  

**关键发现（2025-12-25 Chrome MCP 探索）：**
- 🆕 新用户注册后有**确认年龄页面** `auth.openai.com/about-you`
- 🆕 SheerID 表单第一个字段是 **Status**（选择 Military Veteran or Retiree）
- SheerID 页面需要先登录 ChatGPT 才能访问
- 会收到两封邮件：ChatGPT 验证码 + SheerID 验证链接
- 验证码在邮件 Subject 中：`你的 ChatGPT 代码为 XXXXXX`

## 数据来源：BIRLS 数据库

### 在线搜索（推荐）

**网站**: https://www.birls.org/

- **19.5M+ 已故美国退伍军人**公开数据库
- 可按姓名、生日、服役日期、军种等搜索
- 2024年12月上线，2025年9月更新 150万条新记录
- 包含 SSN、军种、入伍/退役日期等详细信息
- **用途**：验证数据准确性、查找更多有效数据

### 本地数据（当前使用）

使用真实公开退伍军人信息（[BIRLS Database](https://archive.org/details/BIRLS_database)）：

| 字段 | 来源 | 说明 |
|------|------|------|
| First name | BIRLS 真实数据 | 已故军人公开信息 |
| Last name | BIRLS 真实数据 | |
| Birth date | BIRLS 真实数据 | 筛选 1980-2005 年生的 |
| Branch | BIRLS 真实数据 | Army/Navy/Air Force/Marine Corps/Coast Guard |
| Discharge date | **随机生成** | 过去 1-11 个月内 |
| Email | **临时邮箱** | Cloudflare Worker 创建 |

**当前数据统计（birls_update.csv）：**
- 有效记录：19,605 条
- Army: 10,247 | Marine Corps: 3,759 | Navy: 3,098 | Air Force: 2,326 | Coast Guard: 175

## 表单字段（SheerID）

| 字段 | 类型 | 选项/格式 | 自动化方式 |
|------|------|----------|-----------|
| 🆕 **Status** | 下拉 | Active Duty / **Military Veteran or Retiree** / Reservist or National Guard | select_dropdown |
| Branch of service | 下拉 | Air Force / Army / Coast Guard / Marine Corps / Navy / Space Force | select_dropdown |
| First name | 文本 | | human_type |
| Last name | 文本 | | human_type |
| Date of birth | 日期 | Month(下拉) + Day + Year | 月: select_dropdown, 日/年: human_type |
| Discharge date | 日期 | Month(下拉) + Day + Year | ⚠️ **必须在过去12个月内！** |
| Email address | 文本 | 接收验证链接 | human_type |

**Status 字段选择**：必须选择 "Military Veteran or Retiree"（退伍军人）

---

## 技术栈
- **语言**: Python 3.10+
- **浏览器自动化**: Camoufox (最强反检测，Firefox C++ 级修改)
- **Web 框架**: Flask
- **前端**: Vue 3 (CDN)
- **邮箱服务**: Cloudflare Worker 临时邮箱
- **数据来源**: BIRLS 数据库（真实退伍军人公开信息）

## 项目结构
```
veterans-verify/
├── app.py                  # Flask 主应用（API + Web 界面）
├── browser_worker.py       # Camoufox 浏览器自动化核心
├── email_manager.py        # 邮箱验证码/链接处理
├── veteran_data.py         # 退伍军人数据管理（BIRLS）
├── config.py               # 完整配置管理
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量示例
├── data/
│   ├── birls_update.csv    # BIRLS 原始数据（199MB）
│   ├── veterans_processed.json  # 处理后的有效数据
│   └── veterans_used.json  # 已使用记录
├── screenshots/            # 调试截图
├── templates/
│   ├── login.html          # 登录页面
│   └── index.html          # 管理界面
└── CLAUDE.md               # 本文件
```

---

## ⚠️ 强制规则（必须遵守）

### 1. 反检测策略
```
浏览器层（Camoufox 优势）：
- Firefox C++ 级修改（非 JavaScript 注入）
- 0% headless 检测率（vs Patchright 67%）
- 完整指纹伪造（navigator、screen、WebGL、canvas、audio 等）
- 内置人类光标移动算法
- GeoIP 自动指纹匹配

时间随机化：
- 所有延迟使用正态分布随机
- 打字速度 50-150ms/字符
- 请求间隔 30s-2min 随机
- 字段切换延迟 0.3-0.8s

止损与恢复：
- 单项失败 → 冷却 15 分钟
- 连续失败 3 次 → 全局暂停 3-8 分钟
- Captcha 触发 → 暂停 10 分钟
- 暂停后自动恢复，继续队列
```

### 2. 数据规则
```
⚠️ 退伍日期限制：必须在过去 12 个月内！
   - 例如今天是 2025-12-24，有效范围 = 2024-12-24 ~ 2025-12-24
   - 超出此范围会显示 "Invalid discharge date"
   - 代码自动计算：当前日期往前 1-11 个月随机

姓名/生日/军种：使用 BIRLS 真实数据
退伍日期：动态随机生成（过去 1-11 个月）
邮箱：临时邮箱，接收两封邮件：
  1. ChatGPT 验证码（6位数字/字母）
  2. SheerID 验证链接（https://services.sheerid.com/verify/...）
```

### 3. 错误类型枚举（2025-12-26 更新）

```python
# 验证结果类型
RESULT_TYPES = {
    # === 成功 ===
    "SUCCESS": "You've been verified + Continue 按钮",

    # === 消耗类（换下一条数据继续）===
    "VERIFICATION_LIMIT_EXCEEDED": "军人数据已被验证过",
    "NOT_APPROVED": "邮件验证后被拒绝",
    "INVALID_DISCHARGE_DATE": "退伍日期无效（超过12个月）",
    "UNABLE_TO_VERIFY": "信息无法验证",

    # === 需要操作 ===
    "CHECK_EMAIL": "等待邮件验证（去邮箱点链接）",
    "PLEASE_LOGIN": "需要登录 ChatGPT",
    "VERIFYING": "正在验证中（等待）",

    # === 错误 ===
    "FORM_FILL_ERROR": "表单填写失败",
    "NETWORK_ERROR": "网络错误",
    "UNKNOWN_ERROR": "未知错误",
}

# 处理逻辑
# - SUCCESS → 记录成功，完成
# - 消耗类 → 标记已消耗，获取下一条数据，继续循环
# - 需要操作 → 执行对应操作后继续
# - 错误 → 重试或暂停
```

### 4. 前端自动化设计（待开发）

```
┌─────────────────────────────────────────┐
│         Veterans Verify 前端            │
├─────────────────────────────────────────┤
│                                         │
│  [选择模式]                             │
│  ○ 全自动（创建账号+验证）              │
│  ● 半自动（已登录，只验证）             │
│                                         │
│  [邮箱类型]                             │
│  ● 临时邮箱 (@009025.xyz)              │
│    邮箱地址: [____________]             │
│  ○ 自有邮箱（手动查看邮件）             │
│                                         │
│  [当前状态]                             │
│  账号: vethuxntarz@009025.xyz          │
│  军人数据: Brian Sears (Army)          │
│  尝试次数: 3                            │
│  状态: 等待邮件验证                     │
│                                         │
│  [开始验证] [暂停] [停止]               │
│                                         │
│  [日志]                                 │
│  > 填写表单: Brian Sears               │
│  > 提交成功，等待邮件...               │
│  > 点击验证链接...                      │
│                                         │
└─────────────────────────────────────────┘
```

---

## 参考项目（可复用代码）

> ⚠️ 本项目与以下两个项目逻辑相似，只是目标页面不同。**遇到问题时必须优先参考这些项目的实现**。

### 🔍 何时查看参考项目（开发调试规则）

| 遇到问题 | 查看项目 | 具体文件 |
|---------|---------|---------|
| 邮箱创建失败 | test_band | `email_manager.py` - API 调用逻辑 |
| 验证码提取失败 | test_band | `email_manager.py` - 正则匹配模式 |
| 前端显示异常 | test_band | `templates/index.html` - Vue 组件 |
| 账号状态不同步 | test_band | `account_manager.py` - 状态持久化 |
| SheerID 表单填写失败 | K-12 | `one/sheerid_verifier.py` - API 方式 |
| 选择器失效 | K-12 | `notes/` - 页面结构分析 |
| 提交按钮 disabled | K-12 | 检查必填字段逻辑 |

### ⚡ 快速定位问题

```bash
# 邮箱相关问题
查看: E:\test_band_gemini_mail\email_manager.py

# SheerID 表单问题
查看: E:\K-12项目\tgbot-verify\one\sheerid_verifier.py

# 前端界面问题
查看: E:\test_band_gemini_mail\templates\index.html

# 批量管理问题
查看: E:\test_band_gemini_mail\app.py
```

---

### test_band_gemini_mail（邮箱+批量注册）

**路径**: `E:\test_band_gemini_mail`

**项目说明**: Gemini 批量注册自动化，使用相同的临时邮箱服务

**复用内容**:
| 模块 | 文件 | 说明 |
|------|------|------|
| 邮箱服务 | `email_manager.py` | Cloudflare Worker 临时邮箱 API |
| 账号管理 | `account_manager.py` | 批量创建、状态追踪、持久化 |
| Flask 架构 | `app.py` | API 路由、认证、前端模板 |
| 前端界面 | `templates/` | Vue 3 CDN 管理界面 |
| 止损机制 | 冷却逻辑 | 连续失败暂停 |

**关键实现参考**:
```python
# 验证码提取（支持多种格式）
patterns = [
    r'class=["\']?verification-code["\']?[^>]*>([A-Z0-9]{6})</span>',
    r'>([A-Z0-9]{6})</span>',
    r'font-size:\s*28px[^>]*>([A-Z0-9]{6})<',
]
# 兜底：提取任意 6 位字母数字组合
```

### K-12项目（SheerID 验证）

**路径**: `E:\K-12项目`

**项目说明**: K-12 教育优惠验证，使用 SheerID 表单（与本项目表单结构相似）

**复用内容**:
| 模块 | 文件 | 说明 |
|------|------|------|
| SheerID API | `one/sheerid_verifier.py` | HTTP API 直接验证（非浏览器） |
| 设备指纹 | `sheerid_verifier.py` | 32位随机指纹生成 |
| 选择器 | `notes/` | CSS 选择器记录 |

**关键实现参考**:
```python
# SheerID API 端点
SHEERID_BASE_URL = "https://services.sheerid.com"

# 设备指纹生成
def _generate_device_fingerprint() -> str:
    chars = '0123456789abcdef'
    return ''.join(random.choice(chars) for _ in range(32))
```

⚠️ **注意**: K-12 项目使用 HTTP API 方式，本项目使用浏览器自动化方式。表单字段逻辑可参考，但实现方式不同。

---

## 🔧 环境变量管理（重要）

### 配置文件分离

```
.env.example    # 模板文件，提交到 Git，包含所有参数说明
.env.local      # 用户配置，不提交到 Git（已加入 .gitignore）
```

### 加载顺序

```python
# config.py 中的加载逻辑
load_dotenv('.env.example')        # 1. 先加载默认值
load_dotenv('.env.local', override=True)  # 2. 再加载用户配置，覆盖默认值
```

### 新增参数时的规则

当开发过程中需要新增环境变量：

1. **在 .env.example 中添加**：包含参数说明和默认值
2. **在 PLAN.md 中记录**：更新日志中标明新增了什么参数
3. **用户只需在 .env.local 中添加**：不会影响已有配置

### 示例

```bash
# .env.example（模板）
# 新增于 2025-12-26
NEW_FEATURE_ENABLED=false  # 是否启用新功能
NEW_FEATURE_TIMEOUT=30     # 新功能超时时间(秒)

# .env.local（用户配置）
ADMIN_PASSWORD=my_secret_password
NEW_FEATURE_ENABLED=true   # 只需添加需要覆盖的参数
```

---

## 快速启动

```bash
# 1. 安装依赖
cd E:/veterans-verify
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入邮箱服务配置

# 3. 处理 BIRLS 数据（首次）
python veteran_data.py

# 4. 启动服务
python app.py
# 访问 http://localhost:7870
```

---

## 环境变量分类

### 必填配置
```bash
# 管理员认证
ADMIN_PASSWORD=xxx
ADMIN_TOKEN=xxx

# 邮箱服务（复用 test_band 的 Worker）
WORKER_DOMAINS=apimail.example.com
EMAIL_DOMAINS=example.com
ADMIN_PASSWORDS=xxx
```

### 浏览器配置
```bash
MAX_WORKERS=1              # 最大并发数
HEADLESS=true              # 无头模式
PROXY_SERVER=              # 代理（可选）
DEBUG_SCREENSHOT_DIR=screenshots  # 调试截图目录
```

### Chrome MCP 调试配置（重要）

⚠️ **必须先手动启动 Chrome 实例，再使用 Claude Code**

#### 正确的使用流程（2025-12-25 验证成功）

```
步骤 1: 关闭所有 Chrome 窗口
步骤 2: 运行启动脚本 → scripts\start-chrome-devtools.bat
步骤 3: 等待 Chrome 打开（带远程调试端口）
步骤 4: 启动/重启 Claude Code
步骤 5: Claude Code 调用 mcp__chrome-devtools__* 工具
```

#### 关键配置说明

| 配置项 | 值 | 说明 |
|--------|-----|------|
| **调试端口** | 9488 | Chrome 远程调试端口 |
| **Profile 目录** | `C:\temp\codex-chrome-profile` | 插件/登录状态持久化 |
| **MCP 配置** | `chrome-devtools` | 连接到 `127.0.0.1:9488` |

#### 启动脚本内容 (`scripts\start-chrome-devtools.bat`)

```batch
set PORT=9488
set USER_DATA=C:\temp\codex-chrome-profile
start "" %CHROME% --remote-debugging-address=127.0.0.1 --remote-debugging-port=%PORT% --user-data-dir="%USER_DATA%"
```

#### MCP 全局配置 (`C:\Users\asus\.claude\.mcp.json`)

```json
{
  "chrome-devtools": {
    "args": [
      "--browserUrl", "http://127.0.0.1:9488",
      "--proxyServer", "direct://"
    ],
    "env": {
      "NO_PROXY": "127.0.0.1,localhost,::1",
      "HTTP_PROXY": "",
      "HTTPS_PROXY": ""
    }
  }
}
```

#### 为什么必须先启动脚本？

1. **Chrome v143+ 限制**：必须使用非默认 `--user-data-dir` 才能启用远程调试
2. **端口监听**：脚本启动的 Chrome 会监听 9488 端口，MCP 连接该端口
3. **插件持久化**：使用固定 Profile 目录，代理插件等配置会保留
4. **代理绕过**：`NO_PROXY` 环境变量确保 127.0.0.1 不走系统代理

#### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| MCP 连接失败 | 没有先启动脚本 | 先运行 `start-chrome-devtools.bat` |
| 端口不监听 | Chrome 使用了默认 Profile | 检查脚本的 `--user-data-dir` 参数 |
| 代理干扰 | 系统代理拦截了 127.0.0.1 | 检查 `NO_PROXY` 环境变量 |
| 插件丢失 | 使用了新的 Profile 目录 | 重新安装插件到持久化目录 |

### 人类行为模拟
```bash
HUMAN_DELAY_MIN=50         # 打字最小延迟(ms)
HUMAN_DELAY_MAX=150        # 打字最大延迟(ms)
REQUEST_INTERVAL_MIN=30    # 请求最小间隔(s)
REQUEST_INTERVAL_MAX=120   # 请求最大间隔(s)
FIELD_DELAY_MIN=0.3        # 字段切换最小延迟(s)
FIELD_DELAY_MAX=0.8        # 字段切换最大延迟(s)
```

### 止损配置
```bash
MAX_CONSECUTIVE_FAILURES=3 # 最大连续失败次数
COOLDOWN_MIN_SECONDS=180   # 冷却最小时间
COOLDOWN_MAX_SECONDS=480   # 冷却最大时间
CAPTCHA_COOLDOWN_SECONDS=600  # Captcha 冷却时间
```

---

## API 接口

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/status` | 系统状态 |
| GET | `/api/tasks` | 任务列表 |
| POST | `/api/tasks` | 创建任务 |
| GET | `/api/tasks/<id>` | 任务详情 |
| DELETE | `/api/tasks/<id>` | 删除任务 |
| POST | `/api/pause` | 暂停队列 |
| POST | `/api/resume` | 恢复队列 |

---

## 代码风格

- 4 空格缩进（Python 标准）
- 使用 Type Hints
- 日志使用 logging 模块
- 异步操作使用 asyncio
