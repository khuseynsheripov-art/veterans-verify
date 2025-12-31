# Veterans Verify - 页面选择器文档

> 使用 Chrome DevTools MCP 探索记录，2025-12-25

## 启动调试浏览器

```bash
# 运行脚本
E:\veterans-verify\scripts\start-chrome-devtools.bat

# 或手动启动
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\.cache\veterans-chrome-mcp\user-data" --no-first-run
```

---

## 流程概览

```
1. Veterans 优惠页面 → 点击"登录"
2. 登录/注册页面 → 输入邮箱 → 点击"继续"
3. 创建密码页面 → 输入密码 → 点击"继续"
4. 邮箱验证页面 → 输入验证码 → 点击"继续"
5. 确认年龄页面 → 输入姓名+生日 → 点击"继续"
6. Veterans 页面(已登录) → 点击"验证资格条件"
7. SheerID 验证表单 → 填写军人信息 → 提交
8. SheerID 邮箱验证 → 点击验证链接
9. 验证成功 → 获得1年Plus
```

---

## 页面1: Veterans 优惠页面

**URL**: `https://chatgpt.com/veterans-claim`

| 元素 | CSS 选择器建议 | 说明 |
|------|---------------|------|
| 登录按钮 | `button:has-text("登录")` | 主要CTA按钮 |
| 了解更多 | `button:has-text("了解更多")` | 次要按钮 |

**页面标识**:
- 标题包含 "One year of ChatGPT Plus free"
- URL 包含 `/veterans-claim`

---

## 页面1.5: chatgpt.com 主页登录弹窗（⚠️ 2025-12-31 新发现！）

**URL**: `https://chatgpt.com/`（未登录状态）

**重要发现**：点击主页"登录"按钮后，出现的是一个**弹窗对话框**（`dialog` 元素），不是跳转页面！

### 主页元素（点击前）

| 元素 | 选择器 | 说明 |
|------|--------|------|
| 登录按钮 | `button "登录"` | 点击打开弹窗 |
| 注册按钮 | `button "免费注册"` | |
| ⚠️ 个人资料菜单 | `button "打开"个人资料"菜单"` | **陷阱！未登录也存在！** |

### 弹窗元素（dialog 内部）

| 元素 | 选择器 | 说明 |
|------|--------|------|
| 弹窗容器 | `dialog` | 弹窗根元素 |
| 标题 | `heading "登录或注册"` | |
| 邮箱输入框 | `textbox "电子邮件地址"` | ✅ 正确目标 |
| 继续按钮 | `button "继续"` | 提交邮箱 |
| Google 登录 | `button "继续使用 Google 登录"` | ⚠️ 别误点！ |
| Apple 登录 | `button "继续使用 Apple 登录"` | |
| Microsoft 登录 | `button "继续使用 Microsoft 登录"` | |
| 手机登录 | `button "继续使用手机登录"` | |
| 关闭按钮 | `button "关闭"` | 在 banner 内 |

### ⚠️ 常见错误

1. **误判已登录**：`button "打开"个人资料"菜单"` 在未登录状态也存在！
   - 不能用这个按钮判断是否已登录
   - 应该检查是否有 `button "登录"` 按钮

2. **输入位置错误**：弹窗内有多个按钮
   - 正确目标：`textbox "电子邮件地址"`
   - 错误目标：`button "继续使用 Google 登录"`（可能被误点）

3. **选择器不匹配**：CSS 选择器 `input[name="email"]` 可能找不到弹窗中的 textbox
   - 推荐用 Playwright 的 `get_by_role("textbox", name="电子邮件地址")`

### 代码示例

```python
# 1. 在 chatgpt.com 主页点击登录按钮
login_btn = page.get_by_role("button", name="登录")
await login_btn.click()
await asyncio.sleep(1)

# 2. 等待弹窗出现
dialog = page.locator("dialog")
await dialog.wait_for(state="visible", timeout=5000)

# 3. 在弹窗内输入邮箱（关键！）
email_input = dialog.get_by_role("textbox", name="电子邮件地址")
await email_input.fill("xxx@009025.xyz")

# 4. 点击继续
continue_btn = dialog.get_by_role("button", name="继续")
await continue_btn.click()
```

