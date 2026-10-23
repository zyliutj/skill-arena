# 远程运行与本地交付

## 开始时决定保存位置

1. 调用 `python scripts/delivery.py detect`，结合当前任务提供的执行主机信息判断 local/remote。SSH 变量是远程证据；没有变量只能得到 unknown，容器或 Linux 本身都不证明远程。已知主机信息时传 `--context local` 或 `--context remote`。不读取、输出 SSH 变量中的地址或凭据。
2. 读取数据根 `delivery-preferences.json`，按客户端标识选择本地根目录。首次未指定时询问一次目标目录，并继续独立工作；已经授权的目录无需重复确认。不要把个人 Windows 路径固化在公共 skill 中。
3. 远程运行时检查是否已有能访问用户电脑的映射目录。仅目录存在不足以证明它位于用户电脑；结合已配置挂载或用户确认的映射验证，再做临时写入/删除探测。可用时将本轮最终交付目录设在映射路径，直接在那里 export。计算、中间文件与快照仍留远程。
4. 没有映射时，在远程生成交付包，再通过现有已授权文件连接器或从本地执行 pull 同步。不自动建立新反向 SSH、开放端口、上传公共仓库或使用第三方中转。传输通道不可用则记录 remote-only，交付准确远程路径与阻塞原因；不能声称保存到本地。

配置示例（只存数据根，不提交仓库；客户端键由当前主机上下文确认）：

```json
{"clients":{"my-laptop":{"local_root":"D:/Research","mount_on_remote":null}}}
```

可用 `python scripts/delivery.py configure DATA_ROOT CLIENT_ID ABSOLUTE_LOCAL_ROOT` 保存偏好，已有挂载时加 `--mount VERIFIED_MOUNT_PATH`。保存配置不代表连通性已验证。当前附件阈值固定 2 MiB。不要凭服务器 hostname 推断客户端身份，多电脑偏好分开保存。未知客户端时询问，不随意选第一个。

## 报告优先交付

```sh
python scripts/delivery.py export RUN NEW_BUNDLE
python scripts/delivery.py sync BUNDLE ABSOLUTE_LOCAL_OR_MOUNTED_DESTINATION
```

- export 创建新版本目录，完整 Markdown/TXT 正文始终收录；其他已登记附件 ≤2 MiB 随包传输。更大的附件展示大小、源主机位置与“尚未同步”，不塞进 HTML。使用 `--full` 可包含所有已登记附件，但仍不带缓存、快照或中间文件。
- 本地运行正常报告继续保持单文件模式；只有交付包采用报告优先模式。交付报告正文可独立阅读，原件下载使用包内相对链接；先收到报告时链接可能尚未就绪，查看回执。
- 只导出 mapping.json 中登记的产物；不用递归复制整个运行目录。运行记录仍保留在执行端。任务需求和引用仍可阅读。
- sync 支持本地或已挂载路径，按 SHA256 跳过相同文件，使用临时文件及原子替换，最后写 delivery-receipt.json。遇到目标已有不同内容时停止，改用新版本目录，防止覆盖用户修改。失败可重试，不删除远程原件。
- 改动后的成果用新交付版本；同一版本可重试并跳过已传文件。用户希望仅追加某个大附件时，协调者用已授权连接器按清单路径传输并校验，或者生成 `--full` 新包。不能把报告中的远程绝对路径当成本地链接。

## 从本地通过 SSH 拉取

在**用户电脑**执行（不是服务器）：

```sh
python scripts/delivery.py pull EXISTING_SSH_ALIAS /absolute/bundle/path ABSOLUTE_LOCAL_DESTINATION
```

pull CLI 当前支持 POSIX 本地客户端，需要本地可用 rsync 和已配置 SSH 主机别名；使用已有认证和严格主机密钥检查，不提示密码、不关闭验证。脚本不配置 SSH。Windows 本机使用已有文件连接器或挂载目录，不直接运行 pull，不自动安装依赖。此 CLI 限制远程路径为 ASCII 字母、数字、`_ . / -`；其他路径用连接器或挂载方式。

先获取清单和报告，校验后立即放入本地目录，再传附件；每文件有 300 秒超时，传输可从旁边的 `.任务名.arena-transfer` 缓存重试。协调者在后台运行较慢传输并持续报告进度，不等待长工具调用后才回应。delivery-progress.json 区分 report-ready 与 verified；receipt 仅在全部选定文件校验成功后写入。清单不能改写本地目录之外的路径。

交付时给出本地报告路径、远程原件位置、未同步附件数量及实际状态。只有本地写入且校验完成才称“已保存到本地”。没有真实远程传输测试时，明确区分单元测试与真实验证。
