# Veterans Verify - Claude Code 规则

> ⚠️ **重要**: 每次完善逻辑或更新方向时，请同步更新 `PLAN.md`
>
> 本文件包含规则和参考信息。动态任务请看 `TODO.md`，整体进度请看 `PLAN.md`

---

## 项目固定信息

| 项目 | 值 |
|------|-----|
| **GitHub 仓库** | https://github.com/khuseynsheripov-art/veterans-verify.git |
| **Veterans 验证入口** | https://chatgpt.com/veterans-claim |
| **临时邮箱前端** | https://one.009025.xyz/ |
| **本地服务端口** | 7870 |
| **BIRLS 数据** | 19,605 条真实退伍军人数据 |
| **开发测试账号** | `data/dev_test_account.json` |

---

## 🎯 模式设计（核心）

### 七种操作模式

| 模式 | 浏览器 | 账号来源 | 登录方式 | 需要选择账号？ | 说明 |
|------|--------|---------|---------|--------------|------|
| **邮箱池管理** | - | - | - | - | 独立功能，创建/管理临时邮箱 |
| **Camoufox 批量** | 无头 | 临时邮箱 | 脚本自动 | ❌ 固定 | 自动创建邮箱→注册→验证→下一个 |
| **Camoufox 可视化** | 有窗口 | 临时/自有 | 脚本自动 | ✅ 需要 | 调试用，支持两种账号 |
| **Camoufox 无头全自动** | 无头 | 临时邮箱 | 脚本自动 | ❌ 固定 | 单个临时邮箱全自动 |
| **Camoufox 无头自有** | 无头 | 自有账号 | 脚本自动 | ❌ 固定 | 单个自有账号 |
| **CDP 全自动** | CDP Chrome | 临时邮箱 | 脚本自动 | ❌ 固定 | 单个临时邮箱，CDP 连接 |
| **CDP 手动** | CDP Chrome | 临时/自有 | 用户手动 | ✅ 需要 | **保底机制**，用户手动登录 |

### 自动退出/登录逻辑

```
所有模式（除 CDP 手动外）：
  新任务开始 → 自动退出上一个账号 → 自动登录当前账号

临时邮箱：
  → 自动退出 → 自动注册/登录（脚本处理验证码）

自有账号：
  → 自动退出 → 自动登录（使用前端输入的账号密码，脚本处理验证码）

CDP 手动：
  → 用户手动登录 → 脚本只做验证
  → 但需要区分账号类型用于持久化（临时邮箱/自有账号）
```

### 账号来源类型

| 类型 | 说明 | 消耗邮箱 | 验证码/链接获取 |
|------|------|---------|----------------|
| **临时邮箱** | 从邮箱池选择 | 同一个邮箱 | 脚本自动获取（有 JWT） |
| **自有账号** | 手动输入邮箱+密码 | 额外选择邮箱池邮箱 | 脚本自动获取（从消耗邮箱） |

### 前端账号来源交互

```
┌─────────────────────────────────────────────────────────────┐
│  账号来源下拉                                                │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ ○ 选择邮箱池  →  [邮箱池下拉选择]                        ││
│  │   - 账号邮箱 = 消耗邮箱（同一个）                        ││
│  │   - 脚本自动获取验证码/链接                              ││
│  │                                                          ││
│  │ ○ 手动输入自有账号  →  [邮箱输入框] [密码输入框]         ││
│  │   - 账号邮箱 ≠ 消耗邮箱                                  ││
│  │   - 必须额外选择消耗邮箱 → [邮箱池下拉选择]              ││
│  │   - 脚本从消耗邮箱获取验证链接                           ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### CDP vs Camoufox 技术差异

| 维度 | CDP (Chrome) | Camoufox (Firefox) |
|------|-------------|-------------------|
| **连接方式** | `connect_over_cdp()` 连接已有浏览器 | `AsyncCamoufox()` 启动新浏览器 |
| **实例** | 复用用户已启动的 Chrome | 启动新的 Firefox 实例 | 这个如果新设备 gpt的页面可能不一样 或许每次都需要验证码？ 具体逻辑需要看 
| **指纹** | 用户 Chrome 固定指纹 | 每次启动新指纹 |
| **Profile** | 用户 Chrome Profile | 独立 Profile 目录 |
| **场景** | 调试、保底、手动介入 | 批量、反检测、无人值守 |

**核心验证逻辑相同**：
- `detect_page_state()` - 页面状态检测
- `fill_sheerid_form()` - 表单填写
- `submit_form()` - 表单提交
- `check_and_click_verification_link()` - 验证链接点击

### 模式选择指南

```
需求 → 推荐模式

