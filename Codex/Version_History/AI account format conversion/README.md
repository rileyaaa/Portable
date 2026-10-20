# AI 账号格式转换器（本地离线）

目录：当前便携包内 `Version_History/AI account format conversion`（位置无关）

## 运行

双击 `index.html`，或右键选择浏览器打开。

这是静态 HTML/CSS/JS 工具，不依赖后端。默认不上传、不联网、不使用浏览器存储。只有你主动点击下载时，浏览器才会保存导出文件。

## 本轮新增功能

### 1. 一键 ZIP 批量导出

新增 `下载ZIP` 按钮。会把当前所有导出结果打包成：

```text
outputs/sub2api.json
outputs/accounts.env
outputs/account-report.json
01-account/codex-auth.json
01-account/sub2api-account.json
...
```

ZIP 在浏览器内存中即时生成，不写临时文件。

### 2. 格式识别报告

新增 `格式识别报告` 输出，并在页面显示识别报告：

- 账号数量
- 类型：OAuth / API key / opaque
- email/user_id/account_id/plan/client_id
- token 是否存在
- refresh_token 是否存在
- 过期时间 exp
- 风险/可用性评分
- 重复账号检测结果

### 3. JWT 解码查看器（开关控制）

开关：`3 JWT 解码查看器`

打开后显示每个账号的 `access_token` / `id_token` JWT payload，方便查看：

- `exp`
- `iat`
- `client_id`
- `chatgpt_account_id`
- `chatgpt_user_id`
- `chatgpt_plan_type`
- `scp`

预览仍受“预览脱敏”控制；JWT 面板用于本地查看，不联网。

### 4. 规则编辑器（开关控制）

开关：`4 规则编辑器`

用于适配奇怪字段名。例如输入：

```json
{"token":"xxx","mail":"a@b.com","url":"https://api.openai.com/v1"}
```

规则填：

```json
{"token":"access_token","mail":"email","url":"base_url"}
```

转换前会先把字段名映射成标准字段。

### 5. 平台模板库

新增导出模板：

- Cherry Studio 配置草稿
- Chatbox 配置草稿
- LobeChat 配置草稿
- 原有 One API / New API、LiteLLM、OpenAI-compatible 继续保留

不同客户端版本字段可能有差异，所以这些模板是“草稿”，可复制后微调。

### 6. 本地加密账号库（开关控制）

开关：`6 加密账号库`

功能：

- 用密码把当前识别结果加密为 `ai-account-vault.json`
- 以后选择该 vault 文件并输入密码，可解密导入
- 算法：PBKDF2-SHA256 150000 次 + AES-GCM
- 不使用 localStorage/sessionStorage/IndexedDB，不自动落盘

### 7. 有效期/续期能力评分

页面报告和 `account-report.json` 会给每个账号打标签：

- `长期可续期`：有 refresh_token
- `短期可用`：只有 access/id token
- `可能失败`：只有 sessionToken 或字段不完整
- `API Key`：适合 API/代理平台，不能反向变 OAuth
- `字段不足`：缺核心 token/key

### 8. 重复账号检测

基于以下字段做本地重复检测：

- email
- user_id
- account_id
- token fingerprint

发现重复会在报告里提示涉及的账号编号。

### 9. 导出前字段补全（开关控制）

开关：`9 导出前字段补全`

可在页面表格里补：

- name
- email
- account_id
- user_id
- base_url
- plan

点击“应用补全并重新生成”后，所有导出结果会更新。

### 10. 严格离线自检

新增 `离线自检` 按钮。用于确认工具代码没有调用联网/存储能力：

- 无业务网络请求
- 不使用 localStorage
- 不使用 sessionStorage
- 不使用 IndexedDB
- 不注册 Service Worker
- 不使用 Cache API

## 已支持输入

### 单账号

1. ChatGPT web session JSON：`https://chatgpt.com/api/auth/session` 页面 JSON。
2. Codex auth.json：`auth_mode: chatgpt` + `tokens`。
3. sub2api 单账号对象：`platform/type/credentials`。
4. 通用 OAuth token JSON：`access_token/id_token/refresh_token/account_id/email/client_id`。
5. OpenAI API Key：`sk-...`、`sk-proj-...`、`.env`。
6. OpenAI-compatible proxy：`base_url + api_key`、Bearer Header、Cookie/Header 文本。

### 多账号/数组

1. sub2api 完整导出：`{ accounts: [...] }`。
2. 纯数组：`[ {...账号1...}, {...账号2...} ]`。
3. 包装数组：`{ data: [...] }`、`{ items: [...] }`、`{ tokens: [...] }`。
4. 混合数组：OAuth、API key、Codex auth、web session、字符串 env/key 可混放。

## 已支持输出

- Codex auth.json
- Codex auth 批量数组
- 批量文件包 JSON
- ZIP 批量包
- sub2api 完整导出
- sub2api 单账号对象
- 通用 OAuth JSON
- ChatGPT web session 草稿
- `.env` / 环境变量
- OpenAI-compatible JSON
- LiteLLM YAML
- One API / New API 通道草稿
- Cherry Studio 配置草稿
- Chatbox 配置草稿
- LobeChat 配置草稿
- cURL Bearer
- VSCode REST Client `.http`
- 格式识别报告

## 关键限制

- ChatGPT web session 页面通常没有真正的 OAuth `refresh_token`，所以转换出来不能保证自动续期。
- `sessionToken` 不能等价替代 `refresh_token`。
- 是否绑定手机不能从 session JSON 稳定判断；MFA/风控/工作区限制可能导致 Codex 校验或续期失败。
- Codex 官方 `auth.json` 通常代表一个当前登录身份，所以单个 Codex auth 默认取第一个 OAuth；多账号请用“Codex auth 批量数组”或 ZIP 里的拆分文件。

## 测试

```powershell
node .\test\smoke.js
```

当前测试覆盖：

- 目录内原有 4 个 JSON 样例
- 混合多账号数组样例
- 批量输出
- 识别报告
- 平台模板
- 规则映射
