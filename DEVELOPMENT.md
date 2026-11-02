# 开发与维护记录

## 2026-11-02：十轮审计前止损预检的测试夹具修正（无 AC）

- **发现的确定错误：** 在合成发行包原有 `test_archive_is_reproducible_and_excludes_untracked_private_state` 内，前面已成功调用两次 `build_release` 并通过 CLI 生成第三个 ZIP，因此新增的 `--check` 测试不能断言 `tmp` 不存在；该断言若进入下次完整回归必然误报失败。
- **修复：** 在 `--check` 前拍下已经存在的输出目录清单，成功检查和故意制造未提交修改后的失败检查，都要求目录清单完全不变；保持真实 `--check`、ASCII JSON、干净 Git 与拒绝脏 Git 的正反向验证。仍然只使用原来的 8 个发行包测试方法，十轮审计的 `runtime=21` 计数未改。
- **减少再次浪费：** 在 03 下载 Node/Paramiko 前的维护回归中，附加执行原有 `test_release_package.py` 8 个合成 Git/ZIP 测试；候选阶段完整 Python 回归和十轮审计仍执行该套测试，不删减后续覆盖。顺序合同测试也要求这套早期回归位于下载前。
- **范围：** 仅测试/03 工作流/本开发记录；未执行 Windows 原生 runner、未上传 Node/SSH 或发布 ZIP，仍不将未执行步骤视为通过。

## 2026-11-02：03 后段审查与十轮审计前的 ZIP 输入止损预检（未运行 AC）

- **原因与范围：** 第七次 `03` 在原生启动/搬迁测试失败，十轮审计、正式客户 ZIP、独立写权限 `propose` 仍未实测。继续审查发现现有流程先跑十轮 `release-audit.py --release`，才第一次检查真实候选能否通过 `package-release.py` 的客户输入检验；若 Node/SSH 新文件与 Windows 路径、LFS 水合、浏览器清单或 Codex 身份冲突，十轮审计的费用会白花。
- **补充门禁：** 03 仅在候选 Git 本地试提交成功后、十轮审计开始前执行受信任的 `tool/package-release.py --check`（不生成 ZIP），核对 JSON 中的真实 Git 提交、Codex 版本、正数客户文件数；失败立即阻断。原有完整十轮审计、独立 `--verify`、正式 ZIP 试打包和 SHA-256 校验全部保留。增加维护工作流门禁顺序检查，并在**原有**发行包回归中加入真实 `--check` CLI 正反向样本（干净 Git 提交应通过、有未提交改动必须失败）；未新增测试方法数量，`release-audit` runtime 固定 **21 项**不变。
- **验证边界：** 最终源文件、插入顺序、审计仍是 10 轮、Git LFS 与独立写入、19 项 PowerShell 门禁只做离线静态复核；Windows 包内 Python/PowerShell 及真实 Node 26 + Paramiko 候选尚未在新版本上执行。**无新 Actions、无自动发布、无工具二进制合并。**

## 2026-11-02：03 第七次 Windows 原生搬迁测试失败，先止损并审查（Run 41459805288）