调试/保底 → CDP 手动（用户手动登录，脚本验证）
单个临时邮箱 + CDP → CDP 全自动
单个临时邮箱 + 反检测 → Camoufox 无头全自动
单个自有账号 → Camoufox 无头自有
调试 + 反检测 → Camoufox 可视化
批量无人值守 → Camoufox 批量（自动创建邮箱）

任何模式出问题 → 回退到 CDP 手动
```

---

## 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **语言** | Python 3.10+ | |
| **浏览器自动化** | Camoufox | Firefox C++ 级修改，最强反检测 |
| **Web 框架** | Flask | API + Web 界面 |
| **前端** | Vue 3 (CDN) | 无需构建 |
| **数据库** | PostgreSQL | 账号和验证记录 |
| **邮箱服务** | Cloudflare Worker | 临时邮箱 API |
| **数据来源** | BIRLS 数据库 | 真实退伍军人公开信息 |

---

## 文档职责（强制）

| 文档 | 职责 | 更新时机 |
|------|------|---------|
| `CLAUDE.md` | 规则、技术栈、参考信息 | 规则变更时 |
| `TODO.md` | 动态任务（3个槽位）| 新需求自动补第一个 |
| `PLAN.md` | 整体方向、流程说明、更新日志 | 每次代码修改后 |
| `docs/page-selectors.md` | 页面选择器 | 探索页面后 |

### 时间戳格式（强制）

所有更新日志必须包含时间戳：
```
### 2025-12-25 20:27 UTC+8
```

### 上下文文档

开始新会话时，必须阅读以下文档获取上下文：
1. `CLAUDE.md` - 项目规则
2. `TODO.md` - 当前任务
3. `PLAN.md` - 开发计划和进度
4. `docs/page-selectors.md` - 页面选择器

---

## 开发测试流程（强制）

```
1. 阅读文档获取上下文

2. 启动开发环境:
   - python app.py（Flask 7870 端口）

3. 测试自动化脚本:
   - 前端选择模式，开始验证
   - 监控日志，发现问题
   - 完善脚本逻辑

4. 更新文档:
   - 新发现的页面结构 → docs/page-selectors.md
   - 完成的任务 → TODO.md
   - 整体进度 → PLAN.md
```

---

## Git 规范（强制）

### 当前状态（2026-01-02）

```
分支：
  * feature/cdp-auto  ← 当前开发分支
    dev               ← 未使用
    main              ← 最终稳定版

Tag（里程碑）：
  v0.1-cdp-manual    ← CDP 手动模式可用
  v0.2-cdp-auto      ← CDP 全自动模式可用
```

### 简化工作流程（单人开发）

```
⚠️ 核心原则：一个模式一个模式来，用 Tag 标记稳定点

当前策略：
  在 feature/cdp-auto 分支持续开发所有模式
  每个模式完成 → 打 Tag → 继续下一个
  全部完成 → 合并到 main

         v0.1          v0.2          v0.3
          ↓             ↓             ↓
────●─────●─────────────●─────────────●────→ feature/cdp-auto
    │                                 │
    └──────── 任何时候可回退 ─────────┘
```

### 日常操作

```bash
# 查看当前位置
git branch          # 确认在 feature/cdp-auto
git log --oneline -5

# 提交修改
git add .
git commit -m "修复: xxx"
git push origin feature/cdp-auto

# 模式完成后打 Tag
git tag v0.3-camoufox -m "Camoufox 模式可用"
git push origin --tags

# 出问题时回退到稳定版本
git stash                      # 保存当前未提交的修改
git checkout v0.2-cdp-auto     # 回到 CDP 全自动版本
git checkout feature/cdp-auto  # 回到开发分支
git stash pop                  # 恢复之前的修改
```

### Tag 里程碑

| Tag | 模式 | 状态 | 回退命令 |
|-----|------|------|---------|
| `v0.1-cdp-manual` | CDP 手动 | ✅ | `git checkout v0.1-cdp-manual` |
| `v0.2-cdp-auto` | CDP 全自动 | ✅ | `git checkout v0.2-cdp-auto` |
| `v0.3-camoufox` | Camoufox | 待开发 | - |

### 最终合并（全部完成后）

```bash
# 全部模式测试通过后，合并到 main
git checkout main
git merge feature/cdp-auto
git push origin main

