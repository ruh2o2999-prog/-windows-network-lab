# 技术来源与变更记录

从既有真实成功路径中抽取，重新参数化：
- `tools/segmented_transfer.py` 取自已验证的 R104 `segmented_private_transfer.py`，协议名称改为 `generic-segmented-aesgcm-v1`，功能仍是各段随机 AES256-GCM + RSA3072 OAEP-SHA256。
- `tools/test_segmented_transfer.py` 来自 R104 的 19 测试，已删除仅对 Kiwi MV2 manifest 的断言，允许任意合规 ZIP。
- `network_fixture_server.py`、`network_reconcile.py`、`test_network_reconcile.py` 来自 R104 真实 HTTP 基准与核对器，测试路径从 `/r104/api/` 改为 `/probe/api/`。
- `android_http_fixture_probe.py` 来源于真实 Android 受控 HTTP 测试，Android 包名改为 `ANDROID_PACKAGE`。
- `android_smoke.py`、`verify_archive.py`、Android CI 示例和通用销项规则由前期实际工作流改为参数化范例。

历史运行：R102 Canary Runs 43150601023/43151252266；R103 正式运行 43155035169/43156023346；R104 安全传输 43158599253，HTTP 测试 43164415061，验证器 43165394176。

**这些历史实验没有验证“任意 App 都可安装”或“任意导出格式都可解析”**。新项目必须根据自己的 APK/文档与实际回读验收。
