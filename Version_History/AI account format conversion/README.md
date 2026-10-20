# AI 账号格式转换器

这是独立的本地静态工具，用于识别账号数据并转换为不同客户端或代理平台的配置格式。打开本目录的 `index.html` 即可使用，不需要后端或安装依赖；移动整个目录后仍可运行。所属便携项目的使用说明见 [Codex Portable](../../README.md)。

## 使用

1. 用浏览器打开 `index.html`，粘贴文本、选择文件或拖入文件。
2. 查看识别到的账号、缺失字段和有效期提示；需要时启用规则映射或字段补全。
3. 选择输出格式，复制、下载单个结果，或点击“下载ZIP”保存批量结果。
4. 使用后清空输入并关闭页面，妥善保管剪贴板和下载文件。

工具业务代码不发送网络请求，也不使用 localStorage、sessionStorage、IndexedDB、Service Worker 或 Cache API。转换结果在内存中生成；主动复制会写入剪贴板，主动下载会交给浏览器保存。下载位置由浏览器决定，需要留在便携包内时，请选择包内工作目录。

## 输入与输出

| 输入 | 支持的形式 |
| --- | --- |
| ChatGPT session / Codex auth | web session JSON、含 `tokens` 的 `auth.json` |
| OAuth / API Key | 通用 token JSON、`sk-...` / `sk-proj-...`、`.env` |
| 代理配置 | `base_url + api_key`、Bearer Header、Cookie/Header 文本 |
| sub2api | 单账号对象或 `{ accounts: [...] }` |
| 多账号 | 纯数组、`data` / `items` / `tokens` 包装数组；可混合以上格式 |

输出包括 Codex auth、OAuth、sub2api、`.env`、OpenAI-compatible JSON、LiteLLM YAML、One API / New API、Cherry Studio、Chatbox、LobeChat、cURL、VSCode REST Client `.http` 及识别报告。平台模板属于配置草稿，需按目标软件版本核对字段。

单个 Codex auth 默认选择第一个 OAuth 账号；多账号使用批量数组、文件包 JSON 或 ZIP。ZIP 中 `outputs/` 保存各格式结果，账号子目录保存拆分文件；ZIP 在浏览器内存生成，不创建工具临时文件。

## 辅助功能

| 功能 | 作用与限制 |
| --- | --- |
| 识别报告 | 展示账号类型、身份字段、token 是否存在、有效期及重复提示；评分只基于输入字段，不验证服务端可用性 |
| JWT 解码 | 查看 token payload；只解码、不验签，不证明 token 真实或仍然有效 |
| 规则编辑器 | 将特殊字段名映射到标准名，例如 `{"token":"access_token","mail":"email"}`；仅适用于可解析 JSON |
| 字段补全 | 修改 name、email、account_id、user_id、base_url、plan 后重新生成输出 |
| 加密账号库 | 用密码导出/导入 vault 文件，使用 PBKDF2-SHA256（150000 次）和 AES-GCM；依赖浏览器 Web Crypto，不自动保存 |
| 离线自检 | 展示工具的网络/存储设计说明；不是动态网络监测或对浏览器扩展的检查 |

## 凭据与兼容限制

- **普通输出的“预览脱敏”不改变复制或下载内容，也不覆盖 JWT 面板。** JWT 面板会显示身份等 payload 字段。不要把真实输入、输出、报告、截图或 vault 密码提交到仓库或发送给他人。
- ChatGPT web session 通常没有真正的 OAuth `refresh_token`；格式转换不能生成续期能力，`sessionToken` 也不能替代 `refresh_token`。
- API Key 不能转换为 OAuth 登录。缺失 token、过期、MFA、风控或工作区限制仍可能导致导入/续期失败；本工具不联网验证或刷新账号。
- 自动识别和重复检测属于提示，不应据此删除真实账号。导入 Codex Portable 时遵循主项目的认证流程，不直接覆盖活动凭据。
- 浏览器下载、剪贴板、扩展及系统本身有各自的数据行为；工具离线不等于这些外部组件也没有访问数据。

## 开发与测试

`app/converter.js` 负责识别和转换，`app/app.js` 负责页面、ZIP 与 vault，`app/style.css` 负责样式。修改功能时更正本说明的对应内容，不按轮次不断追加功能清单；所属项目的维护约定见 [开发文档](../../DEVELOPMENT.md)。

在本目录使用包内 Node 执行：

```powershell
& '..\..\tool\node\node.exe' .\test\smoke.js
& '..\..\tool\node\node.exe' .\test\static-audit.js
```

独立使用本子项目时也可通过已准备好的 Node 执行同一测试。当前合成 fixture 为 `test/multi-array-sample.json`，包含四个账号；smoke 检查格式输出、账号数量、报告和规则映射，static audit 检查资源引用、页面元素及指定的网络/存储调用等模式。测试还会读取本目录根下的 `.json`，不要将真实账号文件放在这里作为测试输入。

这些脚本不覆盖浏览器交互、剪贴板权限或 Web Crypto 的实际运行，相关功能修改后需另做浏览器验收。
