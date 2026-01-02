# 代理池使用指南

> 版本: v1.0
> 更新: 2025-12-28

---

## 功能概述

代理池管理器支持多个 HTTP/SOCKS5 代理的自动轮换，防止单 IP 被封禁。

### 核心特性

- ✅ **多代理支持** - HTTP/HTTPS/SOCKS5 代理
- ✅ **智能轮换** - 轮询或随机分配策略
- ✅ **失败标记** - 自动识别失败代理并冷却
- ✅ **自动恢复** - 冷却后自动重新启用
- ✅ **状态监控** - 实时查看代理池状态

---

## 配置方法

### 方法 1: 环境变量（适合少量代理）

在 `.env.local` 中配置：

```bash
# 代理列表（分号分隔）
PROXY_LIST=http://1.2.3.4:8080;http://user:pass@5.6.7.8:1080;socks5://9.10.11.12:1080

# 分配策略（可选，默认 round_robin）
PROXY_STRATEGY=round_robin

# 失败代理冷却时间（可选，默认 900 秒）
PROXY_BAD_TTL=900
```

### 方法 2: 文件加载（推荐，适合大量代理）

1. 复制示例文件：
   ```bash
   cp data/proxies.txt.example data/proxies.txt
   ```

2. 编辑 `data/proxies.txt`：
   ```
   # HTTP 代理
   http://1.2.3.4:8080
   http://5.6.7.8:3128

   # 带认证的 HTTP 代理
   http://username:password@9.10.11.12:8080

   # SOCKS5 代理
   socks5://13.14.15.16:1080
   socks5://user:pass@17.18.19.20:1080
   ```

3. 在 `.env.local` 中配置：
   ```bash
   PROXY_FILE=./data/proxies.txt
   PROXY_STRATEGY=round_robin
   ```

---

## 配置参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `PROXY_FILE` | 代理列表文件路径（优先级最高） | 无 |
| `PROXY_LIST` | 代理列表（分号分隔） | 无 |
| `PROXY_SERVER` | 单个代理（兼容旧配置） | 无 |
| `PROXY_STRATEGY` | 分配策略：`round_robin`/`random` | `round_robin` |
| `PROXY_BAD_TTL` | 失败代理冷却时间（秒） | 900 |

**优先级**：`PROXY_FILE` > `PROXY_LIST` > `PROXY_SERVER`

---

## 分配策略

### round_robin（轮询）

按顺序依次使用每个代理，适合代理质量相近的场景。

```
任务1 → 代理A
任务2 → 代理B
任务3 → 代理C
任务4 → 代理A（循环）
```

### random（随机）

随机选择代理，适合代理质量不一的场景。

```
任务1 → 代理B
任务2 → 代理A
任务3 → 代理B（可能重复）
任务4 → 代理C
```

---

## 失败处理机制

### 自动标记失败

当验证任务失败时，使用的代理会被自动标记为失败：

```
代理 1.2.3.4:8080 → 任务失败 → 标记失败 → 进入冷却（15分钟）
```

### 自动恢复

冷却时间到达后，代理自动恢复为可用状态：

```
标记失败后 15 分钟 → 自动恢复 → 重新加入可用代理池
```

### 手动恢复

验证任务成功时，如果代理之前被标记为失败，会立即恢复：

```
代理 1.2.3.4:8080 → 任务成功 → 从失败列表移除 → 立即可用
```

---

## 状态监控

