# 可复用软件研发验证工具包 V1.0

**定位：通用研发能力，不是 Kiwi 插件工程。**
它将 Android 虚拟机冷启动、真实 HTTP 请求基准、ZIP/HAR/Trace 内容核对、私有工件加密交接和原编号销项规则合并成一个交付包。插件、APP、软件自身源码和用户敏感数据**不在本包内**。

## 最短使用路径

1. 安装 Python 3.12+：`python -m pip install -r requirements.txt`
2. 检查语法：`python -m compileall -q tools/`
3. 生成公开合成测试包：`python tools/make_test_zip.py --out /tmp/universal-synthetic.zip`
4. 加密分段回归：`python tools/test_segmented_transfer.py --source /tmp/universal-synthetic.zip --report /tmp/crypto-tests.json`；期望 **19/19**。
5. 三套导出核对器回归：`python tools/test_network_reconcile.py`；期望正例 **10/10**、五类反例正确拒绝。
6. 独立 HTTP 服务器：`python tools/network_fixture_server.py --port 18764 --log out/received.jsonl`，在浏览器中访问 `http://127.0.0.1:18764/`。
7. Linux/Android AVD：先复制 `templates/android-avd-template.yml.txt` 为项目 CI 工作流、填写自己的 APK 来源和包名；模拟器 API30 + google_apis + x86_64 + KVM 的路径已在先前项目跑通。
8. 实际导出核验：将软件导出的 ZIP 与独立服务器日志、观察开始结束时间交给 `tools/network_reconcile.py` 的 `reconcile(zip, host_log, start_ns, end_ns, output)`，不要仅按 ZIP 存在判 PASS。
9. 按 `templates/acceptance_ledger.csv` 记录原编号、版本哈希、环境、Run ID、截图、实际证据和结论。

## 目录

- `tools/android_smoke.py`：安装/启动/截图/XML，**不代表业务测试通过**。
- `tools/android_http_fixture_probe.py`：ADB reverse + Android 浏览器发起受控请求，包名从 `ANDROID_PACKAGE` 环境变量读取。
- `tools/network_fixture_server.py`：可观测的本地 HTTP 真值服务，4 条不同路径含 404。
- `tools/network_reconcile.py`：合并参考请求、HAR、Trace、服务器日志进行结构和路由覆盖校验。
- `tools/test_network_reconcile.py`：已知正常与缺请求/错状态/缺 Trace/服务端缺失等反例。
- `tools/segmented_transfer.py`：各段独立 AES-256-GCM 随机密钥 + RSA3072 OAEP 封装，可信原始 SHA/会话必须由接收端独立固定。
- `tools/test_segmented_transfer.py`：19 个正反例回归。
- `tools/verify_archive.py`：ZIP CRC、条目、哈希核验。
- `templates/`：通用 CI 示例和销项表。
- `docs/`：验收纪律、可移植范围和已验证来源。

## 复现证据与边界

- Android 官方 Kiwi x64 + Android 11 API30 `google_apis` + GitHub hosted runner/KVM 的可运行路线，实证 Run 43150601023、43151252266、43155035169、43156023346。这里提到 Kiwi 仅为**历史验证对象**，本工具包不包含 Kiwi 安装包和业务代码。
- 通用 HTTP 真值基准的前身 Run 43164415061，后来核验程序 43165394176。
- 加密传输的前身 Run 43158599253，真实跨 Runner 私有文件解密一致性已经验证；本包只附通用实现及合成数据测试。
- **改为通用命名、参数和目录后的版本要以本包 CI 重新回归结果为准**，不能把以前项目的历史 PASS 自动等同于新项目 PASS。
- 当前网络核对器是结构、路由覆盖和状态控制基线，不等于逐事件数量、响应主体、时序和媒体流完全一致；更严格的专项验收必须新增测试。
- ZIP/MD5/SHA256/CRC 是文件完整性证据，不能证明运行功能完整。
- Google Drive 的完整项目备份应是未加密原工程（可按上传限制分卷）；公开 CI 的私有工件传输才按需使用分段加密。不得把私有密钥/明文放入公共 Git、日志、Artifacts。
