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

## 页面2: 登录或注册

**URL**: `https://auth.openai.com/log-in-or-create-account`

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

### Status 字段 (状态)

| 选项值 | 说明 |
|--------|------|
| Active Duty | 现役军人 |
| Military Veteran or Retiree | 退伍军人或退休人员 |
| Reservist or National Guard | 预备役或国民警卫队 |

**选择器**: `combobox "Status"`

### Branch of service 字段 (军种)

| 选项值 | BIRLS 数据对应 |
|--------|---------------|
| Air Force | Air Force |
| Army | Army |
| Coast Guard | Coast Guard |
| Marine Corps | Marine Corps |
| Navy | Navy |
| Space Force | Space Force |

**选择器**: `combobox "Branch of service"`

### 完整表单字段

| 字段 | 类型 | Playwright 选择器 | 说明 |
|------|------|------------------|------|
| Status | 下拉 | `combobox "Status"` | 军事状态 |
| Branch of service | 下拉 | `combobox "Branch of service"` | 军种 |
| First name | 文本 | `textbox "First name"` | 名 |
| Last name | 文本 | `textbox "Last name"` | 姓 |
| Date of birth - Month | 下拉 | `combobox "Date of birth..."` | 出生月 |
| Date of birth - Day | 文本 | `textbox "Day"` (第1个) | 出生日 |
| Date of birth - Year | 文本 | `textbox "Year"` (第1个) | 出生年 |
| Discharge date - Month | 下拉 | `combobox "Discharge date..."` | 退伍月 |
| Discharge date - Day | 文本 | `textbox "Day"` (第2个) | 退伍日 |
| Discharge date - Year | 文本 | `textbox "Year"` (第2个) | 退伍年 |
| Email address | 文本 | `textbox "Email address..."` | 邮箱 |
| 提交按钮 | 按钮 | `button "Verify My Eligibility"` | 初始 disabled |

### 关键约束

- **Discharge date 必须在过去12个月内!**
- 提交按钮在所有必填字段填写后才启用
- 邮箱必须有效（会收到验证链接）

---

## 页面8: 验证结果

> ⚠️ 待补充完整流程

**成功**: 跳转 `chatgpt.com`，账号显示 Plus

**失败场景**:
- "Invalid discharge date" - 退伍日期超过12个月
- "Already verified" - 信息已被使用
- "Unable to verify" - 信息无法验证
- "We couldn't verify your status" - 需要上传文档

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

## 更新日志

- 2025-12-25: 初始版本，记录登录注册流程 (页面1-4)
- 2025-12-25: 新增确认年龄页面 (页面5)
- 2025-12-25: 新增已登录 Veterans 页面 (页面6)
- 2025-12-25: **完整记录 SheerID 表单选择器 (页面7)**
  - Status 下拉选项
  - Branch of service 下拉选项
  - 所有表单字段选择器
- TODO: 补充验证结果页面 (页面8)
