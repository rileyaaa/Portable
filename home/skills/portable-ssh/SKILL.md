---
name: portable-ssh
description: Use only when the user explicitly authorizes SSH to a specified server or SFTP transfer. Do not connect, probe, trust hosts, execute remote commands, or transfer files during skill discovery.
---

# 便携 SSH / SFTP（Paramiko）

使用包内 Python 调用 tool/portable-ssh.py，**不使用宿主 OpenSSH、~/.ssh、SSH Agent 或全局 Python**。仅操作用户本次明确指定并授权的主机、用户名、命令、远端路径或文件。SSH 命令可能修改远端服务器；用户只授权读取时不得执行写操作。

首次使用先验证包内 tool/python/python.exe 能导入已验收的 Paramiko 5.1.0 及依赖。当前功能源代码可能先于 Windows 依赖载荷提交；导入失败则报告尚未安装，不得回退宿主 Python，也不得自动在线安装。

所有本地 SSH 文件都在 work/ssh：
- keys/：私钥及 .pub，keygen 默认提示设置私钥口令
- known_hosts：仅在用户提供**独立可信渠道核验过的 SHA256 指纹**后固定服务端公钥
- uploads/：SFTP 待上传的本地文件
- downloads/：下载的远端文件

work/ 已被 Git 忽略、客户发行包排除。不要把密钥、口令、私有 known_hosts、日志和下载文件复制到 home/skills、tool、Git 提交或交接报告。禁止复制宿主 ~/.ssh 或导出 SSH Agent 的密钥。Windows 目录权限/ACL 仍需由用户维护；不要声称目录重定向能抵御拥有同一 Windows 用户权限的恶意进程。

首次连接（example.test、用户名与指纹均仅为占位符）：

1. 当前用户授权后才生成密钥，按提示输入私钥口令：

~~~powershell
.\tool\python\python.exe -B tool\portable-ssh.py keygen --name id_ed25519
~~~

2. 将 work/ssh/keys/id_ed25519.pub 的公钥内容按用户授权方式部署到指定远端账号。绝不自动替远端修改 authorized_keys。

3. 观察远端主机指纹：

~~~powershell
.\tool\python\python.exe -B tool\portable-ssh.py probe --task-authorized --host example.test --port 22
~~~

4. 用户通过可信渠道**独立核对**服务端指纹后，明确确认并固定：

~~~powershell
.\tool\python\python.exe -B tool\portable-ssh.py trust --task-authorized --host example.test --fingerprint SHA256:经核对的真实指纹
~~~

仅通过刚才的 probe 输出获取指纹，不构成可信核验。主机密钥变化时应停止，由用户确认轮换；不允许 AutoAddPolicy 或忽略密钥错误。

授权后的示例：

- 远端只读命令：

~~~powershell
.\tool\python\python.exe -B tool\portable-ssh.py exec --task-authorized --host example.test --user dbuser --key id_ed25519 --ask-passphrase --command "uname -a"
~~~

- 将远端日志存到 work/ssh/downloads/：

~~~powershell
.\tool\python\python.exe -B tool\portable-ssh.py get --task-authorized --host example.test --user dbuser --key id_ed25519 --ask-passphrase --remote /var/log/example.log --local logs/example.log
~~~

- 将 work/ssh/uploads/script.sql 传到用户授权的远端路径：

~~~powershell
.\tool\python\python.exe -B tool\portable-ssh.py put --task-authorized --host example.test --user dbuser --key id_ed25519 --ask-passphrase --local script.sql --remote /tmp/script.sql
~~~

SFTP 默认拒绝覆盖已有目的文件；确需覆盖必须明确使用 --overwrite。私钥口令通过终端交互输入，不在命令行、环境变量或报告内保存。无法安全交互时说明限制，不能自行改成空口令或泄露口令。

远端执行、上传与下载属于真实网络操作，不能将用户对某个服务器的访问授权泛化到其他主机。不要自动扫描地址或批量登录。真实联网功能测试使用用户明确授权的目标；回归测试优先离线 mock 和本地临时 SSH/SFTP 服务。
