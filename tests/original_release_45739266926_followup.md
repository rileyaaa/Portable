# 原始 v0.172.0-portable.1 ZIP：失败项首因复核与定向候选

原始证据不改写：`tests/release_audit_v0.172.0-portable.1-wrapper-corrected.json`；[Windows 45739266926](https://github.com/rileyaaa/Portable/actions/runs/45739266926) completed/failure，记录提交 1c3ecf64174db0f26b295da9104ca9a6de59aac1。原始 9076 个成员精确匹配 Codex/ 包装，缺失/额外/重复均为零，producer 顺序一致。146 PASS_ACTUAL、33 FAIL、157 PROPAGATION_ONLY、150 IDENTITY_ONLY、6 KNOWN_LIMIT、67 NOT_APPLICABLE、2 OBSERVED、1 NOT_REPEATED、13 NOT_RUN、1 BLOCKED_UNVERIFIED。consumer 完成不等于全过。以下覆盖 33 条 FAIL；候选与正式原 ZIP 分开。

| 失败项 | 次数 | 源码与原始日志核对 | 处理/验证边界 |
|---|---:|---|---|
| standalone rg | 3 | PATH 首个实际为 codex-path/rg.exe，后者由 runtime 固定；测试把独立 tool/bin/rg.exe 设为必须 PATH 第一 | 分别绝对路径实测两个工具及 PATH 解析，不调整既定优先级 |
| f2py | 3 | 固定 NumPy f2py2e.get_newer_options 有 (' '.join(iline)).split()，会拆含空格的绝对路径 | 上游参数处理限制；不改 vendor/wheel RECORD，定向用包内工作目录的简单相对文件名验证，绝对空格路径仍不承诺 |
| merge_runs/comment/add_slide/clean | 12 | embedded safe_path 不含 script dir，ModuleNotFoundError office；已有 validator 同类 bootstrap | 四个入口按现有普通路径/文件规则接入精确本包目录，不改 _pth；定向真实文件往返 |
| SSH | 3 | YOLO key 已生成后输出 CP1252 崩溃；normal/maintenance 另有 work/ssh/keys WinError 5（与 0o700 ACL/受限令牌的关联待实测） | 仅修重定向编码；不放宽私钥 ACL、不宣称 normal/maintenance 通过；独立复现普通 Windows 及真实沙箱路径 |
| Android sqlite3 | 3 | 原日志绝对路径汉字变 ??；ANSI 上游路径限制疑似 | 包内 cwd + ASCII 相对名独立试验，不回退宿主或更换二进制 |
| Android etc1tool | 3 | 解码输出缺失，绝对路径 Unicode/参数仍需相对路径定向判明 | 同上，实际图片像素/尺寸回读，不将退出 0 当通过 |
| instruction installer | 3 | CP1252 输出包根 Unicode 崩溃 | 修重定向编码；定向 dry-run 确认无写入 |
| HTTPX CLI | 1 | 固定 httpx 命令明确缺 cli extras；包内库的实际 HTTP consumer 已通过 | 不安装 extras、不冒充 CLI 可用，记录已知可选依赖限制 |
| maintenance policy | 1 | 生成 writable_roots 为包根符合契约，但 protected-audit.txt 实际 PermissionError；不是配置传播成功即可抵消 | 真 Windows sandbox 定向重现，保留保护与批准，不以扩大权限或直接 runner 写入替代 |
| cache cleanup | 1 | 测试准备时 work 不存在，尚未调用清理 | 合成 fixture 创建 work 后定向 preview/cleanup；不得清真用户数据 |

本提交只是源码修正和首因分类，未执行新 Windows 测试，不改变原 ZIP 的状态。
