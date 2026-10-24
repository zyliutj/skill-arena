# 用户选择后的临时反向报告传输

仅用户在无法直接传输时明确选择“通过反向连接传输”后实施。这里预写流程，不会自动建立连接。机制：用户电脑发起 SSH 到已有远端别名，`-R` 将服务器回环端口转发到本地回环接收器；服务器随后向该端口上传报告。不需要本机公网 IP 或安装本机 SSH 服务。OpenSSH 参数依据：[ssh(1) 的 -R](https://man.openbsd.org/ssh#R)。

## 前置检查

- 能在本地运行 Python 与 SSH，能用已有主机别名连接远端；服务器允许 remote forwarding，已有主机密钥可核验。没有本地执行通道时不能仅靠远端代理凭空建立反向通道，给用户本地操作步骤并保持等待/阻塞状态。
- 确认目标客户端、首次路径规则得到的 ROOT、任务子目录和最终报告 SHA256/大小。报告上限 64 MiB；超过时先减少非正文附件或改用其他已授权通道，不截断正文。
- 使用任务 tmp 子目录保存一次性 token，限制为当前用户可读（Windows 检查 ACL，必要时只改这个新建临时目录的 ACL）。token 不写入聊天、日志、命令行参数或全局记忆。

## 操作模板

以下大写参数必须替换为已验证的值，不直接原样执行。

1. 本地后台启动接收器，Windows 使用 `Start-Process -WindowStyle Hidden` 或支持的后台执行器，记录 PID 和日志：

```sh
python scripts/reverse_receiver.py LOCAL_TASK_DIRECTORY SOURCE_SHA256 SOURCE_BYTES LOCAL_TMP_TOKEN_FILE --port 0 --timeout 600
```

读取输出中的实际本地端口 `LOCAL_PORT`；只监听 127.0.0.1。接收器只允许带随机 token 的 POST /report，核对预先固定的大小和哈希，只写 report.html；不提供目录读取或任意路径写入接口。成功后写本地验收记录并退出，失败/超时清理 token。

2. 选一个未占用的远端高位端口 `REMOTE_PORT`，本地启动独立短期 SSH 子进程并记录 PID：

```sh
ssh -N -T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 127.0.0.1:REMOTE_PORT:127.0.0.1:LOCAL_PORT EXISTING_REMOTE_ALIAS
```

不得启用 GatewayPorts、绑定 0.0.0.0、关闭密钥检查或改动现有 Codex 隧道。用已有远端会话检查该监听确为回环；若服务端配置将其扩大绑定则立即停止本次隧道。端口冲突换一个空闲端口；策略禁止时报告原因，不改服务器策略绕过。

3. 将 `reverse_send.py` 上传到远端任务 tmp（已有则复用）。由本地读取 token 文件，通过**已有加密 SSH 会话的标准输入**传给以下远端命令，不作为命令行参数/环境输出：

```sh
python REMOTE_TMP/reverse_send.py REMOTE_FINAL_REPORT REMOTE_PORT
```

协调者用本地子进程 API 将 token + 换行写入该 SSH 进程 stdin；构造远程命令时逐参数按 POSIX shell 引用，不使用字符串拼接注入用户路径。无安全 stdin 传递能力则停止并解释，不打印 token 让用户复制。发送器仅连接远端 127.0.0.1，不经过 HTTP 代理。

4. 本地读取 `local-verification.json`，并调用 `delivery.py verify-local` 对最终源哈希再次核验；给用户本地报告链接。远端 HTTP 200 不能独立替代本地验收。
5. 无论成功失败，终止本次创建的精确 SSH PID 和接收器 PID，删除本次 token，确认本次监听已关闭；不要 killall ssh，不删除用户原件，不影响既有隧道。记录连接方式、耗时、状态，不记录秘密。

失败时只对端口冲突/短暂断线重试一次。仍失败则说明阻塞并再次提供“自行下载文件，无需 Codex 帮助”，不能自动替用户选择。不创建长期后台任务，不要求服务器获得用户电脑的通用登录权限。