# 删除开发分支（可选）
git branch -d feature/cdp-auto
git push origin --delete feature/cdp-auto
```

### 提交规范

```bash
# 提交信息必须中文
git commit -m "修复: 验证码提取逻辑"
git commit -m "新增: SheerID Status 字段"

# 不要添加 AI 署名
# ❌ Co-Authored-By: Claude ...
# ✅ 只写功能描述
```

### 提交类型前缀

| 前缀 | 说明 |
|------|------|
| `新增:` | 新功能 |
| `修复:` | Bug 修复 |
| `优化:` | 代码优化 |
| `文档:` | 文档更新 |
| `重构:` | 代码重构 |

---

## 数据规则（强制）

```
退伍日期限制：必须在过去 12 个月内！
- 例如今天是 2025-12-24，有效范围 = 2024-12-24 ~ 2025-12-24
- 超出范围显示 "Invalid discharge date"
- 代码自动计算：当前日期往前 1-11 个月随机

数据来源：
- 姓名/生日/军种：BIRLS 真实数据
- 退伍日期：动态随机生成（过去 1-11 个月）
- 邮箱：临时邮箱，接收两封邮件：
  1. ChatGPT 验证码（6位数字/字母）
  2. SheerID 验证链接（https://services.sheerid.com/verify/...）
```

---

## 反检测策略（强制）

```
浏览器层（Camoufox 优势）：
- Firefox C++ 级修改（非 JavaScript 注入）
- 0% headless 检测率（vs Patchright 67%）
- 完整指纹伪造（navigator、screen、WebGL、canvas、audio 等）
- 内置人类光标移动算法
- GeoIP 自动指纹匹配
- 每次启动新指纹

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

---

## 成功标识（重要）

**只有看到这个才算成功**：
```
标题: "You've been verified"
按钮: "Continue" → 点击后跳转 chatgpt.com
```

其他任何情况都是**消耗**，需要换下一条军人数据继续尝试。

---

## 账号持久化规则

### 账号类型区分

| 类型 | 说明 | 密码来源 | 消耗邮箱 |
|------|------|---------|---------|
| **临时邮箱** | 从邮箱池选择 | 我们生成 | 同一个邮箱 |
| **自有账号** | 用户手动输入 | 用户提供 | 额外选择邮箱池邮箱 |

### 数据结构（完整版）

```python
{
    # === ChatGPT 账号（核心）===
    "email": "xxx@xxx.com",              # 登录邮箱
    "password": "xxx",                   # 登录密码
    "is_own_account": False,             # 是否自有账号

    # === 消耗邮箱（接收 SheerID 验证链接）===
    # 临时邮箱：consuming_email = None（自己就是消耗邮箱）
    # 自有账号：consuming_email = 额外选择的邮箱池邮箱
    "consuming_email": None,             # 消耗邮箱地址
    "consuming_email_jwt": None,         # 消耗邮箱的 JWT

    # === 临时邮箱专用（自有账号时为 None）===
    "email_jwt": "eyJ...",               # 邮箱 JWT（API 返回）
    "email_login_url": "https://one.009025.xyz/",

    # === 状态追踪 ===
    "status": "pending|registering|verifying|success|failed",
    "error_type": "",
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

### 消耗邮箱获取逻辑

```python
def get_consuming_email(account_data):
    """获取用于接收验证链接的邮箱"""
    if account_data.get("is_own_account"):
        # 自有账号：使用额外选择的消耗邮箱
        return account_data["consuming_email"], account_data["consuming_email_jwt"]
    else:
        # 临时邮箱：自己就是消耗邮箱
        return account_data["email"], account_data["email_jwt"]
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

## 参考项目（可复用代码）

> ⚠️ 本项目与以下两个项目逻辑相似，只是目标页面不同。**遇到问题时必须优先参考这些项目的实现**。

### 何时查看参考项目