- **实测故障：** [Windows Actions #41459805288](https://github.com/rileyaaa/Codex-Portable/actions/runs/41459805288) 使用 main `ce38b0d3`，通过 actionlint、前置工具维护测试、Node 26.13.0 / Paramiko 5.1.0 候选准备与原生导入、转换器检查、全量 Python / Node 回归及浏览器校验；19 项 Windows PowerShell 阶段中，`test_launcher_smoke.ps1` 的正常模式 BAT / 原生配置检查通过后，在第 95 行将已启动过的合成便携目录重命名时收到 Windows `Access to the path ... is denied`。此轮没有运行十轮审计、真实 ZIP 试打包、可信写入 Job，也没有创建工具候选 PR。
- **根因边界：** 现有测试在子进程退出后立即调用 `Directory.Move`，没有为 Windows 的延迟句柄释放留出有限缓冲。原始日志能证明移动时存在访问拒绝，不能仅凭这条错误就断言 Codex 主程序存在持久句柄泄漏，也不能断言只是短暂扫描占用；后续必须由原生 Windows 测试区分。
- **本次修改：** 仅调整维护测试和 03 门禁顺序。合成目录搬迁保留真实 `Directory.Move`，只对 Windows access denied / sharing / lock（错误码 5、32、33）采用最多 20 秒、间隔 250 毫秒的有限重试；路径消失、目标已存在、其它错误或持续锁定一律拒绝通过。03 现在在下载 Node/Paramiko 之前，用当前受信任便携运行时执行一次完整 `test_launcher_smoke.ps1`，先发现可复现的启动/搬迁故障；准备候选后仍把该测试作为 19 项 PowerShell 回归第一项，再次验证升级后的真实环境。增加原有工具维护 Python 测试的顺序与失败门禁断言。重复测试会增加一次启动开销，但失败时可省下候选下载与后续长回归。未删除任何门禁、未改生产启动器、未扩大更新来源。
- **验证边界：** 源码审查已核对 ten-round release-audit 的 unit/tcp/property/runtime 分组计数 64/19/6/21，与现有 unittest 测试方法一致；已核对实际 ZIP 的文件身份、工件摘要和源检出验证路径、双 Job 差异摘要比对、LFS 指针及远端对象上传语句、候选 PR 权限回退逻辑。修改在独立维护分支，新增预检及回归次序也经过最终源文件静态检查；因当前环境无完整包内 Windows 可执行文件和 PowerShell 5.1，**尚未在 Windows Runner 执行修复后的实际测试**。完整十轮审计、ZIP、LFS 远端上传和 propose Job 仍无本轮成功证据；不能将源码审查称为 Windows 通过，不自动重跑 AC，不合并未经完整验证的 Node / Paramiko 工件，不创建 Release。

## 2026-11-02：第六次 03 运行在下载前自检失败（Run 41450908392）

- **错误实况：** [Windows Actions #41450908392](https://github.com/rileyaaa/Codex-Portable/actions/runs/41450908392) 在 main `31c7ad44` 完成固定 SHA actionlint、包内 Windows 测试状态准备后，下载前执行工具维护预检：`Ran 32 tests`、31 项通过，`test_all_maintainer_text_io_is_explicit_utf8` 一项失败；原因是上一提交新增 `tests/test_tool_updates.py:303` 使用合法的 `encoding='utf-8-sig'` 读取有 BOM 的转换器 JS，但编码 AST 检查器只识别 `'utf-8'`，误报为隐式系统编码。**此轮没有下载 Node/Paramiko，没有执行 Windows 候选、完整回归/发布审计、ZIP，也没有生成候选 PR**。
- **修复办法：** 将检查器提取为单独的 `explicit_utf8_text_io`，只认可显式的 `utf-8` 或 `utf-8-sig`（支持 read_text 的 positional / keyword 和 write_text 的 positional / keyword），继续拒绝 `cp1252`、`latin-1`、默认编码和 `encoding=None`。增加独立正反向测试确保检查器不会再次把合法的 BOM 感知 UTF-8 当成错误，也不允许任何未明确编码的文本 I/O；维持第一次发现 Windows CP1252 时设立的安全门禁，不直接删除测试。
- **离线可证据边界：** 使用本地 Python AST 和 unittest 独立执行这段编码检查器的正反向测试，通过；检查仓库三个维护脚本内的 `read_text/write_text` 的编码声明和现有 03 检查门槛。由于仓库为私有且当前运行环境无法取得全部包内 Windows 原生组件，未在本地完成包含真实 Python 3.14/Node26 的整套 03 运行。**下一次手动 AC 才能证明完整版；用户未批准重跑前不运行 AC，也不会直接合并任何失败工具候选**。

## 2026-11-02：03 第五次 Windows 运行及 Node 26 转换器断言修复（Run 41430341405）

- **实测状态：** 手动 `03` 的 [Run #41430341405](https://github.com/rileyaaa/Codex-Portable/actions/runs/41430341405) 在 main `05977f33` 执行 `prepare/all/create_pr=true`，前置 31 项维护回归、官方 Node 26.13.0 候选、SHA-256 + LFS 指针、Paramiko 5.1.0 Windows 原生导入、包内 Corepack 0.35.0 及 Node/npm 版本探测均通过。其后完整 **348 项 Python 测试全数通过**，两套 Node 测试各 10 项全数通过；随后 `Version_History/AI account format conversion/test/smoke.js` 第 181 行出现 `AssertionError [ERR_ASSERTION]`：Node 26 的 `util.parseEnv` 空映射为 null-prototype 对象，而旧测试错误地与普通 `{}` 严格深比较。后续 `static-audit.js`、19 项 PowerShell、十轮 Windows 审计、真实 ZIP、独立写入和候选 PR **没有执行**，因此不存在可审查或合并的工具更新 PR。
- **兼容与安全修复：** 转换器测试不再要求 `parseEnv` 返回映射的内部原型；保留空变量的安全要求，验证返回非 null 对象且 `Reflect.ownKeys(parsed)` 严格为空（连不可枚举/Symbol 属性也不能出现）。生产转换器 `app/converter.js` 未改，不能以测试兼容为名放松输入或密钥安全约束。新增 03 维护合同测试以防恢复原型敏感断言。
- **动作顺序优化：** 03 现在把完整 `smoke.js` 与 `static-audit.js` 两项转换器测试放在已下载并验证候选 Node 后、耗时较长的全量 Python 回归之前；不是删除测试，而是早发现新版 Node 的运行时不兼容。19 项 Windows PowerShell、release-audit 的 10 轮随机测试、正式 ZIP 试打包、独立可信写权限复现及 Git LFS 上传门禁均保留。
- **离线验证与边界：** 已检查 `smoke.js` 整体 JavaScript 语法及空普通对象、空 null-prototype 对象与异常非空对象的自有属性断言行为，检查 03 顺序和测试保护；实际 Windows Node 26 转换器、`static-audit.js`、19 项 PowerShell、十轮审计、ZIP 与新候选 PR 仍须下次手动 Windows AC 验收。本轮不自动启动 AC、不把未通过的工具二进制合并 main、不发布 Release。
## 2026-11-02：03 第四次失败后再次全面预审（Node 26 Corepack、转换器、SSH 运行目录）

- **检视范围：** 以 `main` 的 `d74ce851` 为基线，审查 `03-update-tools.yml` 的只读验证、独立写入、LFS 对象上传、候选 PR、真实 ZIP/十轮审计和 01/02 正式发布测试覆盖。此前 [Run #41425693314](https://github.com/rileyaaa/Codex-Portable/actions/runs/41425693314) 已经通过 Windows Node LFS 候选暂存、SSH 原生导入，但因 2 项默认编码错误和 1 项 Git LFS 反向夹具错误中止了 341 项 Python 回归；本节不是新的 Windows 通过记录。
- **防止升级静默删工具：** Node.js 官方从 25 起不再随包发行 Corepack（参见 `https://github.com/nodejs/node/blob/main/doc/contributing/distribution.md`）。本项目当前确实已安装 Corepack **0.35.0**，其 `engines.node` 支持 `>=26.0.0`；原升级程序整个替换 `tool/node` 会误删 `corepack`、`corepack.cmd` 与 `node_modules/corepack`。现按原始字节保留并检查普通文件、单链接、安全路径和体积上限；Node 26 原生版本验证中额外用**新的包内 node.exe**执行保留 Corepack 的 `--version`，确认不调用宿主 Node 或下载外部依赖。`tool/installed-tools.json` 和工具表新增 Corepack 项，成功升级后继续记录其真实版本；不得把“沿用现有组件”说成“升级了 Corepack”。
- **补足现有测试门禁：** 对照 02 正式发布与 01 稳定版写入流程，03 原先遗漏 `Version_History/AI account format conversion/test/smoke.js` 和 `static-audit.js`。现在加入完整 Node 回归之后、Windows PowerShell 前的相同转换器专项，原 Python 全套、Playwright、19 项 PS5.1（原 18 项加持久化）、十轮随机动态审计和 ZIP 试打包不减少。
- **统一 SSH 运行用户目录：** `run-codex.ps1` 实际将 `HOME`/`USERPROFILE` 指向包根 `home-runtime`，因此默认 `~/.ssh/known_hosts`、SSH 密钥目录应位于 `home-runtime/.ssh`，而不是之前文档误写的 `home/.ssh`。同步修正 `prepare-ssh.py` 安装时的隔离用户目录、README 和工具说明；用户脚本本身仍不能靠环境变量获得绝对的 OS 级写入沙箱。
- **离线验证及仍需 Windows 验收的部分：** 使用本地 Python 的严格 `ResourceWarning` 模式完成 **31 项工具维护 unittest**，新增原 Node ZIP 无 Corepack 时原包的保留、链接/重解析拒绝、真实 Node/Corepack CLI 结果不符时阻断、npm/Corepack/Node 台账同步、转换器测试覆盖和 SSH HOME 验证。AST/YAML 基础检查、两 Job LFS/OID/二进制 diff 静态门禁以及 Corepack 54 个普通文件无链接的 Git 清单复核通过。**没有运行新的 Actions、没有真正更新 main 中 Node 24.16.0/Paramiko、没有创建 Release。** Node 26 和 Corepack 的真实 Windows 执行、19 项 PowerShell、十轮审计、完整 ZIP 以及写入 Job 的 Git LFS 推送必须通过下次授权的完整 AC，不能以本地模拟替代。
## 2026-11-02：03 工具升级第 4 次 Windows 运行的编码与 LFS 测试修复（Run 41425693314）

**真实日志：** [Windows Actions #41425693314](https://github.com/rileyaaa/Codex-Portable/actions/runs/41425693314)，来源 main `a11840fa`，已通过固定 actionlint、包内环境准备、官方 Node/Paramiko 下载与候选暂存、`NODE_LFS_INDEX=PASS`、原生 SSH 导入 `SSH_NATIVE_IMPORT=PASS 5.1.0` 和 Windows 工具版本探测。第 8 步运行 Python 全量回归时实际执行 **341 项，338 项通过、2 项报错、1 项失败**；后续 Node/npm、19 项 PowerShell、十轮审计、ZIP、候选 PR 都没有执行，不得记为已通过。

- **两个 Windows 编码错误：** `tests/test_tool_updates.py` 的工作流源码与中文工具说明读取采用默认 `Path.read_text()`，Windows CP1252 上产生 `UnicodeDecodeError`。统一为 `encoding='utf-8'`；本文件所有文本读写和 `tool/update-tools.py` 对 Android source.properties 的读取也明确编码。新增 AST 回归检查 `tests/test_tool_updates.py`、`tool/update-tools.py`、`tool/prepare-ssh.py` 里所有 `Path.read_text/write_text` 必须明确 UTF-8，以防类似问题再次进入 Windows 门禁。
- **一个 LFS 反向测试失效：** 原测试试图用 `git hash-object -w tool/node/node.exe` 构造没有 LFS 指针的原始暂存 Blob。在配置了 Git LFS clean 的 Windows Git 上，这种路径式哈希可能被 LFS 过滤器转换成有效指针，因此 `assertRaises(ValueError)` 没有触发；这是测试夹具没有真正制造被篡改对象，不是已验证的业务校验漏洞。现在改成 `git hash-object -w --stdin` 以原始 EXE 字节写入 Git 对象、读取 `cat-file` 与暂存 Blob 确认确实为原始 `MZ` 文件，再要求 `verify_node_lfs_index` 拒绝。夹具也安装可控的模拟 LFS clean 过滤器，复现“路径哈希可能被过滤”的场景。
- **减少浪费 AC 时间：** 03 `prepare` 的隔离状态准备完毕后，新增 **下载前工具维护回归**，Windows Python 先执行 `python -m unittest discover -s tests -p test_tool_updates.py -v`，失败即停止，不先下载大型 Node/SSH wheel；原安装后的完整 341+ Python/Node、19 项 PS5.1、10 轮动态审计和真实 ZIP 门禁不删减。
- **此次离线验证与边界：** 26 项定向工具回归在本地全部通过；额外以 Python `EncodingWarning/ResourceWarning` 为错误、模拟 Windows CP1252 默认文本编码、模拟 Git `core.autocrlf=true`、模拟 Git LFS clean 过滤器多组复测通过；三个 Python 脚本 AST 和 YAML 基本结构检查通过。**没有再运行 AC，也未更新 main 中 Node 24.16.0 或正式安装 Paramiko、未生成新 Release。** Windows 3.14、Node 26/npm、19 项 PowerShell、十轮审计、真实 ZIP 与可信写入 PR 仍须下次真正的手动 Windows 流程验收。
## 2026-11-02：03 工具更新第三次失败后的系统性修复（Run 41422353149）

**故障证据：** 手动运行 https://github.com/rileyaaa/Codex-Portable/actions/runs/41422353149 在 Windows 候选准备第 6 步失败：Node 26.13.0 的 node.exe 超过 GitHub 普通 Git 100 MB 限额。先前固定 actionlint、版本盘点通过，但 Windows 全量 Python/Node、PowerShell、10 轮动态审计、真实 ZIP 和 PR 尚未运行，不能算通过。第一次运行 #41419650909 已验证 Paramiko 5.1.0 的原生 wheel 安装和导入，但其后失败，仍未随包发布。

- **完整 LFS 交付：** 只在 Node 更新候选工作树添加精确的 .gitattributes LFS 规则；只读与可信写入 Job 均验证 Git 索引中只有规范 Node LFS 指针，且指针 SHA256、文件大小与原始 exe 完全相等；候选 diff SHA256 覆盖 LFS 规则。可信写入 Job 重建固定来源和散列，先通过 git lfs push --object-id 只上传本次 Node 对象，再推候选分支；绝不自动合并 main、发布 Release。Node LFS 对象会占用账户存储与带宽，区别于 Actions 分钟。
- **预先修复后续测试问题：** 原工具回归固定断言 Paramiko 不存在，现成功安装时改为验证实际发行元数据；03 原遗漏正式 Release 的 test_extension_migration.ps1，现覆盖原 18 项并额外保留 test_extension_persistence.ps1，合计 19 项；PowerShell 5.1 的摘要/OID 分组改用明确正则匹配对象。若仓库不允许 Actions 自动创建 PR，完整验证后的分支依旧可由 GitHub Connector 直接创建 PR，不重跑 Actions。
- **离线验证：** 24 项工具维护 unittest 通过（ResourceWarning 严格模式）、三个 Python 文件 AST 解析与 03 YAML 结构检查通过；通过合成 Git 索引和模拟 LFS clean filter 验证指针规范、文件篡改、属性越界拒绝，以及两个独立 Job 生成相同 diff SHA256。此测试不能代替真实 Windows 的 Node 26/Paramiko 加载、19 项 PowerShell、10 轮审计、ZIP 或 LFS 远端推送。此次不运行新 AC。
- **原生版本盘点：** Run #41422353149 在任何候选写入前测得 Node 24.16.0、7-Zip 26.01、ripgrep 15.1.0、fd 10.4.2、jq 1.8.1 和 ADB 37.0.1；仅同步基线台账，不把 Node 26 或 Paramiko 候选标成现有安装成果。lastSuccessfulToolUpdate 继续保留 null。
## 2026-11-02：03 工具更新首次 Windows 运行故障修复（Run 41419650909）

- **现场证据与范围：** 首次手动 `03-update-tools.yml` 在 `main` 的 `cefd304a` 执行 `mode=prepare`、`group=all`、`create_pr=true`，运行日志见 [GitHub Actions #41419650909](https://github.com/rileyaaa/Codex-Portable/actions/runs/41419650909)。固定 actionlint、隔离目录、只读工具盘点均通过；Windows x64 成功下载和准备固定 Node 26.13.0 以及 Paramiko 5.1.0 和六项原生依赖，日志有 `SSH_IMPORT_NATIVE=PASS`、`SSH_INSTALLED=PASS`、`TOOL_CANDIDATE_STAGED=PASS`。但在阶段 6 执行全量 `git diff --cached --check` 时，因为官方 wheel 自带 LICENSE、WHEEL 元数据和 vendored YAML 文件中原有行尾空格/尾端空行而失败，错误为 `Malformed tool candidate diff`；**阶段 7 之后的完整 Python/Node/PowerShell 回归、十轮动态审计、客户 ZIP 和候选 PR 都尚未执行，不能列为通过**。
- **针对性修复：** `tool/update-tools.py lint-staged` 先验证 Git 暂存差异只包含已审核的工具归属路径，再只对**第一方生成台账、文档和 SSH wheel lock**执行 Git 空白检查；由官方 ZIP/sha256 和 PyPI wheel hash 校验过的第三方源文件继续按原始字节打包，不擅自去除上游许可证空白。03 的只读验证 Job 与独立写权限 Job **两个位置**同步改用相同检查，仍保留随后完整候选 Git 二进制差异 SHA-256 相等验证。额外在 Stage 时拒绝超出 GitHub 普通 Git Blob 100 MB 限额的 Node.exe 候选，避免完整十轮验完才发现无法推送。
- **一起发现的潜在回归：** `tests/test_maintenance_workflows.py` 的新增 03 手动触发断言误写成字面量 `\\n`，本来会在后续完整 Python 回归中失败；修正为实际换行匹配。新增离线回归复现原始官方 wheel 格式警告、验证例外仅限已核对第三方路径；向本地生成说明注入行尾空格或将无关工具脚本加入暂存仍必须拒绝。
- **此次验证边界：** 本地 18 项工具维护定向 unittest 全部通过、两个 Python 文件 AST 解析成功、03 YAML 基本解析通过、两个 Job 均保留差异身份复验及十轮审计入口；**没有再次启动 Actions，也没有更新/合并候选 Node 或 Paramiko 工件、没有发布 Release**。下一次人工运行仍须重新执行完整 Windows 门禁；不能把 2026-11-02 的阶段 6 中途通过视为全部通过。

## 2026-11-02：工具候选离线加固与一次性 Windows 验证设计（未运行 AC）

- **Node 便携入口保护：** 本地审查发现直接以官方 Node ZIP 覆盖整个 tool/node，会删除现有 portable-npm.js 和 npm/npx 的 CMD、PowerShell 入口。现已修复为保留七个已审查的入口，同时跳过上游 install_tools.bat 系统安装器，禁止恢复宿主 npm 搜索或系统安装行为。
- **本批拟更新的真实候选：** tool/tool-update-plan.json 固定 Node.js 26.13.0 LTS Windows x64 官方 ZIP 一项；核对官方 URL、版本、ZIP SHA-256，并要求在 Windows 准备阶段取得官方 SHASUMS256.txt 再独立交叉验证；原有 Node 真正版本待 Windows 原生探测，候选不代表已安装。其他未审核的工具不盲升。
- **集中门禁：** 03-update-tools.yml 的 prepare 一次性执行 Paramiko 原生导入、完整 Python/Node 回归、Chromium 校验、18 项 Windows PowerShell 5.1 回归、十轮随机种子 Windows 发布审计及真实 ZIP 试打包。只读 Job 验证完整候选差异 SHA；独立写权限 Job 重建同一差异才可创建 PR，不会自动合并 main 或创建 Release。
- **离线复核状态：** 本地通过 16 个定向合成回归（路径遍历、符号链接、归属目标、官方摘要不符、Node 自定义入口保持、版本台账同步、异常 Git 暂存范围）、Python 语法及 YAML 基本解析。不能将其等同于 Windows 原生测试、全套项目回归或任何已经运行的 GitHub Actions；本次仍未触发 AC。
## 2026-11-02：工具便携维护与 SSH 支持（候选源码，未运行 AC）

**范围与状态：** 按用户授权，审查全部现有说明和当日提交，再在独立维护分支准备 Python SSH 组件、第三个手动工具更新入口、版本台账和离线边界回归。此阶段只提交维护代码；**没有触发 GitHub Actions、没有下载或安装 Windows Paramiko 原生 wheel、没有升级现有 Node/ADB/Chromium/CLI 二进制，也没有生成正式 Release**。后续只在用户单独批准 AC 后执行 Windows 真实验证和候选 PR；PR 仍需人工复核合并。

- **当日历史提交复核：** `bebb67a` 修正 PS5.1 原生 `python -c` 参数中的引号丢失，避免候选 Git diff 摘要核对失效；`c052eb1` 恢复遭正则替换误伤的完整发布 YAML；`5e9fbe9` 加入稳定版写入前 18 项 Windows 回归、固定 SHA actionlint、严格发行标签和更新的十轮测试计数；`badd0cb` 将两个原生 Codex 入口最终命名为 `01-upgrade-codex-runtime.yml`、`02-verify-and-publish-portable.yml` 并同步引用。上述均属于先前代码历史，本节不冒充重新运行验收。
- **SSH 组件：** `tool/python-ssh-packages.in.txt` 固定 Paramiko 5.1.0 及 bcrypt、cryptography、Invoke、PyNaCl、cffi、pycparser 的 Windows x64 / CPython 3.14 候选版本；`tool/prepare-ssh.py` 仅用包内 Python/pip，官方 wheel-only 解析、真实 SHA-256 lock、限制解压、原生导入及同包临时目录。库放 `tool/python/ssh-packages`，由 `tool/python/Lib/site-packages/codex_portable_ssh.pth` 以相对路径挂载，不改原 42 项基础锁；SSH host key/凭据应留包内 `home/.ssh`，工作文件留 `work`，均不进发行包或 Git。安装工具的约束不等于对任意用户 SSH 脚本输出提供操作系统级绝对沙箱。
- **第三个手动工作流：** `.github/workflows/03-update-tools.yml` 仅支持 `workflow_dispatch`；`check` 为默认只读盘点，`prepare` 用包内 Windows Python 构建完整候选并回归验证；`create_pr=false` 为默认，仅明确打开后才由独立写权限 Job 重建并核对同一暂存 diff SHA-256，建立候选 PR，**绝不自动合并 main 或创建 Release**。Python SSH 可作为首批候选；Node/ADB/bin 走 `tool/tool-update-plan.json` 中人工审核过的确切来源、版本、SHA-256 和映射（当前计划为空），Playwright/Chromium 与默认 Python 全套升级仅盘点，待专用适配。
- **版本台账：** `tool/installed-tools.json` 是实际随包组件版本的机器来源；工具更新成功后，同步生成 `tool/工具更新说明.md` 内受控版本表格，失败不改写。当前未知的独立 EXE 精确版本标记“待 Windows 原生核对”，Paramiko 标记“尚未随包安装”，不把候选版本误报为成品。
- **验证与遗留：** 纯 Python 静态编译、YAML 结构和合成路径/哈希检查可在不调用 AC 的本地环境开展；`tool/python/ssh-packages` 真实 Windows wheel 安装、源 lock、Paramiko import、PS5.1/原生 ZIP、全量 10 轮审计及用户 Win11 实际运行尚待独立授权验收。生成 PR 后仍应先检查完整差异、来源摘要、许可证、Git 大文件及发行体积，再决定合并和正式发行。

## 2026-11-02：维护代码二次回归修复

- **01 稳定版写入前完整 Windows 复核：** 在只读 Job 完成官方 SHA 和 Git LFS 候选差异验证后，先建立不推送的本地候选提交，准备与 02 相同的隔离环境和原生模型目录，再逐项执行完全一致的 18 项 PowerShell 5.1 回归（每项沿用 02 的超时与失败阻断）、Python/Node 检查、十轮动态审计和真实 ZIP 试打包。主分支写权限仍只在独立 Commit Job；Alpha/Beta/RC 仍只允许只读干运行。两个工作流的 Windows Checkout 和 Actionlint 均使用固定审核版本。
- **YAML 静态语法门禁：** 两个正式入口在执行升级/发布前都从 `rhysd/actionlint` 下载固定 `v1.7.12` Windows x64 包，校验该归档的完整 SHA-256，再检查两份正式工作流。失败阻断，不新增常驻 YAML。
- **正式包标签身份：** `tool/package-release.py` 只接受与 `tool/runtime-manifest.json` 三段稳定版本完全相同的 `v<版本>-portable.<正整数修订号>`，省略标签时默认 `<版本>` 对应 `.1`；任何错误版本标签均拒绝生成客户 ZIP，补齐正反向合成测试。
- **十轮审计测试数量更新：** 新增对错误正式版本标签的负向打包测试，`test_release_package.py` 测试数量增加一项；将 runtime 组预期从 20 调整为 21，每轮 110 项、十轮合计 1,100 项动态执行，保留数量不符即拒绝发布的原则。
- **验证边界：** 本轮维护测试均使用测试分支和合成数据；若未真正执行 01 写入和 02 发布 Job，不得将其列为已实测通过。原生 0.166.0 二进制与正式 Release 保持不变。

## 2026-11-02：长期升级维护加固（Node 24、ZIP 试打包、恢复路径）

- GitHub 官方 `actions/checkout` 更新为固定完整 SHA 的 `v7.0.1`（声明 `node24`），仍只使用手动 `01-upgrade-codex-runtime.yml` 和 `02-verify-and-publish-portable.yml` 两个正式入口。保留 `lfs: true` 和 `persist-credentials: false`。
- 01 仅在正式稳定版明确设置 `commit_changes=true` 时，额外于只读 Runner 创建**不推送**的本地候选提交，运行完整 Python 回归、Node/浏览器测试、十轮 Windows 发布审计及真实客户 ZIP 试打包；全部成功之后独立写权限 Job 才核对官方发布、固定日期、候选 Git 差异 SHA-256 和 LFS 并快进提交。Alpha/Beta/RC 始终不得提交。稳定版提交后在 Job Summary 记录原始 SHA 和新 SHA；若随后 02 失败，人工确认远端 HEAD 未改变及无关联 Release 后，使用正常 `git revert` 生成恢复提交，不强制重置、不删除仍需的 LFS 对象。
- 02 不论 `publish_release` 是否开启，都先在只读 Job 真正生成 ZIP、校验 manifest 与 SHA256SUMS 并清理临时文件；明确开启发布时，独立写权限 Job 以同一原始来源 SHA 重新生成 ZIP，并核对与先前验证 ZIP 的**完整 SHA-256 一致**，再进行 draft 上传、下载回读和公开。失败后若已有草稿，保留草稿供人工检查并输出恢复提示，不盲目覆盖或删除。
- 01 输出新版本五个 LFS 程序的总大小及容量提醒；这是每次升级候选的文件体积，不是账户真实存储/带宽额度。官方归档文件名或 JSON schema 变化继续采用拒绝未知内容的策略，并在失败原因中列出待人工适配的变化。
- 这些修改不会升级仓库现有 `0.166.0` 二进制或创建正式 Release。Windows 全量测试需要另行在 Actions 上实测；不能把静态检查或只读试打包说成真实账号、在线 Agent 与终端实机验收。

## 2026-11-02：维护 Actions 简化为两个手动入口、隔离写权限

- 工作流只保留 `01-upgrade-codex-runtime.yml` 与 `02-verify-and-publish-portable.yml`。独立 `02-check-compatibility.yml` 已移除，但兼容性审核脚本 `.github/maintenance/02-compatibility.py` 保留，01 和 Release 继续调用。与升级、发布无关的临时浏览器下载工作流 `download-browser.yml` 已删除；包内固定浏览器及其清单/校验器不变。
- 01 只读 Job 下载并运行官方候选 EXE，检验来源、Windows 配置与 LFS；另由写权限 Job 在不执行新 EXE 的前提下重新取得官方文件、核对稳定版身份、候选差异 SHA-256 与 LFS，才可快进提交。候选维护记录日期在两 Job 中固定，避免跨 UTC 日期导致差异漂移。
- Release 统一执行完整兼容检查、Python/Node/PowerShell 回归和十轮审计，不再依赖先前独立 02 的运行记录。无论是否发布，验证 Job 均需执行真实 ZIP 试打包并删除临时包；只有验证 Job 成功、来源 SHA 与 `main` 相同且人工设置 `publish_release=true` 时，独立写权限 Job 才以一致的 ZIP SHA 重新打包、回读校验三个附件并发布。两个工作流的发布/提交开关均默认关闭；`package_hotfix`、`windows_fixes` 旧选项已清除。
- 不启用 push、定时或自动串联入口，仍需人工分别决定是否提交稳定源码及是否正式发布。此次只变更维护代码、测试和文档，不改动 0.166.0 EXE、Git LFS 固定摘要或现有正式 Release。静态检查不替代新结构上线后的 GitHub Actions 实测。

## 2026-11-02：01 支持官方完整 Release URL 与预发布版隔离测试

- 保留 2026-11-02 修复后的源码基线 `67c31ec06f351105722ec7d4dffa02932562106d`，只修改工作流、维护代码、测试和说明，不永久更新现有 0.166.0 Windows EXE、LFS 指针或正式 Release。
- 01 输入改为 `release_url`：必须是 `https://github.com/openai/codex/releases/tag/rust-v<版本>` 完整官方链接，支持示例 `rust-v0.167.0-alpha.3`。拒绝非官方域名、任意下载地址、查询参数、恶意 URL 和无效版本；同时核对 GitHub Release 的 `tag_name`、`draft`、`prerelease`、官方 SHA-256、架构和 canonical 文件白名单。
- 为防止 Alpha 误入正式包，`commit_changes` 默认关闭；Alpha/Beta/RC 即使手动打开提交也提前拒绝。正式稳定版经完整 01 验证后才允许显式提交；03 的正式发布标签仍只接受三段稳定版本号。
- 版本比较支持相同主版本下 `alpha → beta → rc → stable` 的自然升级顺序；02 的源码变量检查也能识别预发布候选字符串。新合成测试覆盖非法 URL、预发布标签状态不符、伪造摘要、Alpha 升级后再升稳定版以及原有升级回归。
- Windows 实跑发现原升级脚本只识别 LF 的 `DEVELOPMENT.md` 标题定位，在 Windows `core.autocrlf` 生成 CRLF 后会失败；现按实际换行格式插入维护记录，并新增 CRLF 合成回归，继续阻断混杂换行。
- 本次仅对原始基线进行增量代码修复。Windows 运行时下载、原生 Agent/账号连接、客户终端兼容性必须以真实 Actions 与人工验收为准。

## 2026-11-02：01/02/03 手动升级工作流复审与补强

按照人工顺序 `01 → 02 → 03` 复审三个手动 GitHub Actions，发现并修复初版中的实际缺陷。本次不升级 Codex 官方二进制，也不创建或修改现有 Release。

- **01 更新运行组件：** 初版对两项沙箱助手的「重复文件一致」比较实际上比较了同一源路径，无法证明任何事情；已改为明确记录从官方资源目录映射至包根的规则，并对 canonical 归档实行严格文件白名单。Git LFS 预提交检查现要求暂存指针的 SHA-256、文件大小、工作树实际 EXE 摘要及运行清单完全一致。保留官方正式版、架构、来源及摘要校验，不打包语音、独立执行服务器或未经审查的新增组件。
- **02 变量和兼容性检查：** 修复 01 干净检出通常不存在 `tmp/`，导致复用 02 原生检查时直接失败的问题，改为临时创建受控目录并在使用后清理；原先只统计带双引号的 43 个变量，遗漏使用表达式赋值的 `CODEX_INSTALL_DIR` 和 `CODEX_PYTHON`，现在覆盖当前全部 **45 项**声明，并单独核对计算路径及代码引用。额外验证启动器对远程服务子命令的阻断、语音/听写关闭、隔离环境下的原生 `--no-daemon`、`resume`、`fork` 参数和真实配置解析；不读取用户凭据或执行在线模型调用。
- **03 Bug 检查和发布：** 原有全量 Windows 检查、10 轮回归及三个附件回读继续保留。正式发布必须来自 `main`，且来源提交 SHA 与最近一次成功的**手动 02** 运行一致；创建草稿前、最终公开前再次核对远端 `main` SHA，避免测试期间分支变化仍发布旧源码。
- **新增可重复合成测试：** 使用合成 Windows PE、官方归档和独立哈希的离线测试检查文件白名单、语音和远程服务排除、篡改摘要拒绝、两次连续版本升级、模式和版本固定值同步、遗漏动态变量时阻断；01 和 02 的正式工作流都会执行，03 全量测试也会覆盖。合成测试不代替真实 Windows Actions、真实账号、在线 Agent、终端绘制或用户实测。

**本次验证边界：** 已核对 GitHub 上各文件的基准版本、45 项环境变量、五个原生运行组件的固定布局及官方 0.166.0 CLI 对相关帮助参数的源码定义；新增的合成测试尚未在 Windows Actions 实际执行。01 仅允许高于现有版本的官方稳定版提交；更高的官方预发布版只允许不提交的测试；今后有新稳定版本时仍须由人工分别执行 01、02、03，并以真实 Actions 日志和用户实用反馈确认。

## 2026-10-31：按使用者要求重新打包 0.166.0 为 Portable r1

原 `v0.166.0-portable.1` 的 Release 与标签均已不存在；原 r2 仍已发布，但尚未经过使用者实际验收。本次将前一批本地独立执行器精简后的源码重新命名为 `v0.166.0-portable.1`，并保持 `0.166.0` 官方主客户端、Host 与沙箱组件不变。r1 必须通过新的完整 Windows 工作流和十轮随机测试，客户 ZIP 及三个附件回读成功后才能成为正式版；**只有新 r1 验证成功，才允许删除旧 r2 Release 及其标签**。不要先删掉唯一已发布的 0.166.0 包，也不修改 0.164.0 稳定发行版。

现有 GitHub Connector 无法直接调用 workflow_dispatch 或删除 Release。为执行此项明确授权的重新打包和删旧发布任务，允许本次使用一个严格匹配提交信息和专用文件路径的单次 push 引导器；它只调度既有 `02-verify-and-publish-portable.yml` 的 `workflow_dispatch` 全量门禁，等待成功并回读后才删除旧 r2。成功后必须从 main 删除临时引导工作流，现有正式发布工作流仍仅允许手动调度。若失败，保留 r2 并报告真实失败状态，不绕过全量门禁或重用旧测试结果。

## 2026-10-30：可选独立执行器精简（0.166.0 便携修订）

仅面向本地 Windows TUI/文字 Agent，删除未使用的 `codex-exec-server.exe` Git LFS 文件及 `codex-package.json` 的 `execServer` 字段。官方 `rust-v0.166.0` 的 npm staging 同样省略二者；主 `codex.exe`、Code Mode Host、沙箱助手和 `--no-daemon` 不变。此操作只移除可选独立程序，不声称从主客户端二进制中删除全部远程相关代码；便携启动器原本就拒绝 `exec-server` 等服务端子命令。

同步 `tool/runtime-manifest.json`、`codex-package.json`、启动器固定摘要及常用/YOLO 模式副本，调整打包身份白名单、回归和使用说明。已完成任务的一次性 0.166 升级 Actions/适配脚本清理，不允许再次自动引入该 EXE。客户包以固定源码的干净工作树生成；重新打包的 `v0.166.0-portable.1` 必须由现有 `02-verify-and-publish-portable.yml` 的手动分发入口运行完整 Windows 检查与十轮回归，通过 ZIP/远端附件逐项回读后才发布。线上账号、实际端到端模型调用、用户终端滚动显示不在自动验收范围。只有用户实际使用的 0.164.0 可作为已确认稳定基准。

## 2026-10-30：Codex 0.166.0 官方运行时升级（自动化候选）

本次使用 GitHub Actions 从官方固定 release 下载 Windows x64 canonical package，校验归档与独立 EXE 摘要，同步主程序、Code Mode Host、执行器、沙箱助手、搜索工具及 manifest，保留包根启动和全部便携隔离策略。新版新增 codex-exec-server.exe 并适配 package metadata 的 execServer 字段；语音继续不打包，重复沙箱助手继续精简。

启动器 `CODEX_TUI_FULLSCREEN_TRANSCRIPT` 默认 false、可在受控 env.local.ps1 覆盖；继续使用 `--no-daemon` 防止共享 daemon 把状态迁到包外。本提交只有经 runner 验证的文件；真正的 Windows 全量发行门禁由单独 release workflow 执行。账号登录、真实网络代理、付费模型及用户终端重绘不以合成测试冒充实测。

## Codex 上游版本升级与便携包发布标准流程

**当前升级专用的两个手动 GitHub Actions：** [01 更新官方 Codex 运行组件](https://github.com/rileyaaa/Codex-Portable/actions/workflows/01-upgrade-codex-runtime.yml) → [02 完整 Windows 兼容验证、打包及发布](https://github.com/rileyaaa/Codex-Portable/actions/workflows/02-verify-and-publish-portable.yml)。仅允许人工分别触发，不创建 push、定时或自动接力入口。独立的 `02-check-compatibility.yml` 已被发布工作流内置审核替代，兼容性审核代码仍由 `.github/maintenance/02-compatibility.py` 维护；完整十轮审计由 `.github/scripts/release-audit.py` 承担。独立浏览器下载工作流已移除，包内固定浏览器校验功能继续保留。

**01 的自动范围：** 输入完整官方 `release_url`，支持 `rust-v0.167.0-alpha.3` 等 Alpha/Beta/RC 用于只读临时测试；正式稳定版也默认只检查。核对官方 SHA-256、Windows x64 归档布局及固定白名单，替换五个原生程序并同步 manifest、启动器、登录映射、环境模式副本、许可证及说明。仅当显式选择 `commit_changes=true` 且目标为稳定版，01 的只读 Job 才额外运行完整十轮审计及真实 ZIP 试打包，之后单独的可信写权限 Job 重新构建、核对候选差异和 LFS 后提交；不会执行刚下载的 EXE，也不会创建 Release。**发布与兼容范围：** [Release 工作流](https://github.com/rileyaaa/Codex-Portable/actions/workflows/02-verify-and-publish-portable.yml) 直接执行全部受控变量、模型/schema、启动器、Python/Node/PowerShell、完整 Windows 回归与十轮审计；失败停止，且默认不发布时也实际试打包客户 ZIP，不要求单独手动跑兼容检查。写权限发布 Job 只能在同一来源提交全部验证成功、人工选择发布后运行，再次核对 `main`、构建 ZIP、回读三个附件才公开。真实账号和第三方 API 的实机兼容仍需另行验收。
本节是今后升级 Codex CLI 稳定版本或重新打包便携修订时必须遵循的操作顺序；具体安全、权限和目录边界继续执行下方「维护约定」。不要用上一个版本的测试结果代替新版验收，也不要因为上游发布新版就自动覆盖当前可用包。

1. **确认目标与回退基线。** 核对官方稳定版、仓库 `main`、现有 Releases/标签、当前运行清单与最近的 Windows Actions 结果，区分「自动化验证通过」和「用户实际用过且确认正常」。先保留已确认稳定的旧 ZIP、配置与可回退版本，不读取或复制真实账号、密钥、会话及缓存；本轮只操作明确授权的项目文件。
2. **核对上游变更与发行组件。** 阅读目标 `rust-v<版本>` 官方 Release、更新记录、源码和配置 schema，确认 Windows x64 官方工件、SHA-256、许可证及 `codex.exe`、`codex-code-mode-host.exe`、搜索工具、Windows 沙箱助手的版本与实际查找路径。检查新增/删除的 EXE、DLL、资源与依赖；本包默认仅支持本地文字/TUI/Agent，不打包语音、可选独立 `codex-exec-server.exe` 或已证明可省的重复文件。每次升级都重新核对查找顺序，不能照搬旧版删除名单，更不能删掉本地 Agent、Code Mode 或沙箱真正需要的组件。
3. **逐项复核配置变量和协议。** 以新版实际源码消费点为准，检查 `env.ps1` 的每项默认值、`env.local.ps1` 白名单、命令行覆盖、最终生成的 `home/config.toml` 及子进程继承值；失效、改名或语义变化的变量必须修正或删除。重点验证包内 `CODEX_HOME`、交互式 `--no-daemon`、`CODEX_FAST_MODE=false`、`CODEX_TUI_FULLSCREEN_TRANSCRIPT=false`、默认关闭的 Plugins/MCP、普通/维护/YOLO 权限以及 `resume`/`fork`。自定义 API 要对照新版实际请求验证标准 Responses 的模型名、headers、tools、代理与 SOCKS/HTTP 桥，不能只凭 `wire_api=responses` 或配置解析成功推断兼容；官方账号流程单独验证。
4. **成对更新运行时和固定身份。** 从同一官方版本取得主客户端、Host 及配套文件，保留上游二进制原始字节并校验 Windows x64 PE、文件数量和摘要；同步 `tool/runtime-manifest.json`（来源、归档和逐文件 SHA-256、排除项）、`codex-package.json`、`run-codex.ps1` 的版本/固定摘要及 `login-json.ps1` 的登录版本映射。更新需要的 `env.ps1`，并同步 `Version_History` 的四份常用/YOLO 模式副本；正常副本须一致，YOLO 仅保留既定权限/联网差异。校验 Git LFS 实际文件，严禁把 LFS 指针当 EXE，亦不得通过关闭身份校验掩盖缺件。
5. **清理过期适配与同步文档。** 检查启动器中的旧版判断、已废弃参数、模型目录与代理兼容代码；核对 `tests/`、`tool/package-release.py`、`.github/workflows/02-verify-and-publish-portable.yml`、`.github/scripts/release-audit.py` 中固定的旧版本、运行文件白名单、测试数量、随机种子、校验条件和 Release Notes，确保真实覆盖本次目标版本，不能复用上一次的特例说明。同步现有 `README.md`、本文件及 `tool/工具更新说明.md`，不另外创建项目说明文件。检查 `.github/workflows/` 是否残留一次性下载/升级/代触发工作流；旧 `request-release-r2.yml` 已随本次规范化移除，未来同类临时入口不得长期保留；常驻正式发布工作流只允许手动 `workflow_dispatch`。
6. **修复并执行升级回归。** 在 Windows x64、PowerShell 5.1 和包内 Python/Node 环境运行相关及全量测试，覆盖 BAT 菜单与启动链、原生客户端版本、模型配置与实际请求、HTTP/SOCKS 代理、认证切换/异常恢复、会话恢复、Agent/Code Mode、沙箱权限、中文/空格及跨盘搬迁、模式副本、浏览器和工具依赖、发行文件清单。失败先修复再重新运行；Linux 或合成假接口只能作为补充，不可冒充真实 Windows、账号、模型或终端验收。每次正式升级还需由 Windows 发布门禁在最终提交执行新鲜的 **10 轮**随机回归，任何失败、错误、跳过、测试数量不符或源码变更都应阻止发布。
7. **依次手动运行 01 与 Release。** 对干净的 `main` 执行 01，`release_url` 输入完整官方页面链接，例如 `https://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.3`，默认 `commit_changes=false` 为测试；Alpha/Beta/RC 不允许提交。只有正式稳定版且明确选择 `commit_changes=true` 时，01 完成只读验证后由单独写权限 Job 再次检验相同来源、精确候选差异、LFS 和远端 SHA，随后才快进提交 `main`。需要发布 ZIP 时，手动启动 [Release 工作流](https://github.com/rileyaaa/Codex-Portable/actions/workflows/02-verify-and-publish-portable.yml)，选 `main`，输入匹配 manifest 的 `version=v<上游稳定版本>-portable.1`；`publish_release=false` 为默认全量验证与真实 ZIP 试打包模式；只有全部测试成功且显式开启 `publish_release=true`，并且测试 ZIP 和发布 ZIP 的 SHA-256 一致，才能正式发布。同一上游版本后续修订用 `.2`、`.3`；不再需要 `check_set` 或独立 02 的成功运行记录。任何失败都不得发布；无法触发 Actions 应如实报告，不默认增加 push/定时入口。
8. **核对打包与 GitHub Release。** GitHub Actions 应在 Windows 完成全量门禁、10 轮回归和源码再次校验，从干净提交生成客户 ZIP、`release-manifest.json`、`SHA256SUMS` 三个附件；先上传草稿，再下载回读逐项核对 SHA-256、ZIP 文件清单、文件数、来源提交、原生 EXE 与 LFS 实体，成功后才转正式发布。确认 Release 的 tag、target commit、三个附件和工作流成功状态一致。客户 ZIP 不含第一方测试、CI、Git 配置、构建脚本、用户认证、工作目录、缓存和临时状态；GitHub 自动生成的 Source code ZIP 不算便携发行包。未成功发布不得报告为「已打包上线」。
9. **独立实机试用与决定稳定性。** 用户将新 ZIP 解压到不同目录，不直接覆盖稳定包；按日常真实条件检查双击启动、中文/空格路径、API 或账号登录、代理、模型回复、一项实际 Agent/Host 工具调用、`resume`/`fork`、终端显示与退出后的数据保留。明确区分已通过、失败、未执行；真实账号、在线模型或设备测试未经授权不主动运行。只有用户确认日常使用正常，才将该版本视为「已实用验证稳定」。
10. **清理与回退。** 先保留旧版供回退；新版本已正式发布且经实际使用确认后，才按用户要求清理不再需要的旧 Release/附件及其标签，不删除仍在使用的稳定版或历史提交。清理本次临时工件、临时工作流与任务专属缓存，保留合法用户资料。若出现兼容问题，停止推广新版、保留故障证据并退回上一确认稳定版本，修复后使用新的便携修订重新走完整流程；不得覆盖已有发布标签或附件。

**交付口径：** 每轮维护至少报告目标版本、Git 提交、检查范围及结果、Actions 链接、Release/三个附件的真实状态、SHA-256 和尚待用户实测的范围。仅修改文档不需要重打包；未执行或因权限无法完成的步骤必须写明，不得把准备、推送、测试通过与发布成功混为一谈。

---
## 维护约定

开始维护前阅读本节及 [README](README.md)。这里统一记录项目限制；使用方法、下载步骤分别维护在对应文档，不在多处复制整套说明。

1. **只维护四份项目文档。** 根 `README.md`、本文件、`tool/工具更新说明.md`、账号格式转换子项目的 `README.md` 是固定入口。未经用户同意不新增项目说明文档；确有必要时先说明理由并征得同意。每次功能新增、修改或删除，同步相关说明、变量注释及受影响的技能文档；直接更正、删除失效内容，不持续堆叠重复说明。已授权技能所必需的 `SKILL.md`、第三方功能文档和许可证、用户转换任务生成的交付报告不属于新增项目说明文档。
2. **记录原因和结果。** 本文件开头维护稳定规则，下面按日期记录变更原因、最终结果、验证和必要的遗留问题。同一天同一事项可合并更正；不记录逐次尝试、排查对话、无效假设或临时命令输出。已解决事项应更新状态，不长期保留为待办。
3. **目标平台。** 以 Windows x86-64（x64）、本地 NTFS、Windows PowerShell 5.1 为准；x64 不等于 32 位 x86。保留 BAT 的 ASCII/CRLF、PowerShell 的 PS5.1 语法和既有编码兼容。Linux 或 PowerShell 7 的检查不能代替 Windows 验收。
4. **任意解压位置。** `D:\Codex` 仅为常用示例。包根从当前脚本位置派生，不依赖固定盘符、工作目录或继承的旧 `CODEX_INSTALL_DIR`；工具、配置、缓存、状态和临时路径跟随当前包根。不得把机器绝对路径写入默认设置。搬迁回归须覆盖旧包仍存在、无关工作目录、空格和中文目录。
5. **目录边界。** 默认只处理当前包内任务文件，不主动扫描、读写或清理宿主用户目录、其他目录及旧包。包外任务文件按用户已授权的具体范围访问；Windows 必需程序、系统依赖和固定系统策略存在性检查属于明确的系统访问。维护模式扩大包内可写范围，不自动授权包外操作；`workspace-write` 不能保证阻止全部包外读取。
6. **先验证路径，再访问。** 先检查词法边界，再检查完整祖先及目标的 reparse/junction/symlink、输入硬链接和适用的 ACL；检查应早于创建目录、读取内容或执行程序。保留正常/维护模式分界、受保护变量和 CLI 覆盖限制，不通过关闭身份校验、放开路径或关闭 Code Mode 掩盖故障。MCP/插件的外部命令及绝对路径需另行核对。
7. **每次升级复核变量。** 更新 Codex、Host 或任何工具后，核对对应变量的声明、默认值、加载/覆盖、生成配置、子进程最终值和新版实际消费点，并查看上游 schema/发行说明。区分启动器私有接口、原生变量、兼容别名和仅预留路径；确认失效时移除或替换并同步文档、回归。变量存在或程序安装成功都不等于功能生效。
8. **保持工件与工具来源。** Codex/Host 使用同一官方稳定 release 的 Windows x64 工件，校验来源和摘要，更新固定身份、登录版本映射及 `tool/runtime-manifest.json`；保留所需配套资源与许可证，不修改官方 EXE/DLL 字节。本包明确只做文字与 Agent 工作，省略语音组件并关闭仍有效的语音开关；无开关的上游入口如实说明不支持，不能保留失效配置冒充禁用。今后升级也保留文字/Agent 范围。其他工具按 [工具说明](tool/工具更新说明.md) 在包内安装/更新，工具缺失时明确报告，不静默调用宿主或全局包管理器，不永久修改系统/用户 PATH，不运行 Node 随附的系统安装脚本。
9. **保护状态与清理边界。** 不读取、记录或提交真实账号 JSON、API Key、认证快照、会话、机器私密配置及其内容/哈希。测试使用合成数据，临时文件放包内 `tmp` 的独立目录，创建前检查链接；只清理本次创建的文件和启动的进程。认证 snapshot、transition/logout/recovery 标记及 installation identity 不当作缓存删除，既有用户数据和进程应保留。配套浏览器资料固定在 `cache/browser`，任务退出只关闭进程，默认保留资料；用户运行“清理缓存”时才统一删除 Cookies、网站登录和缓存，并通过专用锁拒绝清理活动会话。
10. **单一维护来源与模式副本同步。** Android 完整流程统一维护在 `home/plugins/android-apk-lab/skills`，外层只保留精简 `apk-test-router`，保留用户编写的 `mumu-adb`。Office 的 docx/pptx/xlsx 共用 helper 副本保持一致。根 `env.ps1` / `run-codex.ps1` 更新时，必须同步 `Version_History` 下的四份常用/YOLO 模式文件：常用两份与根文件逐字节相同；YOLO 启动脚本与根相同，env 基于根生成，保持 `CODEX_PORTABLE_PROFILE=strict`，仅将 approval 改为 `never`、sandbox 改为 `danger-full-access`，并保留原 YOLO 的 `CODEX_SANDBOX_NETWORK_ACCESS=true`。Fast、扩展默认值及其他修复全部同步，不另维护旧版客户端身份。用回归验证差异仅为这三项赋值。其他真正历史资料不批量替换；账号格式转换器独立维护。
11. **验证与交付。** 运行与变更相关的回归，明确区分通过、失败、跳过和未运行；不能用假输出或空程序冒充工具可用。保留用户改动，使用现有 checkout，不另建 worktree，除非用户要求。提交/推送前核对差异、引用、Git LFS 工件及私密/临时文件排除；没有执行的 Windows、真实账号或设备流程不得写成已通过。正式包从干净提交的文件清单生成，包含实际 LFS 工件，逐项验证 ZIP，并附来源提交与 SHA-256；不递归打包整个工作目录。
12. **按任务启用，默认关闭 Fast。** `CODEX_FAST_MODE=false`；Plugins、用户 MCP 默认关闭，维护模式也不自动启用。扩展配置须同时满足对应开关和本次 `--portable-extensions`。发现、读取技能或进入维护模式不代表授权运行其工具；只有用户明确提出相关任务，才检查依赖、启动服务、连接设备或操作目标。包内安装不等于授权控制整台电脑或模拟器；实际任务仍限已选目标。
13. **GitHub Actions 只手动运行。** 所有工作流仅允许 `workflow_dispatch`，不添加 push、PR、定时或关联工作流自动触发。临时下载使用短保留期，不建立长期大文件缓存；产物取回并校验后及时删除本次 artifact、临时分支/发行附件及下载缓存。未能执行或清理须明确报告，不能将保留期代替主动清理。
14. **及时提交并推送。** 每完成一批可独立验证、文档已同步的修改就提交并推送到用户指定仓库，不将大量已完成改动或多个提交长期堆在本地。推送前检查差异和测试，推送后核对远端提交；未完成的功能留待下一批，不能为赶进度发布已知损坏入口。
15. **控制体积与重复能力。** 默认面向 DBA、Python 爬虫/数据处理和偶尔开发调试；保留常用运行依赖，低频 Go 编译仍优先放独立项目的手动 GitHub Actions，不自动补回 Go 编译工具；Python EXE 打包已于 2026-10-25 获用户明确授权恢复历史 PyInstaller 及必要依赖，仅在明确打包任务中由 AI 直接调用包内 Python 原生模块，不额外维护打包封装。同一用途优先复用已装依赖；浏览器统一为一套 Playwright 和一份配套 Chromium，不并装 ChromeDriver、第二套浏览器或 Chrome DevTools MCP。先检查现有 API/CDP 是否能完成任务，再考虑新增工具并说明收益与体积。精简前核对上游查找路径、共享依赖和实际功能；不因文件名相似就删除官方助手或资源，不为体积牺牲已保留功能。所有可配置的 profile、下载、缓存、临时文件随包根移动；不能以“便携”名义隐藏系统权限或工具自身的限制。
16. **客户发行内容。** 先在源码检出中完成验证，再从干净提交构建发行 ZIP。第一方测试、CI、Git 配置和开发打包器留在仓库，不进入客户包；临时文件、缓存、账号和本机配置不发布。保留运行依赖、许可证和四篇说明，逐项验证 ZIP 与来源清单。
17. **按风险选择验证范围。** 小改动也可能阻断启动或改变请求协议，不能只按行数判断。客户端/Host、依赖工件、权限与路径边界有变化时执行完整 Windows 门禁。已授权维护范围内、工件未变的脚本补丁，可依据已通过的全量基线、差异核对、定向回归与必要的真机反馈重打包；记录未重跑的范围，逐项校验 ZIP 与上传回读。已知问题未解决时不得以旧测试通过覆盖它，也不将旧测试记成本次新测试。
18. **发行命名和语言要求。** 正式发布标题使用 `Codex Portable <CodexVersion> - Portable r<N>`，Git 标签使用 `v<CodexVersion>-portable.<N>`，发行 ZIP 文件名使用 `Codex-Portable-v<CodexVersion>-portable.<N>-windows-x64.zip`。标题、标签和附件文件名必须使用 ASCII 字符；**GitHub Release 的发布说明仍须使用英文**，这不影响项目开发文档统一采用中文。同一 Codex 版本的可下载包发生变化时递增便携修订号；升级 Codex 上游版本后，便携修订号从 1 开始。仅修改文档不需要增加便携修订号。不得覆盖已发布的标签或附件；日期由 Release 元数据和维护记录保留。

19. **终端偏好由启动器显式生成。** `CODEX_TUI_FULLSCREEN_TRANSCRIPT=false` 为默认值；`env.local.ps1` 仅通过受支持变量白名单覆盖，复用严格布尔解析并写入 `tui.fullscreen_transcript`。根脚本和四份模式副本同步；`--no-alt-screen` 的原生限制和 `--no-daemon` 的隔离策略保持不变。升级时核对该字段的定义、默认值及真正渲染消费点，不能把配置成功解析当作 Windows 滚动重绘验收。

### 升级必须检查的项目

- **来源与配套文件：** 官方固定 release、架构、摘要、许可证、Host/搜索/沙箱助手及实际查找顺序；同步 manifest、版本映射与四份模式模板。
- **真实交互入口：** 在真实终端覆盖双击、提示文本、resume/fork；检查共享后台服务的默认行为、安装路径及本包 `--no-daemon` 策略，不能为启动将 CODEX_HOME 移到包外。版本输出、模型导出和配置读取成功不代表交互启动成功。
- **认证与会话：** API、账号 JSON、官方设备码分别确认认证选择与实际请求路由；检查切换、刷新、退出及失败恢复的 snapshot/标记归属。`last` 不能替代显式认证模式诊断。没有实际验证的流程如实列为待验，不索取或记录真实 Key/账号文件。
- **模型与请求协议：** 核对模型 slug、元数据/schema、默认推理档位、上下文、工具声明及变量实际消费点；特别检查 `use_responses_lite` 等内部协议字段。不能仅看 `wire_api=responses` 就假定协议不变；对照实际请求路径、模型、头和消息/工具结构。自定义 API 保持配置原模型名并使用标准 Responses；官方账号单独验证。Fast 默认仍关闭。
- **代理与网络条件：** 沿用用户实际 HTTP/SOCKS 类型、主机、端口、桥接与 NO_PROXY 条件；覆盖明确开启、默认开启/回车、模型绕过及本地命令代理。模型 API 联网与 shell 沙箱联网分开检查；不能用跳过菜单的直连测试代替用户的代理流程。
- **便携路径与状态：** 正常/维护/YOLO、旧包仍存在、换盘符、中文/空格路径；确认配置、数据库、下载、缓存、编译临时文件随当前根移动，链接拒绝先于访问，清缓存不删除认证。系统依赖访问与“系统层面零包外写入”不能混为一谈；未做文件访问跟踪不能宣称后者已证实。
- **实际功能：** 覆盖模型回复与包内一项 Agent/Host 工具调用，确认功能没有因精简或兼容开关被关闭。假接口用于隔离协议/代理回归，不能单独算真实账号、模型或设备验收；不可用的测试环境要明确说明。
- **交付与编码：** Windows PowerShell 5.1、ASCII/CRLF BAT、单个 UTF-8 BOM、受保护变量及模式副本。下载脚本原文件，避免复制网页引入重复 BOM。按风险选择检查后，从干净提交打包，排除测试/临时/用户状态，上传回读后才发布；成功替代后再删除问题发行包，保留 Git 历史追溯。

## 2026-10-26：Windows 验证通过的兼容性热修复发行版

**原因与结果：** Codex 0.164.0 调整了交互式后台服务的启动准备流程和内置模型元数据。修复后，交互式启动使用官方 `--no-daemon` 参数，使 `CODEX_HOME` 继续保留在便携包内；自定义 API Provider 继续发送标准 Responses 请求，不改变用户配置的模型名称或代理。用户已确认，直接下载 GitHub 上更新后的脚本即可恢复正常使用。复制网页渲染后的脚本文本可能额外引入一个 BOM；仓库中的 Windows PowerShell 5.1 脚本保持单个 UTF-8 BOM。

**发布情况：** 正式版本为 [Codex Portable 0.164.0 - Portable r1](https://github.com/rileyaaa/Codex-Portable/releases/tag/v0.164.0-portable.1)，来源提交 `f4c0c4706fd052bdddc8b33207c6f2ea0145c4d1`。发行 ZIP 大小为 534,778,576 字节，包含 8,689 个客户文件；归档 SHA-256 为 `bd3971f7d7633fd1260dedafa1e9a1aa88c6f0ddfaddca38d7406353a3409a5b`。此前已确认存在故障的 `v2026.10.26` Release 及其附件，在替代版本验证完成后已删除；原 Git 历史和旧标签仍保留，供后续追溯。

**验证情况：** 手动触发的 Windows [Actions 运行记录 40267390511](https://github.com/rileyaaa/Codex-Portable/actions/runs/40267390511) 已通过，耗时约 4.5 分钟。本次定向热修复门禁以完整 Windows 验证基线 `8e09466f`（运行记录 40253783757）为参照，核对源码修改是否位于允许范围内、环境变量默认赋值是否保持不变，并检查原生客户端版本、模式副本与打包回归；同时执行 PowerShell 5.1 的模型及配置检查，包含 34 项模型选项用例和 11 项交互命令分发用例。客户端、Host 及依赖工件均未改变。此前的离线原生客户端对照测试，已在不使用真实凭据或付费模型调用的条件下，验证项目 HTTP/SOCKS 代理桥能够传递标准 Responses 请求。客户发行 ZIP 排除了项目自有测试、CI 工作流、Git 配置、开发打包工具及用户运行状态。上传的三个附件均已重新下载并校验；正式发布前逐项检查 ZIP 内容，发布后再次核对最新 Release 元数据和公布的校验值。Runner 临时文件已清理，未保留 Actions 工件或缓存。**此次定向验证不等同于重新执行完整 Windows 测试，也不代表真实账号登录、在线 Agent/Host 调用或实际设备验收通过。**

## 2026-10-26：自定义 API 的标准 Responses 兼容

**原因与修复：** 官方 0.164.0 内置 gpt-6.1-sol 等模型条目启用了 `use_responses_lite`。与原包 0.156.1 对照发现，新客户端即便 provider 声明 `wire_api=responses`，仍会自动发送内部 Lite 标记、additional_tools 等不同结构。现在自定义 API/本地 provider 总是生成包内兼容 catalog，在保留模型 slug、上下文与其余原生元数据的同时将 `use_responses_lite=false`；官方账号继续使用原生目录。保留 1080 等用户配置的代理端口，不改认证、模型名称或权限。

**实际验证：** 在包内独立 tmp 下载并核验两个官方 Linux 工件，两个版本均经项目原有 HTTP→SOCKS5 桥与本地模拟 1080 端口请求假接口。原包与新版均原样请求 `gpt-6.1-sol`；新版修复后不再发送内部 Lite 请求头及 additional_tools，标准 tools/消息结构的请求成功收到合成回复。不使用真实 Key、不调用收费模型；非测试目标均被模拟代理拒绝。手动检查器 `tests/check_responses_wire.py` 已保留：原 0.156.1 标准请求通过，未使用兼容目录的 0.164.0 会明确检出 Lite 请求头，使用生产函数生成的目录后通过。它仅供源码维护使用，不进入客户包，不自动下载客户端。这证明请求协议与代理链；随后用户已确认直接下载 GitHub 脚本恢复正常。该 Linux 对照本身不称为 Windows 原生测试。

## 2026-10-26：真实交互启动与后台服务冲突

**原因与修复：** 用户真机反馈 `CODEX_HOME must be outside the source CLI package`。固定 0.164.0 的共享后台服务安装器拒绝 CODEX_HOME 位于源 CLI 包内；此前 `--version` 和 `features list` 检查没有覆盖自动后台服务准备。最终交互启动统一附带官方 `--no-daemon`，普通 TUI、提示文本、resume/fork 均覆盖，显式参数不重复追加；exec、登录和配置管理调用保持原有参数。CODEX_HOME 保持包内，权限、认证、Fast 和 Host 身份不变，模式副本同步。普通 Agent/Code Mode 使用嵌入服务，跨进程共享后台服务不启用。

**验证与边界：** 生产最终分发函数的 11 组参数/退出码检查与模式副本检查通过；用户已确认直接下载原文件后恢复正常。此前 `--portable-auth last` 不能代替显式 API 选择，排查时须保留用户实际代理条件。云端 ConPTY 驱动未能稳定识别终端界面，已移除新增驱动与临时检查选项，不将失败或版本输出当作交互测试成功，不新增长期测试依赖。

## 2026-10-26：独立审查后的目录与数据保护修复

**原因与结果：** 默认 PATH 移除带历史绝对解释器路径的 vendor Python bin，五个 BAT、Android 子入口与模式副本同步；已有通用 CMD 入口保留，PyInstaller 继续使用包内 `python -m PyInstaller`。严格入口拒绝内部 `tcp-tunnel`，避免未审核的文件读取与网络服务入口。修正打包来源清单中的旧入口说明。

**数据保护：** 未知 SQLite 索引先复制 DB/WAL 到包内 tmp，再由 SQLite 识别归属；拒绝时不打开原库，避免 checkpoint 或 SHM 改写。指令安装在两份输出都提交前保留原 MD 的逐字节备份，配置失败恢复旧 MD；回滚受阻时保留包内恢复文件并明确报错。Python shim 刷新先验证一级 dist-info 目录，再检查元数据文件，避免 glob 提前枚举链接目标。

**转换器：** 预览按实际凭据及其 JSON/URL/shell 表示隐藏值，复制/下载仍为原内容。dotenv 对含特殊字符的值安全引用；换行、NUL 和无法一致引用的值不生成配置，提示改用 JSON，避免截断或注入额外配置项。

**验证范围：** 新增第二份配置提交失败、崩溃残留 WAL 原文件保持、链接元数据拒绝前不得枚举、默认 PATH、内部子命令拒绝及凭据/ dotenv 语义回归。合成测试不读取真实账号；Windows 完整验证和发布状态以对应手动工作流实际结果为准。

**发布结果：** 完整 Windows 验证及附件回读通过，正式版为 `v2026.10.26`，来源 `8e09466f`；完整结果与真实使用待验范围见文末。

## 2026-10-25：撤销多余打包封装并复查

**范围：** 按用户要求保留已恢复的 PyInstaller 与必要依赖、许可证和来源记录，撤销上次额外加入的专用 CMD、自定义参数／路径封装及其专属测试。通用 Python CLI helper 恢复为此前已验证的原文件，不改变其他命令；原有依赖闭包、历史对象核对保留，Windows 版本测试改用原生 `-m PyInstaller`。现行使用说明同步为 AI 按任务调用原生模块并遵守包内路径约定。此前 PDF、Office、Android、账号保护及所有官方组件不变。

**复核与测试修正：** 首轮三个全新 Linux runner 对相同源码的 164 项回归均通过。随后完整 Windows 工作流 `40206266734` 发现 4 条 PDF 测试在清理阶段报 WinError 32：测试自身用于核对索引的 `with sqlite3.connect(...)` 只结束事务、未关闭连接。现仅将这四处改为 `contextlib.closing`，原有数据保护断言、生产脚本、官方组件及发布门禁不变；未通过的发布已提前取消，没有打包或上传。独立连接审计在原测试复现 4 个未关闭连接，修改后为 0。

**重新复核：** 测试修正后重新计数：Actions `40207107803` 的三个全新 Linux runner 对固定提交 `fc188e9ab77617698a8b348759f56744662eb9c9` 分别正序、逆序和固定随机顺序执行 164 项源码／元数据回归，失败、错误、跳过和遗留 SQLite 连接均为 0；每轮浏览器离线策略、转换器、源码解析和 PowerShell 离线契约均通过。Windows 原生项目留待同一最终提交的完整发布门禁，不借用此前未完成的 Windows 结果。

**发布边界：** 仅当三轮复核通过后，才清理本次临时工作流并请求既有 02-verify-and-publish-portable.yml 的 check_set=full。完整 Windows 验证、干净提交打包、上传附件回读全部通过才发布；实际状态以 Release 和对应工作流为准，不用源码检查冒充 Windows 通过。真实账号、在线 Agent/Host、提权沙箱、任意 PyInstaller spec/hook 的实际冻结产物与真实设备不在本轮范围。


## 2026-10-25：按授权恢复 Python EXE 打包工具（不编译、不发布）

**来源与范围：** 以 `ea68ed98de7a1e92a8ccccb4430347917dab0dc9` 为基线重新检查。确认 PyInstaller 在精简时被移除；按用户本次明确要求，从 `fcaf45e5dfe4c97f096475f211a423b6d882c4ae` 恢复 PyInstaller 6.21.0、hooks 2026.6、altgraph、pefile、pywin32-ctypes、setuptools 及元数据/许可证，保留当前 packaging 26.2，不升级其他运行库。`tool/python-build-manifest.json` 记录所用历史 Git 对象；`_distutils_hack` 只恢复源文件，不恢复旧 `__pycache__`。不恢复 Go、uv 或宿主编译器，不改 Codex/Host、认证、权限、扩展开关或已有 PDF/Office/Android 修复。

**便携入口：** 新增由现行生成器产生的 `tool/bin/pyinstaller.cmd`，沿用现有 Python CLI helper，避免直接执行嵌入旧绝对路径的 vendor EXE。通过固定版本原解析器保留普通脚本、既有 spec 和 `--` 后参数语义；固定包内解释器，先检查主输入和受管目录，暂存限 `tmp`、缓存 `cache/pyinstaller`、默认产物/spec 为 `work/dist`/`work/spec`。失败只清理本次临时目录并恢复进程环境。其他 Python CLI 仍走原入口。固定依赖清单从 36 项增加为 42 项；原锁摘要失效时仍拒绝使用，不伪造历史 wheel 哈希。

**三轮复核：** 最终代码在三个新进程分别正序、逆序、固定随机顺序执行 179 项可本地运行的 Python 测试（含新增 19 项包装入口/路径/状态回归），三轮均无失败、错误或跳过。每轮另通过 8 项离线浏览器策略及转换器 12 项输入/映射、8 项模板、18 项界面/ZIP/账号库检查；第二轮另通过 24 个真实 ZIP/文件系统独立子进程场景，第三轮核对 102 份 Python、10 份 JavaScript 语法和 Office 三副本一致性。本轮未再确认新的遗留生产 Bug，没有为了检查而修改无关正常逻辑。新入口测试以替身捕获参数和环境，不执行 PyInstaller 构建引擎，不把这些结果当作 EXE 打包成功。

**提交与未验证边界：** 仅提交恢复组件、便携入口、原有依赖测试的扩展、新入口回归及既有三份文档；不启动 Actions，不编译 EXE，不生成客户包或修改 Release。完整 Git/LFS/原生运行环境依赖的 5 个测试模块和 3 个单项未在本地运行；已为后续完整检出增加历史对象一致性和 Windows `--version` 检查，但本轮不计为通过。实际 Windows 冻结产物、任意第三方 hook、真实账号/设备与完整 Windows 发布验收仍待单独验证。入口只是路径/状态管理，不是执行沙箱；spec/hook 是可信代码才能运行。三轮源码复核不保证所有场景绝对无 Bug。

## 2026-10-25：Office 解压链接边界与失败句柄保护（源码已提交）

**原因与修复：** 以 `cd6e46542c8debc44a2300d7bfedc08de7d42ec0` 为基线，复现 `safe_extract` 先解析成员路径、后检查链接，导致解压可沿已有内部链接或悬空链接写入重定向目录；ZIP 成员打开失败时，输出文件尚未进入上下文管理，清理时句柄仍然打开。现先用不跟随目标的检查验证完整祖先链，再解析成员路径；先接管输出句柄，再打开 ZIP 成员。三份 Office helper 同步，保留独占创建、已有文件保护、正常 XML／二进制内容和失败清理。不修改 PDF／Android 已有修复、认证、普通／YOLO 权限、Fast、扩展开关或官方组件。

**复现与三轮本地复核：** 在原测试文件新增 7 项回归，未修复 helper 出现 5 项失败，修复后相关 17 项全部通过。最后一次生产修改后，新进程正序、逆序、固定随机顺序分别执行 160 项可本地运行的 Python 源码回归，三轮均无失败、错误或跳过；每轮另通过 8 项离线浏览器策略，以及转换器 12 项输入／映射、8 项模板和 18 项界面／ZIP／账号库检查。第二轮 24 个独立子进程覆盖三份 helper 的真实损坏 ZIP 文件头、CRC 错误、内部／外部／悬空链接、硬链接冲突、路径穿越、正常提取与重新封装；原实现对照 24 场景检出 12 个预期失败，另 12 个正常控制仍通过。101 份 Python、10 份 JavaScript 语法及 Office 副本一致性通过。所有样本为包内 tmp 中的合成数据，没有调用真实账号、设备或外部服务。

**提交与边界：** 修复与测试已通过 GitHub 连接器提交至 main，并回读校验文件摘要；原始补丁及三轮本地日志保留。按用户最新要求，不启动 Actions、不编译、不构建客户发行包、不发布或覆盖 Release。Windows／PowerShell 5.1、真实 Chromium、完整原生依赖及真实 PDF 提取本轮未运行；5 个依赖模块和 3 项依赖完整 Git/LFS 的检查另列未执行，不计入通过数。三轮结论仅限本次源码与合成场景，不保证所有场景无 Bug，也不宣称消除校验与系统调用之间全部竞争窗口。

## 2026-10-25：Office／Android 暂存目录与失败句柄保护（仅源码提交）

**原因与修复：** 以 `15c340fc82dea15c2ded1fde753848070b0415cc` 为基线，复现 Office 重新封装、Android 文本写入／复制／提取仍在持久输出目录创建暂存文件，且损坏的包内 `tmp` 未在创建输出目录前拒绝。现统一先校验并准备当前包的 `tmp`（Office 使用既有 `tmp/office`），再创建输出父目录；保留原子替换、正文／二进制内容及失败时仅清理本次暂存的行为。另复现 Android 复制源打开失败时暂存描述符未关闭，调整上下文管理器顺序，先接管暂存句柄再打开源文件。三份 Office helper 同步，未改动已有 PDF 修复、账号转换器、认证、权限、扩展开关或官方运行组件。

**三轮本地复核：** 原有三份测试文件新增 13 项回归；独立未修复源码对照检出 15 个失败断言（含参数化子案例，错误与跳过均为 0），修复后相关 40 项测试通过。最后一次生产修改后，分别在新进程正序、逆序、固定随机顺序执行 146 项可本地运行的 Python 源码回归，三轮均无失败、错误或跳过；每轮另通过 8 项离线浏览器策略，以及转换器 12 项输入／映射、8 项模板、18 项界面／ZIP／账号库检查。第二轮额外用 40 个独立子进程及实际文件系统审计验证中文／空格路径、搬迁和旧环境变量、链接／文件型 tmp、输出失败、源文件中途消失、截断流与编码失败；第三轮核对 101 份 Python、8 份 JavaScript 语法、Office 副本一致性及固定修复文件摘要。三轮在本次范围内未发现新的可复现问题，测试只使用包内 tmp 中的合成数据，不操作真实账户或设备。

**提交与边界：** 按用户最新要求暂停编译和发布，本次不触发 Actions、不构建客户发行包、不创建或覆盖 Release；仅提交修复、原有测试及本记录，并移除遗留一次性取消工作流。Windows／PowerShell 5.1、原生组件、实际 Chromium、完整依赖和真实 PDF 提取验收未在本轮执行；缺少完整 Git/LFS 检出的 3 项检查及 5 个原生依赖测试模块明确列为未运行，不计作通过。上述三轮是本地源码复核，不替代今后发布前的完整 Windows 验收与附件回读，也不保证所有场景绝对无 Bug。

## 2026-10-25：PDF 资料库原子写入暂存边界

**原因与范围：** 在 `adf8b0c9d3fbea5ca181b03a44f7e9512d33d989` 复现正文及报告的原子写入把 `.pdf-library-*` 暂存文件放在持久库目录，而非包内 `tmp`。现先校验并准备当前包的 `tmp`，再创建输出父目录和独占暂存文件；保留原有 UTF-8/LF 写入、原子替换及失败清理逻辑。不改变 PDF 提取、SQLite 归属、用户正文保护、账号转换器、认证、权限或运行组件。

**复现与前两轮：** 原有 128 项源码回归通过，但未覆盖暂存位置。原数据库测试文件新增 5 项纯合成写入回归，旧实现共 12 项中 3 项失败，修复后 12 项全部通过。第一轮重新运行 133 项源码回归、8 项浏览器策略以及转换器 12 项输入/映射、8 项模板和 18 项界面/ZIP/账号库检查，并核对 573 份源码、6,941 个跟踪路径及 Python/JavaScript 语法；第二轮新进程逆序通过同组 133 项，并用 10 个独立子进程检查 Unicode、大文本、搬迁、链接、替换失败和编码失败，独立核对 6,893 个客户路径及 48 项开发文件排除。两轮未发现新问题；临时产物仅在本轮包内 tmp，测试未使用真实账号。

**第三轮与发布门禁：** Actions `40183181411` 的全新 Linux/Windows runner 检出修复提交 `057a49ed362bd78e3f2eacf47a2ef961d4986374`：134 项随机顺序源码回归无失败、错误或跳过，浏览器策略、转换器、101 份 Python 和 41 份 PowerShell 解析及离线策略通过；Windows 包内 Python 的 159 项回归（含真实 PDF 提取与本轮暂存检查）、20 项 Node 回归、真实 Chromium、账号库、Cookie 持久化和主动清理均通过。本地 133 与 CI 134 的差异为完整 Git 检出的文件清单检查。修复后三轮连续未发现新的可复现问题。已下载校验的临时源码 artifact 主动删除，本工作流随记录清理；再由未修改的 02-verify-and-publish-portable.yml 对最终提交完整验证、打包及上传回读，成功后才发布新版本。真实账号、在线 Agent/Host、提权沙箱和真实设备未测；三轮通过不是所有场景绝对无 Bug 的保证。
**后续补丁（只提交源码，不启动 Actions）：** 后续检查还发现：初次核对索引的生成 Markdown 后，耗时的 PDF 渲染可能与用户新建／修改／删除 Markdown 交错，旧流程会覆盖新内容；删除源 PDF 时，旧流程可能删除初检后刚被用户修改的 Markdown。现在输出写入时在暂存文件准备完成后、最终替换之前再次检查旧文件 SHA-256 或新文件必须不存在；删除旧源输出前再次校验归属。原有的正常增量复用、输出原子替换与失败暂存清理不变。新增 7 项合成场景覆盖渲染及暂存期间的新增、修改、删除、旧源清理与正常增量；原有源码负例中 4 项失败，修复后本地三轮可运行回归通过。该检查不能宣称消除检查与系统调用之间的所有极短竞争窗口；Windows 原生与正式发布验收未执行，仍待后续单独验证。

## 2026-10-25：转换模板的字符串与命令参数保护

**原因与修复：** 从 `1326836bfc5a578b23455b1bcbd08403032e8bf6` 复现两类模板问题：LiteLLM YAML 的动态字段没有作为字符串编码，`#team` 被当作注释、`true` 密钥被当作布尔值；cURL 草稿直接插入 URL、凭据和多行账号名，`&` 会拆分命令，变量与引号会改变实际参数，账号名换行会脱离注释。现仅对 YAML 动态标量做字符串编码（含 YAML 特殊换行），对 POSIX cURL 的 URL 和凭据做字面量引用，并逐行保留账号名注释。未提供凭据时保留原 OPENAI_API_KEY 环境变量占位。保留账号内容、识别规则、其他输出格式及既有账号库保护，不修改 Codex/Host、认证、权限、扩展默认值或运行工具。

**本地复现与前两轮检查：** 在原 smoke 中新增 8 项模板回归，未修复代码 8 项失败，修复后全部通过。第一轮 128 项 Python 源码回归、8 项浏览器策略、12 项输入/映射和 18 项 UI/ZIP/账号库检查通过；解析 101 份 Python、9 份第一方 JavaScript，并核对 573 份源码及 6,941 个跟踪路径。第二轮在新进程逆序复核同组 128 项源码回归；独立 YAML 解析器验证 500 组字符串往返，真实 POSIX shell 以无联网的 curl 替身验证 98 组参数，另对照 24 组原实现输出，确认除 YAML/cURL 及文件包中对应 cURL 内容外均逐字节一致。两轮未发现新的可复现问题，所有输入均为合成数据。

**第三轮与发布门禁：** Actions `40179590268` 的全新 Linux runner 检出修复提交 `45b8cffcbf8af8fb11c31e152180340457292833`：129 项随机顺序 Python 源码回归无失败、错误或跳过，8 项浏览器策略、12 项输入/映射、8 项模板和 18 项 UI/ZIP/账号库检查全部通过；101 份 Python、41 份 PowerShell 解析，以及 33 项模型参数、12 项权限显示、9 项登录保护、7 项登录流程与共享 URL 契约也通过。129 与本地 128 的差异是完整 Git checkout 额外执行实际跟踪清单检查。修复后三轮连续未发现新的可复现问题。本记录与临时审核工作流清理后，仍须由未修改的 02-verify-and-publish-portable.yml 对最终提交执行 check_set=full；Windows 包内运行环境、PowerShell 5.1、原生启动链、浏览器、干净源码打包及上传附件回读全部通过才发布新版本，不覆盖已有 Release。实际发布状态和来源提交以新 Release 为准；本次未导出新的源码 artifact。真实账号、在线 Agent/Host、提权沙箱及真实设备未测，三轮源码复查不能冒充 Windows 验收或所有场景无 Bug 的保证。

## 2026-10-25：账号库与异步导入保护

**原因与范围：** 在 `fd915c83521bf7b1de786ac9334a6c9d8749c580` 上重新复现三项尚未入库的账号库问题：大密文展开为函数参数导致导出栈溢出、异步导出读取了点击后变更的状态、无效导入在失败前已替换原状态。现分块编码 Base64、在首次 await 前固定导出快照、先校验完整导入内容再更新页面。另复现旧 FileReader/解密异步任务覆盖后续清空、编辑、转换或新文件的问题；增加输入版本标记，丢弃过期导入结果和错误提示。保留远端已修复的包装数组和规则映射代码与测试，不改动账号库 v1、PBKDF2-SHA256 150000、AES-GCM、认证、权限、Fast 或官方工件。

**复现与验证：** 旧账号库代码在新回归中失败 5 项；仅修复账号库而未加异步保护时，新增 5 项竞争回归全部失败。最终本地版本的 18 项 UI/ZIP/账号库检查及原有 12 项 smoke 回归均通过。第一轮正序 128 项 Python 源码回归、8 项浏览器策略通过；第二轮分两个新进程逆序跑完同组 128 项，并通过独立 Python/Node 加密交叉验证：8 次解密（最大明文 1189316 字节）、16 次错误密码/篡改拒绝、10 组 Base64、1331 组包装输入、10 种无效导入保护、5 次兼容导入、21 组代理边界和 10 个 Python CLI 子进程场景。本地两轮未发现新的可复现问题，未使用真实凭据。

**第三轮与发布门禁：** Actions `40176018534` 在全新 Linux/Windows runner 检出修复提交 `7a2847eeeed89769a90fba18de619a537347b798`：129 项随机顺序源码回归无失败、错误或跳过；浏览器策略、18 项转换器检查、既有包装/映射 smoke、PowerShell 解析及离线策略通过。包内 Windows Python/Node、真实 Chromium Web Crypto/FileReader、大账号库往返、错误密码保留、清空取消导入、既有 HTML/ZIP/规则映射、截图、Cookie 持久化及主动清理均通过。三轮连续未发现新的可复现问题。临时源码 artifact 已主动删除，本工作流随本记录一并移除；正式发布仍由原 02-verify-and-publish-portable.yml 对最终提交执行 check_set=full，完整验证、打包、上传回读全部成功后才发布，不覆盖已有 Release。真实账号、在线 Agent/Host、提权沙箱及设备未测，三轮通过不等于任何场景绝对无 Bug。

## 2026-10-25：包装数组与字段映射的后续复查

**原因与修复：** 以已发布 `v2026.10.25.1` 的 `a716f58213b523215fbca2742575f2b57e1ad205` 为基线，再次复现两类转换器问题：`data/items` 是元数据、后续字段才是数组时，原逻辑仍选中前面的非数组并报错；规则映射会读取继承属性，破坏 `constructor/toString` 等合法 JSON 键，映射到 `__proto__` 还会改变结果原型并丢失字段。现只调整数组选取、规则自有属性判断和普通数据属性写入三处，不改变合法数组优先级、账号内容、认证或输出格式。新增 12 项输入/映射回归，旧代码稳定失败 8 项，修复后全部通过；既有 Windows 浏览器测试增加真实页面导入和规则映射检查。

**本次验证：** 第一轮重新通过 128 项 Python 源码回归、8 项浏览器策略、转换器 smoke/UI/ZIP 检查，解析 101 份 Python 和 10 份 JavaScript，并核对 573 份源码及 6,941 个跟踪路径。第二轮使用独立 Python 参考实现核对 512 组包装字段组合和 200 组递归映射输入，另执行 10 个独立 Python CLI 场景及逆序 128 项源码回归，均未发现新问题。第三轮 Actions `40173977873` 在全新 Linux/Windows runner 检出修复提交 `0309d53936090e48def86125c8cf832cd39055d2`：129 项随机顺序 Python 源码回归无失败/错误/跳过，浏览器策略、转换器及 PowerShell 解析/离线策略检查通过；Windows 包内 Python/Node、真实 Chromium 页面导入/规则映射、既有 HTML/ZIP、截图、Cookie 持久化和清理检查也通过。三轮连续未发现新的可复现问题。完整发布仍须对清理后的最终提交执行原有 `02-verify-and-publish-portable.yml` 的 `check_set=full`，只有打包及上传附件回读通过后才发布 `v2026.10.25.2`，以对应 Release 的实际来源提交和运行结果为准。

**范围与边界：** 仅修改账号转换器、对应原有测试和两份既有说明，不变更官方 0.164.0 工件、普通/YOLO 权限、Fast、MCP/Plugins 默认值或用户状态。所有输入均为合成数据；三轮复查通过不等于所有场景绝对无 Bug，真实账号、在线 Agent/Host、提权沙箱和真实设备仍不在本次验证范围。正式发布须沿用完整 Windows 门禁，不覆盖已有版本。

## 2026-10-25：辅助工具、账号转换器修复与三轮复查

**Python 用户文件保护：** `88967f671569296a3fdcc5b8c155201f53805582` 修复刷新器覆盖同名用户 CMD，以及指令安装在无效本地配置被拒绝前覆盖旧指令的问题。刷新前和原子替换前核对生成内容归属；用户修改保留，并以既有状态码 3 报告未完成项。指令安装先预检本地配置，再写入指令；写入和替换前拒绝链接、硬链接及非普通输出。原 30 项测试通过；新增 23 项后旧实现有 19 项失败，修复后 53 项通过。配置预检不等于跨两个文件的事务保证，也不声称完全消除并发竞争。

**本轮祖先检查修复：** `6cf2e4d618beec24350643224f5aa4c0e6e0f7fe` 修复命令刷新器从包根向上检查、先查询链接后方目录再拒绝的问题；改为从文件系统根向下检查。两项父级/更高层链接回归在旧代码稳定失败，修复后命令刷新 24 项及指令安装 31 项全部通过。正常 CMD 模板、认证、普通/YOLO 权限、Fast、扩展开关、模式副本和官方 0.164.0 工件均未改变。

**本轮账号转换器修复：** `3c0f043b2f3749c1492f30c87fa9d0925c7e121c` 修复导入账号 `type` 直接进入识别区域 HTML，以及 ZIP 的 UTF-8 文件名字节未设置编码标志、中文名被误解码的问题。仅补现有 HTML 转义及 ZIP 本地头/中央目录的 UTF-8 标志，不更改账号内容或转换格式。新增四项真实页面处理函数/ZIP 回归，旧代码稳定失败两项、修复后全部通过。既有 Windows 浏览器测试增加真实页面文本显示、无注入节点及 Unicode ZIP 检查，并保留原版本、渲染、截图、跨进程 Cookie 持久化和显式缓存清理检查。

**最终重新计数的三轮复查：** 发现转换器问题后停止尚未打包的 `40159811138`，此前三轮不再作为新修改的最终验收。第一轮对最新修复的源码副本重新执行 128 项 Python 回归、8 项浏览器策略、账号转换器 smoke 和四项 UI/ZIP 检查，均通过。第二轮重新执行 13 个独立 Python 进程场景、11 组代理/路径/发行清单边界；另以独立 Python HTML 解析器检查九类导入字段，以标准 ZIP 解码器检查八种多语言路径、原始内容和 CRC，全部通过。第三轮 Actions `40161313406` 在全新 Linux 和 Windows runner 检出上述同一转换器修复提交：129 项源码回归无失败/错误/跳过，8 项浏览器策略、转换器测试、101 份 Python 与 41 份 PowerShell 解析，以及 33 项模型参数、12 项权限显示、9 项登录输入保护、7 项登录流程和共享 URL 契约检查均通过；Windows PowerShell 5.1 和真实配套 Chromium 的新增页面/ZIP、截图、Cookie 持久化与清理检查也通过。129 与 128 的差异为完整 Git checkout 额外执行实际跟踪清单测试，不是重复引用旧日志。三轮均未发现新的可复现问题。

**发布门禁与边界：** 清理临时审核工作流并更新本记录后，既有 `02-verify-and-publish-portable.yml` 必须对最终提交重新执行 `check_set=full`；完整 Windows 启动链、中文/空格路径、权限、MCP、Python/Node、浏览器、干净 Git/LFS 打包及上传附件回读全部通过后，才允许发布 `v2026.10.25.1`。实际发布状态、来源提交和完整验证链接以对应 Release 为准，不覆盖 `v2026.10.25`。本次私有源码 artifact 已主动删除，不长期保留自动触发入口。测试只使用合成账号/传输/设备输入；真实账号刷新、全部在线 Agent/Host、提权沙箱及真实设备仍未测。三轮通过不代表所有场景绝对没有 Bug。

## 2026-10-25：SQLite 归属检查与发布复查

**PDF 手册库数据库保护：** 原归属检查在拒绝无关 SQLite 文件前先设置 journal_mode=DELETE，会改变既有 WAL 数据库；仅检查 table 也会误认领只有 view 的数据库。现先检查 application_id 和所有持久 schema 对象，确认是本工具库或空库后才设置日志模式；拒绝时不改写无关文件。只调整 PDF 手册库的数据库初始化顺序，不改转换内容、索引格式、认证、权限或官方工件。新增 7 项纯合成数据库回归，旧实现稳定复现 2 项失败，修复后 7 项通过，覆盖外部归属、视图库、WAL、空库、既有库和只读打开。修复后独立运行 40115142380 依次在全新 Linux 和 Windows runner 检出同一修复提交：102 项 Python 合成回归、源码解析与生产策略函数检查，以及现有 20 个 Windows 验证组全部通过；新增 7 项数据库检查也在包内 Windows Python 执行通过。第二轮未发现新的可复现问题；不等于所有场景无 bug，真实账号、在线 Agent/Host、提权沙箱及设备操作未测。本任务仅修复和验证，不构建或发布 Release。

## 2026-10-24：0.164.0 配套升级与配置兼容

**原因与结果：** 中断期间官方发布 [0.164.0](https://github.com/openai/codex/releases/tag/rust-v0.164.0)，Codex/Host 及配套助手、搜索程序成对更新；六个运行文件约 464.5 MB，官方 ZIP 摘要、PE 架构、许可证与完整布局已核验，保留原始 EXE 字节。继续省略 39 个语音文件和两份重复助手；固定身份、登录版本映射和模式副本同步。

**变量复核：** 44 个有效 `CODEX_*` 默认赋值仍有生产消费者，provider、Fast、扩展、文件凭证存储和默认 unelevated 沙箱映射继续有效。`realtime_conversation` 已成为 Removed feature，删除失效赋值；有效 App 语音/听写开关保持 false，TUI 的 `toggle_voice` / `toggle_voice_mute` 设为空绑定。上游仍可显示 `/voice`，本包不支持语音，不宣称已隐藏该命令。模型目录与上一版一致，Luna 默认仍为 medium。新增的 64 位 HKLM 固定策略键 `SOFTWARE\Policies\OpenAI\Codex` 的 `RequirementsPath` 会改变官方系统策略文件来源；启动器先检查该值名是否存在，未明确允许宿主策略时拒绝启动，不读取它指向的文件。显式允许宿主策略时保持上游行为。参见官方[系统策略加载](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/config/src/loader/mod.rs#L819)、[语音 feature](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/features/src/lib.rs#L432)和[默认 Windows 后端](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/windows-sandbox-rs/src/unified_exec/mod.rs#L59)。

## 2026-10-24：Windows 验证与 npm 目录边界

**Python 命令入口刷新：** 修正清理时仅凭 helper 文件名子串判断归属、误删用户自建或改写 CMD，以及当前 vendor 缺少入口元数据时误删原命令的问题；只删除与本工具生成内容逐字节一致且已无对应 vendor 的旧入口，无法确认的文件保留。替换暂存统一放当前包内 tmp，并拒绝链接/硬链接输出；正常 CMD 模板字节不变。本项不改 Python 依赖、启动器、认证、权限或官方工件。11 项新增合成回归中，旧实现有 6 项失败，修复后全部通过；本轮全部修复提交后依次用全新 Linux 与 Windows runner 复查，95 项 Python 合成回归、源码解析与生产策略函数检查，以及现有 20 个 Windows 验证组全部通过。验证运行 40110404921；本任务只验证和记录，不构建或发布 Release，不使用真实凭据。

**模型列表请求契约：** 修正生产 Invoke-Models 构造 client_version 查询参数、但 PowerShell 与 Python 双层白名单全部拒绝查询参数的联动错误。仅模型列表固定 HTTPS 端点可带单个数字三段版本；刷新/额度端点仍禁止查询参数，域名、端口、请求方法、请求体、敏感头与禁止重定向规则不变。共享 7 个合法和 26 个非法 URL 用例，Python 额外验证方法/请求体/头限制；PowerShell 直接调用实际模型/额度请求构造函数和实际双层校验，最终传输为合成 stub。旧 helper 的四个合法版本 URL 失败已复现，修复后专项通过；修复后的两阶段独立复查 40110404921 已通过，Python 与 Windows PowerShell 5.1 均验证共享 URL 用例和实际请求构造；不声明真实账号联网已测。

**账号输入异常保留：** 修正账号检查将文件访问/解析异常、缺失索引及 LoadError 统一送入失效凭据删除分支的问题；错误索引不再导致删除整个容器。两处输入失败分支改为 ERROR_KEPT，避免后续多账号 prune，并抑制异常详情；成功解析后缺少必需字段、明确服务端认证失效及网络错误的既有分类不变。9 项生产函数回归全部使用合成对象，网络与删除均为 stub；旧实现可复现错误分类，修复后专项通过。修复后的两阶段独立复查 40110404921 已通过，9 项输入异常回归也在真实 Windows PowerShell 5.1 执行通过；测试不访问真实账号或认证服务。

**模型指令安装入口：** 单独调用 `tool/codex-instruct.py` 时，旧实现会先解析入口祖先或输入链接再拒绝，并在 home/包根暂存写入文件。现先做词法规范化，再从文件系统根向下检查祖先与普通单链接包标记；输入、自定义 home 和本机配置在跟随链接目标前拒绝，实际 I/O 使用同一规范化路径。原子写入的独占暂存文件改为当前包内 `tmp`，失败只清理本次暂存，不动其他文件。不改指令内容、持久配置格式、认证、权限或官方工件。合计 19 项合成回归覆盖入口/输入/输出链接、先拒绝后探测、暂存范围、失败清理、正常安装和真实搬迁；新用例在修复前可复现失败，修复后 Linux 合成回归通过。修复后独立运行 40105103992 在全新 runner 检出提交复查，81 项 Python 合成测试、42 份 PowerShell 解析及 CLI/权限提示/扩展迁移与持久化等生产函数回归全部通过，未发现新的可复现问题。Linux/PS7 不替代 Windows；完整 Windows 验收和发行附件回读仍为发布前置条件，最终结果以对应 Release 与 Actions 为准。

**权限状态提示：** 修正 YOLO 仍显示 SAFE/work/tmp 及只读模式套用 workspace-write 网络提示的错误。显示优先按实际 sandbox 模式区分；YOLO 明确不提供包外写入或命令网络限制，只读不冒充宿主进程完全不写入。仅修改提示表达式并同步模式启动器，不改权限、网络、认证和二进制。新增 12 种生产表达式组合回归，与模式副本检查一起通过专项检查；修复后全新检出的源码及生产函数回归再次通过，未发现新增可复现问题；完整 Windows 验收与附件回读仍为发布前置条件，最终结果以对应 Release 与 Actions 为准。

**扩展配置生命周期复查：** 修正维护命令整体回写导致未启用的 MCP/Plugin 配置丢失，以及旧 config 首次迁移只保存在内存、后续启动被拒绝时丢失的问题。旧扩展先在包内 tmp 独占写入、刷盘并原子提交持久文件，成功后才删除旧生成配置；失败保留原文件，已有持久文件（包括空文件）优先且不在启动时重写。管理命令需显式启用对应类型，成功后只回写该类型，另一类不变；查看无变更不写回，删除最后一项不复活。同步模式启动器，不改认证、权限或官方工件。迁移失败、目标冲突、链接拒绝、重启恢复及真实维护 MCP add/list/remove 均纳入回归；迁移、回写和 CLI 参数专项显式接入正式 Windows 门禁。 修复后从新检出的提交再次核对启动失败恢复、命名空间回写、CLI、模式副本、固定版本变量与发行门禁，源码及专项回归通过，未发现新增可复现问题；Linux/PS7 结果不替代随后完整 Windows 发布验收。

**CLI 模型参数：** 修正 `-m=模型名` 把等号并入模型名的解析错误，使其与分离写法及 `--model=...` 一致；空值拒绝，插件子命令的 `-m` 仍是 marketplace 参数。继续修正先写 TUI 提示词再写模型参数时启动器漏读覆盖的问题：按固定版本命令名区分子命令与提示词，保留插件 marketplace 参数和 `--` 边界。同时将 TUI 提示词与子命令生命周期状态分离，避免 `Logout` / `MCP` 等大小写不同的提示词误触退出登录或扩展管理逻辑；真正的小写子命令继续受原有权限约束。33 项生产解析回归覆盖参数形式、顺序、空值及命令边界；中文搬迁场景用 `Logout` 提示词实际验证短参数、生成配置与原生客户端的一致性，不执行真实退出登录。修复后从全新检出独立复查源码、固定版本变量、模式副本与扩展迁移/持久化，并增加 23 项提示词/真实子命令边界验证，均通过；本轮未发现新增可复现问题。该复查使用 Linux/PS7，不代替完整 Windows 验收；最终发行仍须全量 Windows 检查和上传附件回读通过。

**收尾复核与发布门禁：** 按固定 0.164.0 上游 schema、feature 定义和当前生产引用复核 42 项字面量默认设置及 2 项派生路径，未将仅预留工具路径当作已安装功能。源码检查 40067858314 通过 97 份 Python AST、11 份 JavaScript 语法、38 份 PowerShell 语法、5 个 BAT 的 ASCII/CRLF 和模式副本检查；其中 PowerShell 解析在 Linux/PS7 执行，不代替 Windows 运行。正式工作流保留原有全量检查，补入真实 BAT/客户端完整启动回归，并以固定客户端的只读 features/list 检查生成配置的实际加载与关闭开关，避免仅靠 --version 推断配置有效。上传先创建 draft，重新下载三个附件、比对 SHA-256 并逐项验证 ZIP/来源清单后才公开为非预发布；测试、下载和验证材料只使用本次包内 tmp。最终发布结果以对应完整 Windows 运行及 Release 附件为准。

**完整启动补验：** 新增真实 BAT → 启动器 → 固定原生客户端的离线回归，发现 PS5.1 / .NET Framework CodeDOM 在含中文的包内临时目录编译失败。仅将编译入口改为当前 Windows Framework 自带 csc、Unicode 子进程环境和 UTF-8 参数文件；源码、输出和清理仍限本次包内 `tmp`，监督器 C#、Job、标准流、模式和凭据逻辑不变。Windows 专项运行 40066085104 的普通、中文/空格改名搬迁、旧根仍存在及维护入口三组启动与生成配置、继承/捕获标准流均通过；该任务最后的文档写回失败，不将任务总状态记为成功。修复已按通过测试的精确字节提交，完整启动检查纳入后续正式发布门禁。

**标准流回归修复：** 全量运行 `40056474654` 中，已知编译临时目录保留提示导致 stderr 精确匹配误报。测试现仅接受这条提示出现一次，保留 stdout、退出码及捕获模式的严格检查；新增 14 个正反例。不修改生产监督器，不丢弃未知诊断，不放宽发布门禁。修复后已通过 [Windows 全量运行 40064538870](https://github.com/rileyaaa/Codex-Portable/actions/runs/40064538870)，该次仅验证不发布。

**原因与结果：** npm 的用户/全局配置虽位于包内，上游仍会从工作目录向父层发现项目 `.npmrc`。六个 npm/npx 入口现统一使用包内 Node 和固定项目根，保留经校验的显式包内 `--prefix`，配置和缓存路径先校验后加载；不依赖增加环境变量来假定隔离。实际 bundled npm 配置加载、参数保留及 Windows 入口纳入发布回归。

**Windows 修复：** 账号检查 BAT 的菜单提示包含未转义的右括号，导致 CMD 在解析分支时中止；现正确转义，保留原菜单行为。首次直接运行浏览器时由监督器安全创建缺失的包内 `tmp`，不再依赖先运行 BAT。进程监督器保守保留未能安全删除的包内编译临时目录，提示改写到 stderr，避免污染 MCP 的 JSON-RPC stdout；残留可由“清理缓存”回收，不进入发行包。Windows 专用入口和进程监督继续通过独立测试验收。

**验证约束：** Windows 工作流使用与便携入口一致的包内/系统 PowerShell 模块路径，各组检查单独显示结果并设有限超时。实测纯 PowerShell 启动约 0.26 秒，首次加载文件系统模块约 25 秒；合成测试使用 60 秒有限等待，较长的多进程测试组另设 8 分钟上限，不以无限等待掩盖失败。BAT 合成测试超时时按本次 PID 回收子进程树，避免只杀父进程后阻塞临时目录清理。

## 2026-10-23：发布复查与打包

**精简决定：** 复核后没有可无损删去的大块内容。C/C++ PDF 开发文件及两份搜索程序最多约可省 10.5 MB 解压体积；用户明确选择保留现状，修复 bug 后发布。没有删除这些候选；测试保留在源码中，客户 ZIP 排除第一方测试、CI 和打包脚本，模式模板与转换器运行文件继续交付。

**修复：** 之前只在依赖安装器中禁用了宿主 pip 配置，普通 Agent 命令仍可能经 Windows 系统路径读取 `pip.ini`。根启动器、五个 BAT、子进程环境和生成的 shell 配置现统一固定 `PIP_CONFIG_FILE=nul`，模式副本同步；真实 bundled pip 加载器的合成回归验证普通和 isolated 模式下均不读取配置文件。

**边界复查：** 修复 PPT 多张缩略图派生文件、Poppler 可执行文件和 Android 映射/规则输入漏验链接的问题；登录 HTTP helper 移除未使用的文件参数，只接收启动器传入的标准输入。Windows 实测暴露 Android MCP 的中文 JSON 响应受默认码页影响，现统一通过字节流输出合法 ASCII/UTF-8 JSON，并覆盖低码页及无效 UTF-8 后恢复处理。官方账号默认改用设备码，避免系统默认浏览器写入宿主资料；原方式仅在明确设置 `CODEX_BROWSER_LOGIN_FLOW=system_browser` 后启用，失败不自动回退，模式副本同步。

**浏览器：** 固定资料改为 `cache/browser`，任务结束关闭进程并保留 Cookies/登录；“清理缓存”统一删除，并与浏览器通过独立锁互斥。修复固定 MCP 上游关闭连接未必关闭浏览器上下文的问题，由包装器显式持有和关闭上下文。只下载固定官方 Chromium ZIP，不额外安装 ffmpeg、winldd、ChromeDriver 或第二套浏览器。

**发行准备：** 新增打包器，仅接受已提交且干净的完整 checkout，拒绝私密路径、链接、Windows 文件名冲突和 LFS 指针，验证固定运行包身份；ZIP 生成后逐项检查内容摘要与 CRC，另产出来源清单和 SHA256SUMS。补齐官方固定版本的 LICENSE/NOTICE，保留原始字节。新增手动发布工作流，在 Windows 运行回归后打包，上传 draft 成功才转为正式 Release；不创建长期 artifact 或缓存，结束后清理本次 runner 文件。真实账号、在线 Agent/Host、提权沙箱与设备操作仍不属于该工作流的验收范围。

**发布要求：** GitHub API 已恢复访问；Windows 发布工作流及最终 Release 是否完成以实际运行和远端附件为准，不能将本地 ZIP、代码提交或工作流文件当作已发布。

## 2026-10-23：DBA/Python 用途精简

**原因与结果：** 本地主要使用文字 Agent、Python 爬虫和数据处理，编译频率低。移除 Go、PyInstaller 及其专用依赖、可再生 Python 字节码、uv/uvx/uvw 和两份重复沙箱助手，项目文件由约 1,146 MB 降为 807 MB，减少约 339 MB（30%）；按解压后的受版本管理文件统计，不含 Git 历史、用户状态和尚未下载的浏览器。Python、Node、Office/PDF、现有 Android 和浏览器脚本依赖保留，36 个 Windows Python 运行包的依赖关系闭合。

默认 unelevated 沙箱使用客户端内置执行路径；两个根目录助手用于 elevated 沙箱。保留它们是因为 TUI 提权入口仍可达，缺件时上游可能按裸文件名查找程序；仅删除已核对同根目录优先查找的资源副本。当时的 0.163.0 运行文件为六个、约 446.3 MB，固定清单和模式副本同步更新。

| 关联问题 | 最终处理 |
| --- | --- |
| 删除编译工具后仍导出旧路径、创建空工具目录 | 五个 BAT 和启动器清除继承的 Go/uv 变量，移除 PATH、缓存骨架及生成配置中的对应项；正常和 YOLO 四份模板同步 |
| 安装器会补回 PyInstaller 和大范围可选依赖 | 改用已有 Python/pip，固定现有 36 个版本；仅接受官方 PyPI wheel，完整依赖加 SHA-256 锁，安装和导入成功后才发布新锁 |
| pip 覆盖安装会保留旧版本元数据、替换整个 CLI 目录 | 补装前拒绝版本冲突、重复或额外发行包及无法归属的入口；固定运行集可同版修复，跨版本升级另用受控暂存副本，避免静默损坏用户后来添加的工具 |
| pip 隔离参数仍可能加载系统配置，安装入口漏查包根祖先 | 显式禁用 pip 配置文件并固定索引；完整祖先检查早于 marker 访问，安装前检查 Python 树中的链接 |
| 文本输入大小限制误用于大型 EXE marker | marker 只检查普通文件与链接；32 MB 上限仅约束锁输入，回归包含大型稀疏 marker 和超限报告 |
| 依赖安装器会重写 dist-info/RECORD，导致原始字节摘要误报 | 四个 RECORD 从已安装文件摘要中排除；149 个运行/许可文件、官方完整 wheel 和源码摘要继续校验 |
| 自定义 header 示例使用受保护的 CODEX_* 名称 | 改为普通变量名，验证生成的子进程环境实际接收配置中的 header 值 |

从官方 PyPI 成功解析全部 36 个 Windows x64 / CPython 3.14 wheel，并生成、验证候选哈希锁；只做解析，没有在 Linux 冒充 Windows 安装。综合回归及待验范围见文末。未新增项目说明文档。

## 2026-10-20：文字/Agent 精简与联动检查

**原因与范围：** 用户确定不使用语音；此前分项回归不足以覆盖新运行包、进程监督和工具入口之间的依赖。本轮核对固定版本上游的资源查找、沙箱助手缓存和原生变量消费点，检查第一方脚本并执行现有综合回归，不将离线检查称为 Windows 全流程验收。

**精简结果：** 删除语音专用的 39 个文件，减少约 19.4 MB；保留主程序、Code Mode Host、搜索和两种沙箱助手。当时生成配置关闭 `in_app_voice`、`in_app_dictation`、`realtime_conversation`；最后一项在 0.164.0 已移除，当前处理见最新升级记录。资源目录中的重复沙箱副本已在后续 DBA 精简中移除，当前布局和取舍见 README。

| 联动问题 | 修复结果 |
| --- | --- |
| 仅校验主程序/Host，未覆盖新布局的 metadata、搜索和沙箱资源 | 启动前固定 manifest 摘要并验证全部所列文件；固定清单原始字节，防止 Windows 换行转换破坏新摘要；检查沙箱状态树链接及可复用助手缓存，不读取沙箱凭据内容 |
| 任意 `CODEX_*` 可通过本机设置进入原生客户端 | 本机配置只接受已核对的启动器设置，拒绝原生日志、跟踪和安装路径等未经审核的变量；既有支持项保留 |
| MCP 前台进程未显式继承管道，桌面中文输出可能按错误编码解读 | 监督器只传递三个标准句柄，保留 Job 管理和捕获模式；桌面 worker 明确输出 UTF-8，新增 Windows 实际标准流回归入口 |
| 浏览器目录先递归后查链接，MCP 元数据可再次改变工作目录 | 先逐层验证再遍历；移除上游 `_meta.cwd`，输出路径固定成已校验绝对路径，新标签 URL 同样限制为允许协议 |
| Android 反编译入口存在语法错误，Python 守卫漏查祖先/悬空链接 | 修正三处插值；补齐固定包根、完整祖先、单链接 marker、越界先拒绝及搬迁测试 |
| Office 子进程部分状态目录仍可继承宿主环境 | 三套 helper 同步验证并重定向 AppData、ProgramData、Public、XDG 等目录，先验证再创建临时目录 |
| 缺少 OCR 工具后，增量构建永久复用失败结果 | 相同文件和参数下也会重试此前 `missing` / `failed` 页；成功缓存仍可复用 |
| Git 忽略规则未覆盖沙箱秘密和运行状态 | 排除沙箱数据、日志、会话、扩展私密配置及缓存目录；确认这些目录没有已跟踪文件 |

根脚本改动及语音限制已同步四份模式文件；未新增项目说明文档。当前测试范围、结果和 Windows 待验项统一维护在文末。

## 2026-10-20：常用与 YOLO 模式同步

**原因：** 四份模式文件仍保留旧客户端身份及扩展默认值；这些是需要持续同步的发行模板，并非冻结历史。

**结果：** 常用两份与根文件完全一致；YOLO 启动脚本同步，env 只保留 approval、sandbox、network 三项差异。`strict` 在两种模式中都相同，Fast 和扩展默认关闭。`never` + `danger-full-access` 可避免权限批准等待，但会关闭执行器文件写入沙箱；路径重定向仍生效，不能据此保证任意命令绝不越界。严格写入边界使用常用模式。无人值守还需预先完成认证并选择非交互启动。

## 2026-10-20：统一浏览器与限定应用调试

**原因：** ChromeDriver 与 Chrome 分别更新容易失配；多套浏览器/MCP 增加便携包体积，默认桌面 MCP 的操作范围又过大。

**结果：** 仅采用一套固定 Playwright 依赖，共用一份配套 Chromium。任务脚本、可选 stdio MCP 与 CDP 诊断复用同一安装；无 ChromeDriver、第二浏览器或 Chrome DevTools MCP。进程用户目录、profile、缓存和临时下载落包内，退出时关闭本次进程；资料保留与统一清理见上面的维护约定。MCP 过滤任意 Node 执行、上传、安装、配置及客户端重定向根目录；任务脚本入口仍是受当前权限约束的代码执行，不能冒充不可信脚本沙箱。Windows 桌面入口使用系统 UI Automation，只读指定 PID 主窗口的有界树，修改动作需要额外开关，未安装通用 Windows-MCP。

**交付状态：** JS 依赖约 18.7 MB、185 个文件已安装并记录摘要；10 月 23 日通过官方 CDN/Google 存储取得唯一配套 Chromium，305 个文件约 458 MB（官方 ZIP 约 207 MB），来源和摘要记录在 browser-manifest.json。浏览器 payload 使用 Git LFS，发行 ZIP 包含实际文件。未使用下载 Actions 或生成临时 artifact；手动下载工作流保留为备用。

**附带修正：** PDF ZIP 摘要写回现有 `SHA256.md` 的最近导出记录，ZIP 内仍只含 Markdown，不自引用最终 ZIP 哈希，也不增加项目说明文档。复现了 Windows `core.autocrlf=true` 会改写新增官方 Python 文本文件、导致摘要失配的问题；`.gitattributes` 现固定 Python、Playwright 和客户端资源的原始字节，不改动上游内容。

## 2026-10-20：技能去重、任务开关与 PDF 检索

**原因：** Android 外层技能与插件内 17 组流程完全重复，维护模式会自动激活用户 MCP；大量 PDF 全文进入上下文造成额外开销，Office 技能存在“依赖已安装”等不准确说明。

**结果：** 删除 43 份重复 Android 文件，保留插件内完整流程与外层精简入口；保留 `mumu-adb` 和可作为离线模板资料的 OpenAI templates，移除不相关的 plugin-management 缓存及生成字节码。Plugins/MCP 默认关闭并增加本次会话开关；关闭时仍完整保存用户扩展配置。默认和自定义模型指令都加入任务授权规则，Fast 保持关闭。

Office 保留现有 OOXML/Python 工作流，改为用户模板优先、按需选择模板资料、检查实际渲染结果，缺失渲染工具不宣称成品已验收。新增 `pdf-library` 适配成熟 PyMuPDF4LLM：按页转换、原文字补充、SHA 增量更新、限长检索/读取与纯 Markdown ZIP；文字、代码、OCR 和视觉结构分别报告。安装经官方 wheel 与 RECORD 校验的 Windows PyMuPDF、PyMuPDF4LLM、tabulate、defusedxml，来源及文件摘要见 `tool/optional-python-manifest.json`。

**修复：** APK MCP PowerShell 入口的 `$Label:` 插值和路径拆分正则原本无效；已修复。MCP 启动增加明确任务开关，并提前检查完整路径祖先、链接和输入边界；不自动注册、启动或连接设备。

**验证：** 11 项 Android 子进程/路径测试、13 项真实合成 PDF 行为测试、11 项 PowerShell 扩展策略测试通过。PDF 测试在 Linux 使用匹配版本上游引擎；Windows payload 的摘要/架构检查不代替 Windows 实际运行。未执行 MuMu、Appium、真实桌面操作或用户文档转换。

## 2026-10-20：统一项目文档

**原因：** 项目使用、变量、维护规则和版本记录分散，存在重复、历史状态混入当前说明及过多过程描述。

**结果：** 文档归并为四个入口，维护限制集中到本文件开头；README 统一说明 Git LFS 工件获取、五个 BAT、配置、目录搬迁和换电脑迁移；工具文档集中下载来源、布局和更新；转换器保留独立说明。原根级规则、变量清单和变更日志的有效内容已合并，不再单独维护；功能性技能和第三方文档不因本次整理删除。开发记录改为日期、原因、结果及验证，过时事实直接更正。

**文档核验：** 清点 358 份 Markdown，读取并筛查项目维护约束；完整审阅项目主文档及相关技能规则。第三方文档用于确认归属与引用，不宣称逐字审计其全部技术内容。修正两份 Appium 技能的维护文档入口；转换器文档按实际代码区分预览脱敏、JWT 展示和静态离线说明。

## 2026-10-20：0.163.0 升级与变量兼容

**原因：** 原 0.156.1 runtime pair 需要升级；部分变量虽有声明，但未传到实际调用，或生成了过时配置值。

**结果：** 从 [官方 rust-v0.163.0](https://github.com/openai/codex/releases/tag/rust-v0.163.0) 的完整 Windows x64 ZIP 成对更新 Codex/Host，补齐沙箱及搜索资源；按当前文字/Agent 用途省略语音专用目录。仅把 metadata 的入口名称适配为 `codex.exe`；保留的官方二进制字节不变。来源、ZIP 摘要、实际文件及明确省略组件以 [runtime-manifest.json](tool/runtime-manifest.json) 为准，启动器和登录版本映射同步更新。

| 原因 / 兼容点 | 最终处理 |
| --- | --- |
| Python 登录后端忽略连接超时变量 | 将 `CODEX_LOGIN_JSON_CONNECT_TIMEOUT_SEC` 传入 requests 连接超时，默认 8 秒、上限 30 秒且不超过请求总限；PowerShell 后端仍只有整体超时 |
| 菜单开关拼写错误被静默当作 false | `CODEX_STARTUP_INTERACTIVE` 使用严格布尔解析，非法非空值报错 |
| Fast 配置使用旧值 | 改为 `service_tier="priority"`，关闭时仍明确生成 `default`；旧 `fast` 仅是上游兼容别名 |
| Luna 目录读取失败时默认档位过时 | 回退改为 `medium`，与本版本 bundled 目录一致 |
| 新版优先解析资源目录中的 Host | 对存在的资源目录 Host 追加路径及固定 SHA 校验，避免只校验根文件 |
| 旧 WebSocket feature 已移除 | 保持 provider 的 `supports_websockets` 映射，不恢复 `responses_websockets` / `responses_websockets_v2` |
| 工具变量被误当成安装或启用证明 | 明确 `ANDROID_SDK_ROOT` 为兼容别名；独立 ADB 不等于完整 SDK，预留 Java/Office 等路径不表示已有程序 |

核对覆盖 43 个显式 `CODEX_*` 设置。判定依据包括 [配置 schema](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/config.schema.json)、[Provider 定义](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/model-provider-info/src/lib.rs) 和 [feature 定义](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/features/src/lib.rs)。`CODEX_*` 多数由启动器翻译，不因官方没有同名环境变量就认定失效；官方模式忽略自定义 modality/context 是设计约束，Apps/Fast/模型权限仍取决于账号和上游。

## 2026-10-20：搬迁与目录边界修复

**原因：** 正常启动已按脚本位置派生包根，但部分辅助工具仍信任旧环境变量，文件链接及 bootstrap 检查顺序存在遗漏。

| 问题 | 结果 |
| --- | --- |
| 旧 `CODEX_INSTALL_DIR` 可把 Office/PDF 引向仍存在的旧包 | 7 个 helper 改为从自身脚本布局定位根，验证 marker、脚本和完整祖先链；同步三套 Office 副本 |
| 临时目录 category 可带 `..`，部分检查先跟随链接目标 | 提前拒绝越界/带 anchor 的工具与临时分类路径，拒绝悬空链接，避免先查询包外目标 |
| 模型指令文件缺少硬链接输入检查 | 读取内容前调用 `Assert-PortableRegularInputFile`，链接输入被拒绝且不生成指令文件 |
| BAT 在完整祖先检查之前创建目录 | 五个根 BAT 的首次检查改为纯 CMD 遍历至卷根，早于 `cd/mkdir`；后续 PowerShell 校验保留 |
| MuMu 默认检查宿主用户和系统 Temp | 默认限包内 ADB 状态与日志；包外故障诊断按具体授权，仅检查必要元数据；包外删除须有对应授权 |
| Maven bootstrap 路径含空格时缺少内部引号 | 五个 BAT 对齐启动器已有的带引号赋值；这是初始化一致性改进，未证实原 Codex 会话中发生 Maven 故障 |
| Host 回归使用系统临时目录 | 改为仓库 `tmp` 下独立 fixture，隔离子进程临时状态并仅清理本次文件 |

**保留的限制：** 自定义 MCP/插件配置正文不会自动迁移，旧绝对路径需人工核对。直接绕过 BAT 启动 PowerShell 可能先使用宿主缓存；`tool/setup-tools.ps1` 已补完整祖先保护，Android 路径/bootstrap 的直接入口尚无同等保护。应从已验证的正常/维护入口使用，不经 junction 直接调用；直接入口场景仍待 Windows 专项验证。

## 验证结果与待验范围（2026-10-26）

[完整 Windows 运行 40253783757](https://github.com/rileyaaa/Codex-Portable/actions/runs/40253783757) 对 `8e09466f` 执行全部发布门禁并通过，正式发布 [v2026.10.26](https://github.com/rileyaaa/Codex-Portable/releases/tag/v2026.10.26)。192 项 Python 回归、34 项 CLI 参数、完整 BAT/原生客户端及真实 Chromium 均通过；上传后回读三个附件，逐项验证 8,689 个客户文件，排除 48 个开发文件。Actions 临时 artifact/cache 为零。本地 Linux 检查明确跳过 Windows 原生执行项，不代替此 Windows 结果。所有样本为合成数据，不读取真实凭据。

| 检查 | 结果与范围 |
| --- | --- |
| Python unittest discovery | Windows 192 项通过：便携路径、HTTP、运行包、Android、Office/PDF、固定依赖、模式副本、pip 隔离、浏览器安装与发行 ZIP 校验 |
| `test_portable_config.ps1` | 最新 Windows 全量运行中 15 项通过，包含固定 0.164.0 客户端实际导出目录；离线无导出输入时另两项明确跳过 |
| `test_portable_paths.ps1` | 14 项通过：真实加载 env.ps1，覆盖 15 个派生路径、中文/空格、旧根、无关 cwd、移动目录及受保护/未审核变量；另验证真实启动器函数清除 Go/uv 变量、保留 Python/Node 路径、转发 header，并将 pip 配置禁用传到子进程和 TOML，不执行整个启动链 |
| `test_python_setup.ps1` | 4 组通过：实际 pip 参数、配置禁用与子进程变量筛选、修复范围拒绝早于任何 pip 调用、完整祖先链接拒绝；不执行安装 |
| 官方 PyPI wheel 解析 | Windows x64 / CPython 3.14 的 36 个固定版本解析成功，候选锁生成和校验通过；未执行 Windows 安装 |
| `test_instruction_paths.ps1` | 3 项通过：普通文件成功，真实硬链接/符号链接被拒绝；Linux 仅替换 Windows 路径包含判断，链接检查及写入用生产函数 |
| `test_extension_policy.ps1` | 12 项通过：Fast/扩展默认关闭、语音配置关闭、维护模式、显式开关、命名空间筛选、配置保留及两条模型指令生成路径 |
| `test_runtime_preflight.ps1` | 10 项合成工件检查通过：清单先校验、文件缺失/替换/链接、沙箱缓存新旧与状态硬链接；不执行客户端，不读取真实凭据 |
| `test_automation_paths.ps1` | 通过：子进程目录重定向、参数引用、越界/硬链接、先查祖先再遍历、只清理自有目录、任务开关与 PowerShell 解析；没有启动 Windows 程序 |
| `test_automation_process.ps1` | Windows 全量运行 40064538870 及中文编译修复专项均通过；包含 14 个严格诊断正反例和真实继承/捕获标准流 |
| `test_automation.js` | 10 项通过：实际固定版 MCP 初始化与工具筛选、拒绝未选任务、路径边界、禁止能力、依赖字节摘要；不启动浏览器 |
| `test_portable_npm.js` / `test_npm_entrypoints.ps1` | 10 项真实 npm 配置回归通过；Windows CMD/PowerShell 入口、显式项目根与包外拒绝已通过 |
| `test_system_policy.ps1` | 8 项合成检查通过：固定 Registry64/HKLM、值名存在性、授权 gate、异常拒绝与句柄回收；不读真实策略 |
| `test_browser_login_flow.ps1` | 7 项离线检查通过：默认设备码、显式系统浏览器、非法值与失败无回退 |
| `test_bootstrap_paths.ps1` | 15 个 Windows BAT 普通/junction 用例通过；测试入口环境与链接拒绝，不代替完整登录链 |
| `test_launcher_smoke.ps1` | 普通、中文/空格搬迁及维护入口三组真实 BAT/原生启动已通过专项 40066085104；新增客户端配置消费断言与全部正式门禁一同复验，不使用真实账号 |
| `test_browser_smoke.ps1` | Windows 实际 Chromium 在搬迁后的合成包启动、截图、关闭后重新打开并保留 Cookie，随后由缓存清理器删除资料且保留工作输出；通过 |
| 原生客户端与模型目录 | Windows Codex 0.164.0 启动及 `debug models --bundled` 导出通过 |
| 语法、格式与 BAT 静态检查 | 第一方 PowerShell 解析和 Python AST 检查通过；5 个 BAT 的 ASCII/CRLF、Go/uv 变量清除、pip 配置禁用和祖先检查先于目录创建检查通过。按 CRLF 规则检查项目差异；保留的官方 EXE/DLL、Playwright 依赖及原始 npm CLI 字节未改写；六个 npm/npx shim 为便携入口 |
| 转换器 smoke / static audit | 通过；一个合成 fixture、四账号、17 种输出，命令见子项目 README |

以下开发测试仅随 GitHub 源码提供，客户发行包不附带。在源码包根使用 Windows PowerShell 5.1 复验：

```powershell
.\tool\python\python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
powershell.exe -NoProfile -File .\tests\test_portable_config.ps1
powershell.exe -NoProfile -File .\tests\test_portable_paths.ps1
powershell.exe -NoProfile -File .\tests\test_instruction_paths.ps1
powershell.exe -NoProfile -File .\tests\test_bootstrap_paths.ps1
powershell.exe -NoProfile -File .\tests\test_extension_policy.ps1
powershell.exe -NoProfile -File .\tests\test_runtime_preflight.ps1
powershell.exe -NoProfile -File .\tests\test_python_setup.ps1
powershell.exe -NoProfile -File .\tests\test_automation_paths.ps1
powershell.exe -NoProfile -File .\tests\test_automation_process.ps1
.\tool\node\node.exe --test .\tests\test_automation.js .\tests\test_portable_npm.js
powershell.exe -NoProfile -File .\tests\test_browser_login_flow.ps1
powershell.exe -NoProfile -File .\tests\test_system_policy.ps1
powershell.exe -NoProfile -File .\tests\test_npm_entrypoints.ps1
powershell.exe -NoProfile -File .\tests\test_browser_smoke.ps1
```

配置回归可用匹配客户端的 `debug models --bundled` 成功导出到包内临时 UTF-8 JSON 后，传入 `-BundledModelsPath` 启用另两项检查；先检查导出退出码。Windows 链接回归需 NTFS，创建符号链接可能需要 Developer Mode 或相应权限；Python 无此能力时明确 skip，PowerShell 指令测试会报错，都不算通过。

**真实使用待验：** 新盘符、中文/空格目录下的完整正常/维护会话及跨电脑迁移；真实 Agent/Host 工具调用与实际命令环境；Python 安装器的真实重装；授权条件下的三种登录模式、刷新凭据、代理和 Windows 沙箱。合成 NTFS、BAT、进程与浏览器检查已覆盖相应自动化行为，不代替上述完整使用流程。语音已排除，不再列为待验功能。旧版本的历史验收记录不代替 0.164.0 的实际结果，也不据离线测试宣称项目没有其他 bug。

**已知实现注意点：** PS5.1 的 `File.Replace`、泛型集合和原生空参数传递曾有兼容问题，后续改动应保留对应处理；认证多文件切换依赖 transition/logout 标记与 snapshot 归属，不可猜测回收；缺少 Host 时恢复匹配完整布局，不能用关闭 Code Mode 作为修复。当前 checkout 不包含历史 checker/updater 套件，不引用不存在的脚本或把旧版本哈希当成当前身份。
