# Veterans Verify - 开发计划

> 此文件作为开发上下文，每次完善逻辑或更新方向时请更新

**最后更新**: 2025-12-24

---

## 项目目标

自动化完成 ChatGPT Veterans 验证，获取 1 年免费 ChatGPT Plus。

---

## 当前状态：Phase 2 进行中

### ✅ 已完成

| 模块 | 状态 | 说明 |
|------|------|------|
| 数据来源 | ✅ | BIRLS 数据库，19,605 条有效记录 |
| veteran_data.py | ✅ | 数据管理模块，支持随机获取、去重、军种映射 |
| browser_worker.py | ✅ | Camoufox 自动化，支持完整验证流程 |
| email_manager.py | ✅ | 支持验证码 + 验证链接提取 |
| config.py | ✅ | 完整配置管理 |
| .env.example | ✅ | 中文注释配置模板 |
| account_manager.py | ✅ | **批量账号管理**（参考 test_band） |
| app.py | ✅ | **Flask API 重构**，支持批量创建 |

### 🔄 进行中

- [ ] 配置 .env 测试完整流程
- [ ] 收集各种错误类型
- [ ] 优化 CSS 选择器

---

## 核心流程

```
┌─────────────────────────────────────────────────────────────┐
│                    Veterans Verify 流程                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 创建临时邮箱 ──────────────────────────────────────────► │
│                                                              │
│  2. 打开 chatgpt.com/veterans-claim ──────────────────────► │
│                                                              │
│  3. 点击"登录" ─► 输入邮箱 ─► 创建密码 ─────────────────────► │
│                                                              │
│  4. 等待 ChatGPT 验证码邮件 ─► 输入验证码 ──────────────────► │
│                                                              │
│  5. 登录成功 ─► 自动跳转 SheerID 验证页面 ──────────────────► │
│                                                              │
│  6. 填写表单（BIRLS 真实数据 + 随机退伍日期）────────────────► │
│     - Branch of service                                      │
│     - First name / Last name                                 │
│     - Date of birth                                          │
│     - Discharge date（过去 1-11 个月）                        │
│     - Email                                                  │
│                                                              │
│  7. 点击 "Verify My Eligibility" ───────────────────────────► │
│                                                              │
│  8. 等待 SheerID 验证邮件（链接）─► 点击链接 ────────────────► │
│                                                              │
│  9. 检查结果：                                                │
│     ├─ 成功 ─► 跳转 chatgpt.com，获得 1 年 Plus              │
│     ├─ 已验证 ─► 换下一条数据重试                            │
│     ├─ 无法验证 ─► 记录错误，换数据重试                       │
│     └─ 其他错误 ─► 止损冷却                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 数据来源

### BIRLS 数据库

- **来源**: [Internet Archive](https://archive.org/details/BIRLS_database)
- **文件**: `data/birls_update.csv` (199MB)
- **处理后**: `data/veterans_processed.json` (19,605 条)

### 数据字段

| 字段 | 来源 | 说明 |
|------|------|------|
| first_name | BIRLS | 真实姓 |
| last_name | BIRLS | 真实名 |
| birth_date | BIRLS | 真实生日（1980-2005年） |
| branch | BIRLS | 真实军种 |
| discharge_date | **随机生成** | 过去 1-11 个月 |
| email | **临时邮箱** | Cloudflare Worker |

### 军种分布

```
Army:         10,247 (52.3%)
Marine Corps:  3,759 (19.2%)
Navy:          3,098 (15.8%)
Air Force:     2,326 (11.9%)
Coast Guard:     175 (0.9%)
```

---

## 技术架构

### 参考项目

| 项目 | 复用内容 |
|------|----------|
| `e:\test_band_gemini_mail` | 邮箱服务、Profile 管理、Flask 架构、止损机制 |
| `e:\K-12项目` | SheerID 表单自动化、反检测策略、错误处理 |

### 技术栈

- **浏览器**: Camoufox (Firefox C++ 级反检测)
- **后端**: Flask + asyncio
- **前端**: Vue 3 (CDN)
- **邮箱**: Cloudflare Worker 临时邮箱
- **数据**: BIRLS CSV → JSON

### 反检测策略

```
Camoufox 优势：
├── Firefox C++ 级修改（非 JS 注入）
├── 0% headless 检测率
├── 完整指纹伪造
├── 内置人类光标移动
└── GeoIP 自动指纹匹配