---

## 页面2: 登录或注册（auth.openai.com 页面版）

**URL**: `https://auth.openai.com/log-in-or-create-account`

> 注意：这是从 veterans-claim 页面进入时的登录页面。从 chatgpt.com 主页登录会先显示弹窗。

| 元素 | CSS 选择器建议 | Playwright 选择器 |
|------|---------------|------------------|
| 邮箱输入框 | `input[name="email"]` | `textbox "电子邮件地址"` |
| 继续按钮 | `button[type="submit"]` | `button "继续"` |
| Google 登录 | - | `button:has-text("Google")` |
| Apple 登录 | - | `button:has-text("Apple")` |
| Microsoft 登录 | - | `button:has-text("Microsoft")` |
| 手机登录 | - | `button:has-text("手机")` |

**页面标识**:
- URL 包含 `log-in-or-create-account`
- 标题 "登录或注册"

---

## 页面3: 创建密码 (新用户)

**URL**: `https://auth.openai.com/create-account/password`

| 元素 | CSS 选择器建议 | Playwright 选择器 |
|------|---------------|------------------|
| 邮箱显示 | `input[readonly]` | `textbox "电子邮件地址"` (readonly) |
| 编辑邮箱 | `a:has-text("编辑")` | `link "编辑电子邮件"` |
| 密码输入框 | `input[type="password"]` | `textbox "密码"` |
| 显示密码 | - | `button "显示密码"` |
| 继续按钮 | `button[type="submit"]` | `button "继续"` |

**密码要求**: 至少12个字符

**页面标识**:
- URL 包含 `create-account/password`
- 标题 "创建密码"

---

## 页面4: 邮箱验证码

**URL**: `https://auth.openai.com/email-verification`

| 元素 | CSS 选择器建议 | Playwright 选择器 |
|------|---------------|------------------|
| 验证码输入框 | `input[name="code"]` | `textbox "代码"` |
| 继续按钮 | `button[type="submit"]` | `button "继续"` |
| 重发邮件 | - | `button "重新发送电子邮件"` |

**验证码格式**: 6位数字/字母混合

**邮件发送者**: OpenAI / ChatGPT

**页面标识**:
- URL 包含 `email-verification`
- 标题 "检查您的收件箱"

---

## 页面5: 确认年龄 (新页面!)

**URL**: `https://auth.openai.com/about-you`

| 元素 | CSS 选择器建议 | Playwright 选择器 |
|------|---------------|------------------|
| 全名输入框 | `input[name="name"]` | `textbox "全名"` |
| 年份 | `input[type="number"]` | `spinbutton "年, 生日日期"` |
| 月份 | `input[type="number"]` | `spinbutton "月, 生日日期"` |
| 日期 | `input[type="number"]` | `spinbutton "日, 生日日期"` |
| 继续按钮 | `button[type="submit"]` | `button "继续"` |

**页面标识**:
- URL 包含 `about-you`
- 标题 "确认一下你的年龄"

---

## 页面6: Veterans 页面 (已登录状态)

**URL**: `https://chatgpt.com/veterans-claim?redirectedFromAuth=true`

| 元素 | CSS 选择器建议 | Playwright 选择器 |
|------|---------------|------------------|
| 验证按钮 | `button:has-text("验证")` | `button "验证资格条件"` |

**页面标识**:
- 按钮文字从"登录"变为"验证资格条件"

---

## 页面7: SheerID 验证表单 (核心!)

**URL**: `https://services.sheerid.com/verify/690415d58971e73ca187d8c9/?verificationId=...`

**页面标题**: "Unlock this Military-Only Offer"

### ⚠️ 2025-12-27 重要更新

**Status 字段动态显示！** 有些账号有 Status 字段，有些没有，需要动态检测：

```python
# 检测 Status 字段是否存在
status_field = await page.query_selector('#sid-military-status')
if status_field:
    # 有 Status 字段，先选择 "Military Veteran or Retiree"
    await select_dropdown('#sid-military-status', 'Military Veteran')
# 然后继续填写其他字段
```