| 遇到问题 | 查看项目 | 具体文件 |
|---------|---------|---------|
| 邮箱创建失败 | test_band | `email_manager.py` - API 调用逻辑 |
| 验证码提取失败 | test_band | `email_manager.py` - 正则匹配模式 |
| 前端显示异常 | test_band | `templates/index.html` - Vue 组件 |
| 账号状态不同步 | test_band | `account_manager.py` - 状态持久化 |
| SheerID 表单填写失败 | K-12 | `one/sheerid_verifier.py` - API 方式 |
| 选择器失效 | K-12 | `notes/` - 页面结构分析 |
| 提交按钮 disabled | K-12 | 检查必填字段逻辑 |

### 快速定位问题

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

## 待研究数据源

> 用户提出的备选数据源，待验证是否符合 SheerID 表单要求

| 数据源 | URL | 说明 |
|-------|-----|------|
| VA 墓地定位 | https://gravelocator.cem.va.gov/ | 墓地位置，可能有军人信息 |
| 虚拟墙 | https://www.vlm.cem.va.gov/ | 阵亡军人纪念 |
| VA 开放数据 | https://www.data.va.gov/ | VA 公开数据集 |
| 遗体捐献名单 | 待查 | 美国军人遗体捐献 |
| 法院案件 | 待查 | 公开审理案件中的军人信息 |
| BIRLS 在线 | https://www.birls.org/ | 19.5M+ 已故退伍军人数据库 |

**SheerID 表单需要的字段**：
- First name / Last name
- Birth date（月/日/年）
- Branch of service（军种）
- Discharge date（退伍日期，**必须在过去 12 个月内！**）

---

## 环境变量管理

### 配置文件分离

```
.env.example    # 模板文件，提交到 Git，包含所有参数说明
.env.local      # 用户配置，不提交到 Git（已加入 .gitignore）
用户使用scripts/sync_env.py
```

### 加载顺序

```python
# config.py 中的加载逻辑
load_dotenv('.env.example')        # 1. 先加载默认值
load_dotenv('.env.local', override=True)  # 2. 再加载用户配置，覆盖默认值
```

### 新增参数时的规则

1. **在 .env.example 中添加**：包含参数说明和默认值
2. **在 PLAN.md 中记录**：更新日志中标明新增了什么参数
3. **用户只需在 .env.local 中添加**：不会影响已有配置

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

## 项目结构

```
veterans-verify/
├── app.py                  # Flask 主应用（API + Web 界面）
├── run_verify.py           # CDP 模式验证脚本
├── automation/
│   └── camoufox_verify.py  # Camoufox 模式验证
├── email_manager.py        # 邮箱验证码/链接处理
├── email_pool.py           # 邮箱池管理
├── proxy_manager.py        # 代理池管理
├── profile_manager.py      # Profile 持久化
├── database.py             # PostgreSQL 数据库
├── veteran_data.py         # 退伍军人数据管理（BIRLS）
├── config.py               # 完整配置管理
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量示例
├── data/
│   ├── birls_update.csv    # BIRLS 原始数据（199MB）
│   ├── veterans_processed.json  # 处理后的有效数据
│   ├── email_pool.json     # 邮箱池
│   └── proxies.txt         # 代理列表
├── profiles/               # Camoufox Profile 目录
├── screenshots/            # 调试截图
├── templates/
│   ├── login.html          # 登录页面
│   └── index.html          # 管理界面
├── docs/
│   ├── page-selectors.md   # 页面选择器
│   └── proxy-pool-guide.md # 代理池指南
├── scripts/
│   ├── start-chrome-devtools.bat  # Chrome 调试启动
│   └── sync_env.py         # 环境变量同步工具
├── CLAUDE.md               # 本文件（规则）
├── TODO.md                 # 动态任务
└── PLAN.md                 # 开发计划
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
| POST | `/api/verify/start` | 启动验证任务 |
| GET | `/api/verify/status/<email>` | 查询任务状态 |
| POST | `/api/email-pool/create` | 批量创建邮箱 |
| GET | `/api/email-pool` | 获取邮箱池 |

---

## 代码风格

- 4 空格缩进（Python 标准）
- 使用 Type Hints
- 日志使用 logging 模块
- 异步操作使用 asyncio

---

## 🏗️ 模块化架构（核心设计原则）

### 设计哲学：容错 + 可组合

```
核心原则：一个模式出问题，还能用其他模式继续！

模式之间是 **可组合的模块**，不是独立的完整流程：

┌─────────────────────────────────────────────────────────────┐
│ 邮箱池管理（独立操作）                                        │
│   → 手动/批量创建邮箱，不依赖任何自动化                       │
└─────────────────────────────────────────────────────────────┘
                            ↓ 提供邮箱
