# Veterans Verify - Claude Code 规则

> ⚠️ **重要**: 每次完善逻辑或更新方向时，请同步更新 `PLAN.md`

---

## 🔗 项目固定信息

| 项目 | 值 |
|------|-----|
| **GitHub 仓库** | https://github.com/khuseynsheripov-art/veterans-verify.git |
| **临时邮箱前端** | https://one.009025.xyz/ |
| **本地服务端口** | 7870 |

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
| `docs/page-selectors.md` | 页面变化时 | CSS 选择器、页面结构 |

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

## 验证流程（2025-12-24 更新）

```
1. 创建临时邮箱
2. 打开 chatgpt.com/veterans-claim
3. 点击"登录" → 注册/登录 ChatGPT
   - 输入邮箱 → 创建密码（新用户）
   - 接收 ChatGPT 邮箱验证码 → 输入验证码
4. 登录后自动进入 SheerID 验证表单
5. 填写表单（Branch、姓名、生日、退伍日期、邮箱）
6. 点击 "Verify My Eligibility"
7. **收 SheerID 验证邮件**（来自 verify@sheerid.com，包含链接！）
8. 点击链接完成验证
9. 成功 → 跳转 chatgpt.com（账号获得1年Plus）
```

**关键发现：**
- SheerID 页面需要先登录 ChatGPT 才能访问
- 会收到两封邮件：ChatGPT 验证码 + SheerID 验证链接

## 数据来源：BIRLS 数据库

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
| Branch of service | 下拉 | Air Force / Army / Coast Guard / Marine Corps / Navy / Space Force | select_dropdown |
| First name | 文本 | | human_type |
| Last name | 文本 | | human_type |
| Date of birth | 日期 | Month(下拉) + Day + Year | 月: select_dropdown, 日/年: human_type |
| Discharge date | 日期 | Month(下拉) + Day + Year | ⚠️ **必须在过去12个月内！** |
| Email address | 文本 | 接收验证链接 | human_type |

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

### 3. 错误类型枚举
```python
# 需要收集和处理的错误类型
ERROR_TYPES = {
    "BROWSER_INIT_ERROR": "浏览器初始化失败",
    "EMAIL_CREATE_ERROR": "创建邮箱失败",
    "CHATGPT_CODE_TIMEOUT": "ChatGPT 验证码超时",
    "CHATGPT_REGISTER_ERROR": "ChatGPT 注册失败",
    "FORM_FILL_ERROR": "表单填写失败",
    "SUBMIT_DISABLED": "提交按钮被禁用",
    "SUBMIT_ERROR": "提交失败",
    "VERIFY_LINK_TIMEOUT": "SheerID 验证链接超时",
    "ALREADY_VERIFIED": "该信息已被验证过",
    "INVALID_INFO": "信息无法验证",
    "NEED_LOGIN": "需要登录",
    "RATE_LIMITED": "请求频率限制",
    "UNEXPECTED_ERROR": "未知错误",
}
```

---

## 参考项目（可复用代码）

> ⚠️ 本项目与以下两个项目逻辑相似，只是目标页面不同。遇到问题时优先参考这些项目的实现。

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

**遇到问题参考**:
- 邮箱创建失败 → `email_manager.py` 的 API 调用
- 前端不工作 → `templates/index.html` 的 Vue 组件
- 账号持久化 → `account_manager.py` 的 JSON 存储

### K-12项目（SheerID 验证）

**路径**: `E:\K-12项目`

**项目说明**: K-12 教育优惠验证，使用 SheerID 表单（与本项目表单结构相似）

**复用内容**:
| 模块 | 文件 | 说明 |
|------|------|------|
| SheerID 表单 | 自动化逻辑 | 下拉选择、日期填写 |
| 选择器 | `notes/` | CSS 选择器记录 |
| 反检测 | 人类行为模拟 | 延迟、打字速度 |

**遇到问题参考**:
- SheerID 表单变化 → 检查 `notes/sheerid-page-analysis.md`
- 选择器失效 → 使用 Chrome MCP 重新探索
- 提交按钮 disabled → 检查必填字段是否都填写

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