**可能的 Status 选项**:
- Active Duty
- Military Veteran or Retiree（选这个）
- Reservist or National Guard

### 入口方式

**重要发现**: 不需要登录 ChatGPT 即可访问 SheerID 表单！
1. 访问 `https://chatgpt.com/veterans-claim`
2. 点击 "Verify eligibility" 按钮
3. 直接跳转到 SheerID 表单

### Branch of service 字段 (军种)

| 选项值 | BIRLS 数据对应 | 说明 |
|--------|---------------|------|
| Air Force | Air Force | |
| Air Force Reserve | - | 预备役 |
| Air National Guard | - | 国民警卫队 |
| Army | Army | |
| Army National Guard | - | 国民警卫队 |
| Army Reserve | - | 预备役 |
| Coast Guard | Coast Guard | |
| Coast Guard Reserve | - | 预备役 |
| Marine Corps | Marine Corps | |
| Marine Corps Forces Reserve | - | 预备役 |
| Navy | Navy | |
| Navy Reserve | - | 预备役 |
| Space Force | Space Force | |

**选择器**: `get_by_role("combobox", name="Branch of service")`

### 完整表单字段（2025-12-27 更新）

| 字段 | 类型 | CSS 选择器 | 说明 |
|------|------|------------------|------|
| **Status** | 下拉 | `#sid-military-status` | ⚠️ **动态字段**，有些页面有有些没有 |
| Branch of service | 下拉 | `#sid-branch-of-service` | 军种 |
| First name | 文本 | `get_by_role("textbox", name="First name")` | 名 |
| Last name | 文本 | `get_by_role("textbox", name="Last name")` | 姓 |
| Date of birth - Month | 下拉 | `get_by_role("combobox", name="Date of birth")` | 出生月 |
| Date of birth - Day | 文本 | `get_by_role("textbox", name="Day").nth(0)` | 出生日 |
| Date of birth - Year | 文本 | `get_by_role("textbox", name="Year").nth(0)` | 出生年 |
| Discharge date - Month | 下拉 | `get_by_role("combobox", name="Discharge date")` | 退伍月 |
| Discharge date - Day | 文本 | `get_by_role("textbox", name="Day").nth(1)` | 退伍日 |
| Discharge date - Year | 文本 | `get_by_role("textbox", name="Year").nth(1)` | 退伍年 |
| Email address | 文本 | `get_by_role("textbox", name="Email address")` | 邮箱 |
| 提交按钮 | 按钮 | `get_by_role("button", name="Verify My Eligibility")` | 填完后启用 |

### 下拉框选择方式

```python
# 1. 点击 combobox 打开列表
combobox = page.get_by_role("combobox", name="Branch of service")
await combobox.click()
await asyncio.sleep(0.3)

# 2. 选择选项
option = page.get_by_role("option", name="Army", exact=True)
await option.click()
```

### 关键约束

- **Status 字段动态显示** - 有些页面有，有些没有，需要动态检测后选择 "Military Veteran"
- **Discharge date 必须在过去12个月内!**
- 提交按钮在所有必填字段填写后才启用
- 邮箱必须有效（会收到验证链接）

---

## 页面8: 验证结果

### 8a. Check your email (邮件验证页面)

**URL**: `https://services.sheerid.com/verify/...` (同表单页面)

**页面标题**: "Check your email"

**页面内容**:
```
标题: "Check your email"
说明: "An email has been sent to your email account with a personalized link to complete the verification process."
提示: "Please check for an email from us (verify@sheerid.com) for all the details."
按钮: "Re-send"
```

**触发条件**: 军人信息通过初步验证，等待邮件确认

**下一步**: 点击邮件中的验证链接

**选择器**:
| 元素 | uid/选择器 |
|------|-----------|
| 标题 | `heading "Check your email"` |
| 重发按钮 | `button "re-send"` |

### 8b. ✅ 验证成功 "You've been verified"（唯一成功标识！）

**URL**: SheerID 验证链接页面