┌─────────────────────────────────────────────────────────────┐
│ CDP 手动模式                                                  │
│   → [用户手动登录] + [验证核心] ← 已验证可用 ✅              │
└─────────────────────────────────────────────────────────────┘
                            ↑ 复用
┌─────────────────────────────────────────────────────────────┐
│ CDP 全自动模式（单个）                                        │
│   → [自动退出/登录] + [验证核心]                              │
└─────────────────────────────────────────────────────────────┘
                            ↑ 复用
┌─────────────────────────────────────────────────────────────┐
│ Camoufox 模式（单个）                                         │
│   → [启动浏览器] + [自动登录] + [验证核心]                   │
└─────────────────────────────────────────────────────────────┘
                            ↑ 循环调用
┌─────────────────────────────────────────────────────────────┐
│ 🔄 批量全自动模式                                             │
│   → [批量创建邮箱] + [循环: 全自动验证] + [成功后下一个]     │
│   → 失败换数据重试，成功退出登录继续下一个邮箱               │
└─────────────────────────────────────────────────────────────┘
```

### 核心模块（可复用）

| 模块 | 函数 | 文件 | 状态 |
|------|------|------|------|
| 页面状态检测 | `detect_page_state()` | run_verify.py:264 | ✅ |
| 表单填写 | `fill_sheerid_form()` | run_verify.py:385 | ✅ |
| 表单提交 | `submit_form()` | run_verify.py:491 | ✅ |
| 重试按钮 | `click_try_again()` | run_verify.py:511 | ✅ |
| 验证链接点击 | `check_and_click_verification_link()` | run_verify.py:107 | ✅ |

⚠️ **注意**: `camoufox_verify.py` 中有同名函数，这是历史遗留的**重复实现**。
未来重构时应统一到一个共享模块。

### 模式切换指南（容错）

```
如果 CDP 全自动出问题：
  1. 停止任务
  2. 用户手动在 Chrome 中登录
  3. 切换到 "CDP 手动" 模式
  4. 脚本继续验证流程

如果 CDP 手动也出问题：
  1. 停止任务
  2. 切换到 Camoufox 可视化模式
  3. Camoufox 启动新指纹，重试全流程

如果 Camoufox 也出问题：
  1. 检查代理是否正常
  2. 检查 IP 是否被风控
  3. 使用邮箱池管理功能手动创建新邮箱
  4. 用新邮箱重试
```

### 禁止重复造轮子（强制）

修改自动化逻辑前**必须**：

1. **先搜索现有实现**：`Grep` 搜索函数名
2. **确认是否已存在**：看 run_verify.py 和 camoufox_verify.py
3. **优先复用**：修改现有函数而非创建新函数
4. **如需新函数**：放在共享位置，两个模式都能调用

---

## 🔮 后续扩展方向

### 方向 1：链接模式

**场景**：直接访问 SheerID 验证链接，无头循环验证

**适用于**：
- 用户已有 SheerID 链接（从 chatgpt.com/veterans-claim 获取）
- 链接可能可以复用（验证失败后刷新继续）
- 无需登录 ChatGPT

**实现思路**：
```
link_verify.py
  → 输入: SheerID 链接
  → goto(link)
  → 复用 fill_sheerid_form()
  → 复用 submit_form()
  → 失败换数据重试
```

**待测试问题**：
- 验证失败后，是刷新链接还是同一个链接？
- 如果是同一个链接，可以直接无头循环直到通过
- 链接有效期多久？

### 方向 2：Telegram 机器人

**场景**：用户通过 Telegram 提交验证请求

**三种模式**：
| 模式 | 输入 | 流程 |
|------|------|------|
| 链接模式 | SheerID 链接 | 直接验证 |
| 自有账号 | 邮箱+密码 | 登录后验证 |
| 全自动 | 无 | 创建临时邮箱，完整流程 |

**待参考项目**：用户可能有类似的 Telegram 机器人项目

### 方向 3：网页链接自动化

**场景**：用户在网页输入链接，后台自动验证

**实现**：复用链接模式 + Web 界面

### 扩展时的复用原则

```
新模式 = 复用现有模块 + 新增必要的连接逻辑

✅ 正确：
  链接模式 = goto(link) + fill_sheerid_form() + submit_form()

❌ 错误：
  链接模式 = 从头写一套新的表单填写逻辑
```