### API 查询

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:7870/api/status
```

返回示例：

```json
{
  "success": true,
  "proxy_pool": {
    "total": 10,           // 总代理数
    "available": 8,        // 可用代理数
    "bad": 2,              // 失败冷却中的代理数
    "strategy": "round_robin",
    "proxies": [           // 可用代理列表（密码已隐藏）
      "http://1.2.3.4:8080",
      "http://username:***@5.6.7.8:1080"
    ]
  }
}
```

### 日志监控

启动时会显示代理池状态：

```
[ProxyManager] 初始化完成，共 10 个代理
[ProxyManager] 策略: round_robin, 失败冷却: 900s
```

任务运行时会记录代理使用：

```
使用代理: http://username:***@1.2.3.4:8080
[ProxyManager] 分配代理: http://username:***@1.2.3.4:8080
```

失败时会记录：

```
[ProxyManager] 标记失败代理: http://username:***@1.2.3.4:8080
[ProxyManager] 剩余可用代理: 9/10
```

---

## 最佳实践

### 1. 代理质量

- ✅ 使用**美国住宅代理**（与 Veterans 验证匹配）
- ✅ 确保代理速度稳定（延迟 < 500ms）
- ❌ 避免使用数据中心代理（容易被识别）
- ❌ 避免使用免费公共代理（成功率低）

### 2. 代理数量

- **单账号验证**：3-5 个代理即可
- **批量验证**：建议 10+ 个代理
- **高并发**：代理数量 ≥ 并发任务数 × 2

### 3. 冷却时间

- **默认 900 秒（15 分钟）**适合大多数场景
- 如果代理质量高，可适当缩短（如 600 秒）
- 如果经常失败，可适当延长（如 1800 秒）

### 4. 错误处理

如果所有代理都失败：

```
[ProxyManager] 没有可用代理！
警告: 代理池为空，使用直连
```

此时会自动切换为直连模式（无代理）。

---

## 故障排查

### 代理连接失败

```
错误: ProxyConnectionError
```

**解决方案**：
1. 检查代理格式是否正确
2. 测试代理是否可用（ping 或 curl）
3. 检查防火墙设置

### 代理认证失败

```
错误: ProxyAuthenticationRequired
```

**解决方案**：
1. 检查用户名密码是否正确
2. 确认代理支持认证
3. 特殊字符需要 URL 编码（如 `@` → `%40`）

### 所有代理都失败

```
[ProxyManager] 剩余可用代理: 0/10
```

**解决方案**：
1. 等待冷却时间结束（自动恢复）
2. 检查代理提供商是否正常
3. 临时禁用代理池（删除 `PROXY_FILE` 配置）

---

## 示例配置

### 小型项目（3 个代理）

```bash
# .env.local
PROXY_LIST=http://1.2.3.4:8080;socks5://user:pass@5.6.7.8:1080;http://9.10.11.12:3128
PROXY_STRATEGY=random
PROXY_BAD_TTL=600
```

### 生产环境（文件加载）

```bash
# .env.local
PROXY_FILE=./data/proxies.txt
PROXY_STRATEGY=round_robin
PROXY_BAD_TTL=900
```

```
# data/proxies.txt（假设你有很多 HTTP 代理）
http://user1:pass1@proxy1.example.com:8080
http://user2:pass2@proxy2.example.com:8080
http://user3:pass3@proxy3.example.com:8080
...
```

---

## 技术架构

### 核心模块

- `proxy_manager.py` - 代理池管理器
- `config.py` - 配置加载
- `app.py` - Flask 应用集成

### 工作流程

```
1. 启动 Flask → 加载配置 → 初始化代理池
2. 创建验证任务 → 从代理池获取代理
3. 任务执行 → 使用代理连接
4. 任务完成 → 更新代理状态（成功/失败）
5. 失败代理 → 标记冷却 → 定时恢复
```

---

## 常见问题

**Q: 是否必须使用代理？**
A: 不是。未配置代理时，系统会使用直连模式。

**Q: 可以混用 HTTP 和 SOCKS5 代理吗？**
A: 可以。代理池支持多种协议混合。

**Q: 代理失败后多久恢复？**
A: 默认 900 秒（15 分钟），可通过 `PROXY_BAD_TTL` 配置。

**Q: 如何查看当前使用的代理？**
A: 查看日志或调用 `/api/status` API。

**Q: 代理池满了怎么办？**
A: 代理池没有上限，可以添加任意数量的代理。

---

## 更新日志

### 2025-12-28

- ✅ 初始版本发布
- ✅ 支持 HTTP/HTTPS/SOCKS5 代理
- ✅ 轮询和随机分配策略
- ✅ 失败标记和自动恢复
- ✅ 集成到 Flask 应用