**页面内容**:
```
标题: "You've been verified"
说明: "Enjoy 1 year of ChatGPT Plus on us. We also sent you a confirmation email with a link to claim your offer."
按钮: "Continue" → 点击后跳转 veterans-claim
```

**⚠️ 这是唯一的成功标识！任何带 Try Again 按钮的都是失败！**

**选择器**:
| 元素 | 选择器 |
|------|--------|
| 标题 | `heading "You've been verified"` 或页面包含 `you've been verified` |
| Continue 按钮 | `button "Continue"` 或 `link "Continue"` |

**成功后完整流程**:
```
1. 点击 "Continue" 按钮
   ↓
2. 跳转到 veterans-claim 页面
   ↓
3. 页面显示 "Claim offer" 按钮（不是 "Verify eligibility"）
   ↓
4. 点击 "Claim offer" 按钮
   ↓
5. 跳转 Stripe 支付页面 (pay.openai.com)
   ↓
6. 显示 $0.00 + ChatGPT Plus 订阅
   ↓
7. 账号获得 1 年 Plus ✅
```

**持久化记录**:
- 更新账号状态为 `verified`
- 更新验证记录为 `success`
- 记录成功的军人数据（first_name, last_name, branch, discharge_date）

### 8c. ❌ 验证失败场景（有 Try Again 按钮 = 失败！）

**⚠️ 核心理解：有 Try Again 按钮的页面都是失败状态！**

**失败场景（全部需要换军人数据重试）**:

| 错误类型 | 页面特征 | 按钮 | 含义 | 处理方式 |
|---------|---------|------|------|---------|
| Not approved | `Error` + `Not approved` | Try Again | 军人数据验证被拒绝 | 点击 → 换数据 |
| Unable to verify | `Error` + `We are unable to verify` | Try Again | 无法验证军人身份 | 点击 → 换数据 |
| sourcesUnavailable | `Error` + `sourcesUnavailable` | Try Again | SheerID 数据源不可用 | 点击 → 换数据 |
| Verification Limit Exceeded | `Verification Limit Exceeded` | ❌ 无 | **军人数据已被他人使用** | 直接导航 veterans-claim |
| Invalid discharge date | `Invalid discharge date` | Try Again | 退伍日期超12个月 | 换数据 |
| We couldn't verify | 需要上传文档 | - | 需要人工审核 | 换数据 |

**关键：**
- 有 Try Again 按钮 → 点击后换数据重试
- 没有按钮 → 直接导航到 `https://chatgpt.com/veterans-claim`
- **所有失败都只消耗军人数据，不消耗邮箱**

### 8c-1. ⚠️ "Already been approved" 特殊情况

**页面内容**:
```
标题: "Error"
说明: "Looks like you've already been approved for this offer."
按钮: "Try Again"
```

**这个情况需要区分处理**:

| 出现次数 | 含义 | 处理方式 |
|---------|------|---------|
| 第1-4次 | 邮件验证成功，但页面可能卡住 | 返回 veterans-claim 点击 Claim offer |
| **第5次及以上** | **邮箱已经验证过了！** | **标记邮箱为 `email_already_used`，需要换邮箱！** |

**脚本处理逻辑**:
```python
# 记录 already_approved 出现次数
already_approved_count = 0

if state == "email_verified":  # already been approved
    already_approved_count += 1

    if already_approved_count >= 5:
        # 邮箱已用过，需要换邮箱
        pool.mark_failed(email, "email_already_used: already been approved 5+ times")
        return False  # 退出，提示换邮箱
    else:
        # 正常流程，返回 veterans-claim
        await page.goto(VETERANS_CLAIM_URL)
```

### 8d. "Error - Not approved" 详情

**URL**: SheerID 验证链接（带 emailToken 参数）

**页面内容**:
```
标题: "Error"
说明: "Not approved"
按钮: "Try Again" → 跳转到 veterans-claim
底部: "Verification services powered by SheerID"
```

**触发条件**:
- 初步验证通过（发送了验证邮件）
- 但邮件链接验证后仍被拒绝
- 可能原因：数据在 SheerID 后端验证失败

