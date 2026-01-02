# 快速修复指南

## 本次更新内容（2025-12-28 23:50）

### ✅ 已修复

1. **代理解析 API 失败** - 添加缺失的 `parse_proxy_format` 导入
2. **CDP 代理冲突** - CDP 模式不再设置代理（由浏览器插件管理）
3. **环境变量管理** - 新增自动同步工具

---

## 1. 环境变量同步工具

### 功能
- 从 `.env.example` 自动读取新参数
- 合并到 `.env` 文件
- **保留已有配置**，只添加新参数
- 自动备份原文件

### 使用方法

```bash
# 运行同步工具
python scripts\sync_env.py

# 提示示例：
# [警告] 此操作会修改 E:\veterans-verify\.env
#        原文件将备份到 E:\veterans-verify\.env.backup
#
# 是否继续？(y/n): y
#
# [读取] 已有配置: 15 个参数
# [备份] 已备份原文件到: E:\veterans-verify\.env.backup
#   [+] 新增参数: PROXY_HTTP_FILE=
#   [+] 新增参数: PROXY_HTTPS_FILE=
#   [+] 新增参数: PROXY_SOCKS5_FILE=
#   [+] 新增参数: PROXY_DEFAULT_PROTOCOL=http
#   [+] 新增参数: PROXY_PREFER_TYPE=http
#   [+] 新增参数: PROXY_STRATEGY=round_robin
#   [+] 新增参数: PROXY_BAD_TTL=900
#   [+] 新增参数: PROXY_MODE=pool_with_fallback
#
# [完成] 同步完成!
#    - 保留参数: 15 个
#    - 新增参数: 8 个
#    - 输出文件: E:\veterans-verify\.env
#
# [提示] 请检查新增参数，根据需要修改默认值
```

### 配置新参数

同步后，编辑 `.env` 文件，配置代理池：

```bash
# 代理池文件（选择一个或多个）
PROXY_HTTP_FILE=data/http美国.txt       # HTTP 代理池
PROXY_HTTPS_FILE=                       # HTTPS 代理池（可选）
PROXY_SOCKS5_FILE=                      # SOCKS5 代理池（可选）

# 代理策略（推荐）
PROXY_MODE=pool_with_fallback           # 代理池优先，失败时用主代理
PROXY_STRATEGY=round_robin              # 轮换策略
```

---

## 2. 代理管理界面

### 前端操作

1. **刷新浏览器** → http://127.0.0.1:7870
2. **点击"代理管理" tab**
3. **粘贴或上传代理列表**
   - 支持格式：`ip:port`, `ip:port:user:pass`, `http://ip:port`
   - 自动转换为标准格式
4. **查看统计** - 右侧显示代理池状态

### 后端 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/proxy/parse` | POST | 解析粘贴的代理文本 |
| `/api/proxy/upload` | POST | 上传代理文件解析 |
| `/api/proxy/stats` | GET | 获取代理池统计 |

---

## 3. CDP 模式代理说明

### 🔥 重要变更

**之前**：CDP 模式尝试使用主代理（会与浏览器插件冲突）
**现在**：CDP 模式不设置任何代理，完全由浏览器插件管理

### 代理使用逻辑

| 模式 | 代理来源 | 说明 |
|------|---------|------|
| **CDP（手动登录）** | 浏览器插件 | 程序不设置代理 |
| **Camoufox（无头）** | 代理池 | 程序管理代理，支持轮换 |

### 代码位置

`app.py:get_proxy_for_task()`：

```python
# CDP 模式：不使用代理（浏览器插件处理）
if mode == 'cdp':
    logger.info(f"[Proxy] CDP 模式 - 不设置代理（由浏览器插件管理）")
    return None
```

---

## 4. Camoufox 指纹持久化

### 新增功能

每个账号独立的 Profile 目录，持久化：
- 浏览器指纹
- Cookies
- LocalStorage
- Session

### 目录结构

```
profiles/
  ├── a1b2c3d4e5f6g7h8/    # 账号1 的 Profile
  ├── h8g7f6e5d4c3b2a1/    # 账号2 的 Profile
  └── ...
```

### 数据库字段

```sql
ALTER TABLE accounts ADD COLUMN profile_path VARCHAR(255);
```

### Profile 管理

```python
from profile_manager import get_or_create_profile, delete_profile

# 获取或创建 Profile
profile_path = get_or_create_profile("test@009025.xyz")

# 删除 Profile（重置指纹）
delete_profile("test@009025.xyz")
```

---

## 5. 前端显示增强

### 账号列表

新增两列：
- **代理** - 显示代理 IP（紫色高亮）
- **Profile** - 显示是否有 Profile（✓ / -）

### 账号详情

新增显示：
- 完整代理 URL
- Profile 路径

---

## 🔧 故障排查

### 代理解析失败

**症状**：粘贴或上传代理时没有反应

**原因**：缺少 `parse_proxy_format` 导入

**修复**：已在 `app.py` 中添加导入，重启 Flask 即可

---

### CDP 模式代理冲突

**症状**：CDP 模式下代理不生效或冲突

**原因**：程序设置的代理与浏览器插件冲突

**修复**：CDP 模式现在不设置代理，完全由插件管理

---

### Profile 目录丢失

**症状**：数据库有 `profile_path` 记录，但目录不存在

**解决**：重新创建 Profile

```python
from profile_manager import create_profile
create_profile("email@example.com")
```

---

## 📝 下次需要完善的功能

1. ~~代理管理界面~~ ✅
2. ~~Camoufox 指纹持久化~~ ✅
3. ~~环境变量同步工具~~ ✅
4. **邮箱池管理界面**（待开发）
5. **自动分配代理**（待开发）
6. **Profile 清理工具**（待开发）
7. **代理健康检测**（待开发）

---

## 🚀 立即使用

```bash
# 1. 同步环境变量（添加新参数）
python scripts\sync_env.py

# 2. 编辑 .env，配置代理池
notepad .env

# 3. 重启 Flask（如果正在运行）
# Ctrl+C 停止
python app.py

# 4. 刷新浏览器
# http://127.0.0.1:7870
```
