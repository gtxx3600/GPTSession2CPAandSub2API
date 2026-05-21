# ChatGPT Session to CPA / sub2api / Cockpit / 9router / AxonHub

纯前端单页面工具，用来把 ChatGPT Web 登录 session JSON 转换成 CPA、sub2api、Cockpit Tools、9router 或 AxonHub 可导入 JSON。

## 在线使用

### [**》》 点我直接使用 《《**](https://gtxx3600.github.io/GPTSession2CPAandSub2API/)

## 使用提示

Plus 号可以用此方式导入中转站使用；Free 号的 access token 不能用于调用接口。

本工具可用来解决 Codex OAuth 登录需要绑定手机的问题。Plus 账号通过 Web 登录后的 session 就能生成可导入中转站的账号 JSON 数据；这类数据没有 `refresh_token`，但 `access_token` 有效期通常足够长。

解释一下： plus激活前（free状态）或激活后（plus状态）获取的session在使用上没有区别（free时拿到的session, 激活plus后就可以调模型了），只是账号级别标识有点区别（标识为free or plus），不影响调模型。 换句话讲，不管你啥时候拿到的session, 用本项目转换导入中转站，只要账号当前激活了plus, 就能正常调模型接口。

本工具主要针对 Plus 账号适用，Free 账号即使转换了也没有权限调用 GPT 模型。GoPay 拉闸了，没法每天发 Plus 了；加入 Discord 频道免费获取 GPT 撸羊毛信息，然后配合本工具导入 CPA or Sub2API 使用。

## GOAPY 拉闸了， Party is OVER ～ 
## **加入 Discord 频道免费获取 GPT 撸羊毛信息：**

### [**》》 加入 Discord 频道 《《**](https://discord.gg/GFmHY2TZNy)

邀请链接：`https://discord.gg/GFmHY2TZNy`


## 支持输入

支持粘贴或拖入 ChatGPT Web session JSON，例如包含：

- `user.email`
- `accessToken`
- `sessionToken`
- `expires`
- `account.id`
- `account.planType`

也支持粘贴或拖入 9router Codex OAuth JSON，例如包含 `accessToken`、`refreshToken`、`expiresAt`、`providerSpecificData.chatgptAccountId` 和 `providerSpecificData.chatgptPlanType`。

也支持粘贴或拖入 AxonHub Codex auth.json，例如包含 `tokens.access_token`、`tokens.refresh_token`、`tokens.id_token` 和 `last_refresh`。

页面也会尝试从 `accessToken` 的 JWT payload 中补充邮箱、账号 ID、用户 ID、计划类型和过期时间。

## 输出格式

- `CPA`：生成 Codex CPA auth JSON，包含 `type: "codex"`、`access_token`、`session_token`、`id_token`、`email`、`account_id`、套餐和过期时间等字段；缺少真实 `id_token` 时会根据 session 与 access token claims 构造 Codex 可解析的占位 JWT claims。
- `sub2api`：生成参考 `CPA2sub2API` 项目的 `exported_at/proxies/accounts` 结构，账号平台为 `openai`，类型为 `oauth`。
- `Cockpit`：生成 Cockpit Tools Codex JSON 导入可识别的扁平 token 格式，包含 `id_token`、`access_token`、`refresh_token`、`account_id`、`email`、`expired` 等字段。
- `9router`：生成 9router Codex OAuth JSON，包含 `accessToken`、`refreshToken`、`expiresAt`、`providerSpecificData`、`provider`、`authType`、`priority`、`isActive`、`createdAt` 和 `updatedAt` 等字段。
- `AxonHub`：生成 AxonHub Codex auth.json，包含 `auth_mode: "chatgpt"`、`last_refresh` 和 `tokens.access_token/refresh_token/id_token`。缺少真实 `refresh_token` 时会写入 `__missing_refresh_token__` 占位值，方便在 access token 过期前试用；过期后不能自动刷新。
ChatGPT Web session 通常不包含 OAuth 文件里常见的 `refresh_token`，因此 access token 过期后不能自动刷新。

## 本地使用

直接打开：

```text
docs/index.html
```

所有解析和转换都在浏览器本地完成，不上传 token，不写入本地存储。

## Python CLI / Python API

如果不想打开网页，可以直接用 Python 包。它不需要浏览器、Node.js、数据库或网络请求，只使用 Python 标准库。

### 环境

```text
Python >= 3.10
```

### CLI

从文件生成 Cockpit JSON：

```bash
python -m gptsession_converter --format cockpit --input input.summary.json --output cockpit.json
```

从 stdin 生成 Cockpit JSON：

```bash
cat input.txt | python -m gptsession_converter --format cockpit > cockpit.json
```

支持的输入：

- 普通 ChatGPT Web session JSON
- 旧 `.summary.json` 这类外层包裹 JSON，只要内部能递归找到 `accessToken`
- 包含 JSON 片段的 `.txt`
- 简单 `key=value` / `key: value` 文本，例如 `accessToken=...`

支持的输出格式：

- `cockpit`
- `cpa`
- `sub2api`
- `9router`
- `axonhub`

### Python 调用

```python
from gptsession_converter import convert_file, convert_text

result = convert_file("input.summary.json", output_format="cockpit")
cockpit_json = result.output

result = convert_text(raw_text, output_format="cockpit")
```

安全边界：

- 不联网
- 不上传 token
- 不写入本地存储
- CLI 默认只把结果写到你指定的输出文件或 stdout
- 示例里不要使用真实 token；真实 session JSON 等同敏感登录凭证