**选择器**:
| 元素 | 选择器 |
|------|--------|
| 标题 | `heading "Error"` |
| 说明 | `StaticText "Not approved"` |
| 重试按钮 | `link "Try Again"` |

### 8e. "Error - Unable to verify" 详情

**URL**: SheerID 验证页面

**页面内容**:
```
标题: "Error"
说明: "We are unable to verify you at this time. If you believe you received this in error, please contact SheerID support."
按钮: "Try Again" → 跳转到 veterans-claim
底部: "Verification services powered by SheerID"
```

**触发条件**:
- 军人信息无法在 SheerID 数据库中验证
- 可能是数据不准确或已过期

**选择器**:
| 元素 | 选择器 |
|------|--------|
| 标题 | `heading "Error"` |
| 说明 | `StaticText` 包含 "unable to verify" |
| 重试按钮 | `link "Try Again"` |

---

## SheerID 风控机制分析

### 1. 身份一致性核查 (Identity Consistency Check)

**检测方式**:
- 交叉核对军人数据（姓名、生日、军种、退伍日期）
- 与 DMDC（国防人力数据中心）数据库比对
- 验证年龄是否符合服役资格

**应对策略**:
- ✅ 使用真实 BIRLS 数据（已故军人公开信息）
- ✅ 退伍日期动态生成（过去 1-11 个月）
- ⚠️ 部分数据可能已过期或被标记

### 2. 设备指纹与行为分析 (Device Fingerprinting & Behavior Analysis)

**检测方式**:
- 浏览器指纹（Canvas、WebGL、Audio、Fonts）
- 设备 ID（Screen、Navigator、Timezone）
- IP 地址和地理位置
- 请求频率和时间模式
- 鼠标/键盘行为特征

**应对策略**:

| 风险点 | 解决方案 | 实现 |
|-------|---------|------|
| 浏览器指纹 | Camoufox C++ 级伪造 | ✅ 已集成 |
| 设备 ID | 每次会话随机生成 | ✅ Camoufox 内置 |
| IP 地址 | 代理池轮换 | 🔄 待实现 |
| 请求频率 | 随机间隔 30s-2min | ✅ 已配置 |
| 行为特征 | 人类光标移动算法 | ✅ Camoufox humanize |

### 3. 推荐的风控对策

```python
# 代理池轮换（每次验证尝试换代理）
PROXY_POOL = [
    "http://user:pass@proxy1:port",
    "http://user:pass@proxy2:port",
    # ...
]

# 请求间隔随机化
VERIFY_INTERVAL_MIN = 60   # 最小间隔 60 秒
VERIFY_INTERVAL_MAX = 180  # 最大间隔 180 秒

# 连续失败暂停
MAX_CONSECUTIVE_FAILURES = 3
COOLDOWN_AFTER_FAILURES = 300  # 暂停 5 分钟
```

---

## 错误处理

| 错误类型 | 页面特征 | 处理方式 |
|---------|---------|---------|
| 邮箱已注册 | 跳转到登录页面 | 使用已有账号或换邮箱 |
| 密码太弱 | 显示红色提示 | 增加密码复杂度 |
| 验证码错误 | 显示错误提示 | 重新获取验证码 |
| 验证码过期 | 点击重发 | 重新发送邮件 |
| Rate limit | 显示限制提示 | 等待后重试 |

---

## Camoufox 自动化代码示例

```python
async def fill_login_form(page, email: str):
    """填写登录表单"""
    # 等待邮箱输入框
    email_input = page.locator('input[type="email"]')
    await email_input.fill(email)

    # 点击继续
    continue_btn = page.locator('button:has-text("继续")')
    await continue_btn.click()

async def fill_password(page, password: str):
    """填写密码"""
    password_input = page.locator('input[type="password"]')
    await password_input.fill(password)

    continue_btn = page.locator('button:has-text("继续")')
    await continue_btn.click()

async def fill_verification_code(page, code: str):
    """填写验证码"""
    code_input = page.locator('input[name="code"]')
    await code_input.fill(code)

    continue_btn = page.locator('button:has-text("继续")')
    await continue_btn.click()
```

---