人类行为模拟：
├── 打字延迟：50-150ms/字符
├── 字段切换：0.3-0.8s
├── 任务间隔：30-120s
└── 正态分布随机

止损机制：
├── 单次失败 → 冷却 15 分钟
├── 连续 3 次失败 → 暂停 3-8 分钟
├── Captcha 触发 → 暂停 10 分钟
└── 自动恢复，继续队列
```

---

## 错误类型（待收集）

```python
ERROR_TYPES = {
    # 浏览器相关
    "BROWSER_INIT_ERROR": "浏览器初始化失败",

    # 邮箱相关
    "EMAIL_CREATE_ERROR": "创建邮箱失败",
    "CHATGPT_CODE_TIMEOUT": "ChatGPT 验证码超时",
    "VERIFY_LINK_TIMEOUT": "SheerID 验证链接超时",

    # ChatGPT 注册
    "CHATGPT_REGISTER_ERROR": "ChatGPT 注册失败",

    # SheerID 表单
    "FORM_FILL_ERROR": "表单填写失败",
    "SUBMIT_DISABLED": "提交按钮被禁用",
    "SUBMIT_ERROR": "提交失败",

    # 验证结果
    "ALREADY_VERIFIED": "该信息已被验证过",
    "INVALID_INFO": "信息无法验证",
    "NEED_LOGIN": "需要登录",
    "RATE_LIMITED": "请求频率限制",

    # 其他
    "UNEXPECTED_ERROR": "未知错误",
}
```

---

## 开发计划

### Phase 1: 基础框架 ✅

- [x] 配置 BIRLS 数据来源
- [x] 实现 veteran_data.py 数据管理
- [x] 更新 browser_worker.py 完整流程
- [x] 更新 email_manager.py 支持链接提取
- [x] 配置 .env.example 中文注释
- [x] 创建 PLAN.md 开发上下文

### Phase 2: 测试调优（当前）

- [x] 配置 .env 连接临时邮箱
- [x] 手动测试单次流程（Chrome MCP 探索）
- [x] 收集 SheerID 表单真实选择器 → `docs/page-selectors.md`
- [ ] 收集各种错误页面
- [ ] 优化错误处理逻辑
- [ ] 修复验证码提取 bug（Subject 解析）

### Phase 3: 批量运行

- [ ] 实现任务队列批量处理
- [ ] 添加成功/失败统计
- [ ] 优化止损策略
- [ ] 添加 Web 界面监控

### Phase 4: 优化增强

- [ ] Profile 多代理轮换
- [ ] 成功率统计分析
- [ ] 自动重试失败任务
- [ ] 导出成功账号列表

---

## 下一步行动

1. **配置 .env** - 填入临时邮箱服务配置
2. **运行测试** - `python browser_worker.py` 测试单次流程
3. **收集选择器** - 根据真实页面更新 CSS 选择器
4. **完善错误处理** - 收集并分类各种错误

---

## 注意事项

⚠️ **退伍日期必须在过去 12 个月内**
- 代码自动生成：当前日期往前 1-11 个月随机
- 超出范围会显示 "Invalid discharge date"

⚠️ **SheerID 需要先登录 ChatGPT**
- 不能直接访问 SheerID 页面
- 必须从 chatgpt.com/veterans-claim 入口进入

⚠️ **两封邮件**
1. ChatGPT 验证码（6位）
2. SheerID 验证链接（点击完成验证）

---

## 更新日志

### 2025-12-25 21:00 UTC+8

**持久化逻辑深度完善**

明确区分两种凭证：

| 凭证类型 | 用途 | 来源 |
|---------|------|------|
| **ChatGPT 账号** | 登录 ChatGPT | 我们生成密码 |
| **临时邮箱 JWT** | API 查询邮件 | API 返回 |

**临时邮箱登录说明**：
- API 创建邮箱返回 `jwt` + `address`，没有传统密码
- 前端 https://one.009025.xyz/ 输入邮箱地址即可登录
- JWT 用于后端 API 查询邮件

**给用户的输出格式**：
```
ChatGPT 登录：邮箱 + 密码
查看邮件：https://one.009025.xyz/ + 邮箱地址
```

---

### 2025-12-25 20:48 UTC+8

**CLAUDE.md 规则完善**

根据用户需求，添加以下固化规则：

1. **项目固定信息**
   - GitHub 仓库：https://github.com/khuseynsheripov-art/veterans-verify.git
   - 临时邮箱前端：https://one.009025.xyz/
   - 本地服务端口：7870

2. **账号持久化规则**
   - 必须保存：email, chatgpt_password, email_jwt, status, veteran_data
   - 状态追踪：pending → registering → verifying → success/failed
   - 用户可通过前端登录查看邮件

3. **参考项目说明完善**
   - `E:\test_band_gemini_mail` - 邮箱+批量注册逻辑
   - `E:\K-12项目` - SheerID 表单自动化

---

### 2025-12-25 20:27 UTC+8

**代码完善（深度思考分析）**

基于 `page-selectors.md` 和 `会话记录总阶.md` 的分析，完成以下修复：

1. **email_manager.py - 验证码提取修复**
   - 新增 Subject 验证码提取（优先级最高）
   - 支持中文格式：`代码为 XXXXXX`
   - 支持英文格式：`code is XXXXXX`

2. **browser_worker.py - 确认年龄页面处理**
   - 新增 `handle_about_you_page()` 方法
   - 新增 `VerifyStatus.CONFIRMING_AGE` 状态
   - 随机生成姓名（20-25岁）
   - 填写 `input[name="name"]` 和生日 spinbutton

3. **browser_worker.py - SheerID 表单完善**
   - 新增 **Status 字段**（"Military Veteran or Retiree"）
   - 更新选择器对齐 `page-selectors.md`
   - 修复 Day/Year 输入框使用索引区分（第1个=DOB，第2个=Discharge）

4. **HumanBehavior 类增强**
   - 新增 `generate_random_birthday(min_age=20, max_age=25)`
   - 新增 `generate_random_name()` 生成随机英文名

---

### 2025-12-25

**页面选择器探索（Chrome MCP）**
- 使用 Chrome DevTools MCP 实际探索完整流程
- 成功注册测试账号：`hkcy23djl@009025.xyz`
- **发现新页面**：确认年龄页面 (`auth.openai.com/about-you`)
- **完整记录 SheerID 表单**：
  - URL: `https://services.sheerid.com/verify/...`
  - Status 下拉选项：Active Duty / Military Veteran or Retiree / Reservist or National Guard
  - Branch of service：Air Force / Army / Coast Guard / Marine Corps / Navy / Space Force
  - 所有表单字段选择器
- 更新文档：`docs/page-selectors.md`
- 创建启动脚本：`scripts/start-chrome-devtools.bat`

**修复验证码提取**
- 发现邮箱管理器提取验证码的 bug（误识别邮箱域名）
- 验证码在邮件 Subject 中：`你的 ChatGPT 代码为 XXXXXX`

---

### 2025-12-24

**初始化**
- 初始化项目框架
- 下载 BIRLS 数据库，筛选 19,605 条有效记录
- 实现完整验证流程（ChatGPT 注册 → SheerID 表单 → 邮件链接）
- 创建 .env.example 中文注释版本
- 创建 PLAN.md 开发计划

**批量系统（参考 test_band_gemini_mail）**
- 新增 account_manager.py：批量账号管理、任务队列、止损机制
- 重构 app.py：Flask API 支持批量创建/查询/重试
- 新增 API 接口：
  - POST /api/accounts - 创建账号（支持批量）
  - GET /api/accounts - 获取账号列表
  - POST /api/accounts/<email>/retry - 重试失败账号
  - GET /api/accounts/export - 导出成功账号
  - GET /api/status - 系统状态