## 已知问题与报错

### 1. SheerID "Please log in" 错误

**URL**: `https://services.sheerid.com/verify/690415d58971e73ca187d8c9/`

**错误页面内容**:
```
标题: "Please log in."
说明: "You must be logged in to verify. Log in to your account then try again."
按钮: "Try Again" → 跳转到 https://chatgpt.com/veterans-claim
```

**原因**: 直接访问 SheerID 验证 URL 时，没有携带 ChatGPT 的登录状态

**解决方案**: 必须从 `veterans-claim` 页面通过正常流程进入

### 2. 登录状态丢失问题

**场景**:
- 注册完成 → 跳转到 OpenAI Platform → 点击 "I'm looking for ChatGPT" → 回到 ChatGPT 主页
- 主页显示"登录"和"免费注册"按钮，而不是已登录状态

**可能原因**:
- Cookie 跨域问题（auth.openai.com vs chatgpt.com）
- 新 Chrome Profile 没有正确保存 Session
- 需要代理才能正确同步登录状态

### 3. veterans-claim 页面"登录"按钮不跳转

**现象**: 点击"登录"按钮后页面无变化

**分析**:
- 按钮是 `<button>` 不是 `<a>`
- 可能需要 JavaScript 触发
- 或者被网络/代理问题阻止

### 4. JSON 解析错误

**错误信息**: `Unexpected token '<', "<!DOCTYPE "... is not valid JSON`

**场景**: 登录时点击"继续"后

**原因分析**:
- 服务器返回了 HTML 而不是 JSON
- 可能是网络/代理问题
- 或者请求被拦截/重定向

**解决方案**: 点击"重试"或检查代理设置

### 5. OpenAI Platform 欢迎页面

**URL**: `https://platform.openai.com/welcome?step=create`

**页面内容**:
- 标题: "Welcome to OpenAI Platform"
- 要求创建 Organization
- 底部有 "I'm looking for ChatGPT" 链接

**说明**: 新用户注册后会跳转到这里，需要点击 "I'm looking for ChatGPT" 回到 ChatGPT

### 6. Verification Limit Exceeded (军人信息已被验证)

**URL**: SheerID 验证页面

**错误页面内容**:
```
标题: "Verification Limit Exceeded"
说明: "We're glad you're enthusiastic, but it looks like you've already redeemed or attempted to redeem this offer."
底部: "Verification services powered by SheerID"
```

**原因**:
- **该军人信息已经被验证过了**（被其他人或之前的尝试使用）
- 同一军人数据只能验证一次
- 与账号无关，是数据级别的限制

**解决方案**:
- **更换军人数据** - 使用新的 BIRLS 数据重试
- 当前账号可以继续使用
- 将已使用的军人数据记录到 `veterans_used.json`
- ⚠️ 持久化规则：验证过的数据必须标记，避免重复使用

---

## OpenAI 验证码邮件格式

**发件人**: OpenAI / ChatGPT

**Subject 格式**:
- 中文: `你的 ChatGPT 代码为 XXXXXX`
- 英文: `Your ChatGPT code is XXXXXX`

**验证码提取**:
```python
# 从 Subject 提取
patterns = [
    r'Subject:.*?代码为\s*([A-Z0-9]{6})',
    r'Subject:.*?code\s+is\s+([A-Z0-9]{6})',
]
```

---

## ⚠️ 重要：ChatGPT 账号 vs 临时邮箱区分（2025-12-28 更新）

### 核心概念

```
┌────────────────────────────────────────────────────────────────────┐
│                    验证成功后 Plus 归属                            │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  验证成功后，1 年 Plus 给的是【登录的 ChatGPT 账号】               │
│  而不是【接收验证链接的临时邮箱】                                  │
│                                                                     │
│  临时邮箱只是消耗品，用于接收 SheerID 验证链接                     │
│  验证成功后这个临时邮箱就不能再用了（跟军人数据一样消耗掉）        │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### 不同模式下的区别

| 模式 | ChatGPT 账号 | 接收邮箱 | 关系 | 账号信息 |
|------|-------------|---------|------|---------|
| **全自动** | 临时邮箱 A | 临时邮箱 A | 一致 | email + password + jwt |
| **半自动-临时邮箱登录** | 临时邮箱 A | 临时邮箱 B | 不同 | A 完整，B 标记 consumed |
| **半自动-自有邮箱登录** | Gmail 等 | 临时邮箱 | 不同 | Gmail 无 jwt，临时邮箱 consumed |

### 数据结构

```
accounts 表（记录真实验证通过的 ChatGPT 账号）:
{
  "email": "xxx@009025.xyz",        // ChatGPT 登录邮箱
  "password": "xxxxxx",             // ChatGPT 密码
  "jwt": "eyJ...",                  // 仅 @009025.xyz 有，自有邮箱无
  "status": "verified",
  "consumed_email": "yyy@009025.xyz", // 消耗的临时邮箱（可选）
  "profile_name": "John Doe",       // 注册时填的名字
  "profile_birthday": "1990-01-15"  // 注册时填的生日
}

email_pool（临时邮箱池）:
{
  "address": "yyy@009025.xyz",
  "jwt": "eyJ...",
  "status": "consumed",              // 新状态：已消耗
  "consumed_by": "xxx@009025.xyz",   // 被哪个账号消耗的
  "consumed_at": "2025-12-28T03:00:00"
}
```

### 前端显示规则

**账号列表显示的是：真实验证通过的 ChatGPT 账号**

| ChatGPT 账号类型 | 显示内容 |
|-----------------|---------|
| @009025.xyz 临时邮箱 | email + password + jwt + 临时邮箱凭证 |
| 自有邮箱 (Gmail 等) | email + password + 消耗的临时邮箱（无 jwt） |

### 半自动模式检测

1. **一致性检测**：
   - 如果登录账号是 `@009025.xyz` → 提示接收邮箱应该填一样的
   - 因为临时邮箱注册的 ChatGPT，接收验证也用同一个邮箱最合理

2. **已消耗检测**：
   - 如果选择/输入的临时邮箱已经 `consumed` 或 `verified`
   - 提示：邮箱已验证过，会导致报错 "already been approved"，请换邮箱

### 错误案例（之前的问题）

```
错误记录：
  账号列表显示：nnxp47bwy@009025.xyz 验证通过

实际情况：
  真实验证通过的账号：vethuxntarz@009025.xyz
  消耗的临时邮箱：nnxp47bwy@009025.xyz

正确记录应该是：
  accounts 表：vethuxntarz@009025.xyz (verified)
  email_pool：nnxp47bwy@009025.xyz (consumed, consumed_by: vethuxntarz)
```

---

## 更新日志

### 2025-12-25 UTC+8
- 初始版本，记录登录注册流程 (页面1-4)
- 新增确认年龄页面 (页面5)
- 新增已登录 Veterans 页面 (页面6)
- **完整记录 SheerID 表单选择器 (页面7)**
- 新增已知问题与报错
- 新增 Verification Limit Exceeded 错误
- 补充验证结果页面 (页面8)

### 2025-12-26 23:10 UTC+8
- **新增 sourcesUnavailable 错误**
  - 页面内容: `Error` + `sourcesUnavailable`
  - 有 Try Again 按钮
- **新增 Verification Limit Exceeded 无按钮情况**
  - ⚠️ 此页面没有 Try Again 按钮！
  - 需要直接导航到 veterans-claim
- **更新成功页面详情**
  - 标题: "You've been verified"
  - 说明: "Enjoy 1 year of ChatGPT Plus on us. We also sent you a confirmation email with a link to claim your offer."
  - 按钮: Continue
- **修复验证链接末尾括号问题**
  - 邮件中的链接可能包含 `)` 等字符
  - 需要清理: `["\'>)(\]\[]+$`

### 2025-12-28 01:10 UTC+8
- **新增 "Already been approved" 页面状态**
  - 点击邮件验证链接后可能显示
  - 页面内容: `Error` + `Looks like you've already been approved for this offer.`
  - 有 Try Again 按钮
  - **这不是错误，是邮件验证成功的状态！**
  - 处理方式：返回 veterans-claim 点击 Claim offer
- **修复 get_by_address 方法名 bug**
  - `EmailPoolManager.get_email_by_address` → `get_by_address`
- **明确成功标准**
  - 只有到达 Stripe 结算页面才算验证成功
  - 流程：填表 → check_email → 点击链接 → Claim offer → Stripe

### 2025-12-28 03:00 UTC+8
- **⚠️ 重要修复：账号 vs 临时邮箱区分**
  - 问题：之前把"接收邮箱"当作"验证通过的账号"，导致数据错误
  - 修正：验证通过的是【登录的 ChatGPT 账号】，临时邮箱只是消耗品
- **新增临时邮箱 consumed 状态**
  - 临时邮箱验证后标记为 `consumed`（消耗品，不能再用）
  - 跟军人数据消耗逻辑一样
- **账号信息显示规则**
  - 如果 ChatGPT 账号是 @009025.xyz → 提供完整 JWT
  - 如果 ChatGPT 账号是自有邮箱 → 不提供 JWT，但记录消耗的临时邮箱
- **半自动模式检测**
  - 如果登录账号是 @009025.xyz → 提示接收邮箱应该填一样的
  - 如果选择的临时邮箱已 consumed → 提示换邮箱

### 2025-12-28 02:00 UTC+8
- **澄清 Try Again 按钮含义**
  - Try Again = 失败状态，需要换数据重试
  - 可能情况：not_approved / unable_to_verify / verification_limit 等
  - **不是成功！有 Try Again 就是失败**
- **明确成功的唯一标识**
  - 成功 = "You've been verified" + Continue 按钮
  - 点击 Continue → 跳转 veterans-claim → Claim offer → Stripe($0.00)
- **新增 "already been approved" 重复检测**
  - 第1-4次出现：邮件验证成功，返回 veterans-claim 点击 Claim offer
  - 第5次及以上：邮箱已经验证过，标记为 `email_already_used`，需要换邮箱
  - 脚本新增 `already_approved_count` 计数器
- **半自动模式邮箱追踪完善**
  - 新增 `--account` 参数：记录关联的 ChatGPT 账号
  - 邮箱池新增 `linked_account` 字段：追踪临时邮箱给哪个账号用
  - 成功时保存完整军人信息到 `verified_veteran` 字段
- **持久化信息完整性**
  - 邮箱池记录：address, jwt, status, linked_account, verified_veteran
  - 数据库记录：accounts 表 + verifications 表关联

### 2025-12-31 00:35 UTC+8
- **⚠️ CDP 全自动登录逻辑问题发现**
  - 问题：脚本退出登录后，没有正确执行登录流程，直接跳转到了验证页面
  - 原因分析：
    1. `register_or_login_chatgpt` 函数在检测登录状态时可能过早返回 True
    2. 检测用户头像按钮的逻辑 (`profile_btn`) 可能在退出登录后仍匹配到某些元素
    3. 需要更严格的登录状态检测
  - **正确的 CDP 全自动登录流程应该是**：
    ```
    1. logout_chatgpt() 退出当前登录 → 页面留在 chatgpt.com
    2. register_or_login_chatgpt() 在 chatgpt.com 主页点击"登录"按钮
    3. 跳转到 auth.openai.com → 输入邮箱 → 继续
    4. 输入密码（新用户创建，老用户输入）→ 继续
    5. 如需验证码 → 从临时邮箱获取验证码 → 输入
    6. 如有 about-you 页面 → 填写姓名+生日
    7. 登录成功 → 返回 True
    8. run_verify_loop 导航到 veterans-claim → 开始验证
    ```
  - 待修复点：
    - 移除过早的 `return True` 检测逻辑
    - 确保登录流程完整执行后才返回成功

### 2025-12-25 20:00 UTC+8
- 新增 "Error - Unable to verify" 错误详情
- **新增 SheerID 风控机制分析**
  - 身份一致性核查说明
  - 设备指纹与行为分析
  - 风控对策表格
- 完善失败场景处理表格（全部换数据重试）
- 明确 Try Again 按钮的跳转逻辑
