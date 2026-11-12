# Kiwi 插件主线 R104：真实网络采集一致性验证阶段记录

## 继承与禁止误销项
- 正式插件基线仍为 V0.4.58 MV2，正式包 SHA-256 `32219f852321aea68843acfac91a33c86be2563c4f4a609988fed109d7edc479`。
- R103 已证明：真实 Kiwi 安卓虚拟机安装、侧栏显示、观察起止、原生下载确认、Android 下载 ZIP 通过 ADB 回读、47 文件 ZIP CRC。
- R104 不修改上述正式业务源码。本文件仅新增受控网络采集验收方法；原始 R/F/T、UX、R77-02、R88-01、R94-04 均原编号继承。
- 不允许依据受控服务可访问、ZIP 文件存在或 CI 作业成功状态来销项 A7 网络采集完整性。

## 已获得真实运行证据
- 真实 Android 11 Google APIs x86_64 + 官方 Kiwi 14310011181，CI Run 43164415061。
- 受控本地 HTTP 服务 `127.0.0.1:18764`，`adb reverse tcp:18764 tcp:18764`。
- Kiwi 网页自动发起 7 个批次，每批四个 fetch 路径，共 **28 次实际 API 请求**；服务端独立真实回执：alpha.json 7×200、beta.txt 7×200、expected-404 7×404、tiny.svg 7×200。
- HTTP 服务建立、ADB 反向端口、Kiwi 页面打开、服务端实际收到请求、状态码、批次序号六类基础门与 A0 初始化共 **R104-A0～A6 7/7 PASS**。
- 原始 GitHub Artifact #13918734709；所有基准服务器回执、Kiwi 真实截图、UI XML、脚本均由 CI 保存。
- 执行原始 R101 Canary 基线只是复用既有安装宿主；本 R104 不据此声明正式插件网络采集已通过。

## 验收程序独立质量门
- 正式插件 R104 测试脚本：`kiwi-r104-lab/r104-production-network-test.py`；
  受控服务：`kiwi-r104-lab/controlled_fixture_server.py`；
  导出对账：`kiwi-r104-lab/r104_capture_reconcile.py`。
- CI Run 43165394176：正式脚本 Python 编译 / 对账器独立单测通过。
- 构造的正例 ZIP `requests.json` + HAR + Trace：10/10 对账项 PASS。
- 五项故意失败均被正确识别：缺少请求、HAR 404 被篡改、Trace 丢失请求、服务端漏收、服务端状态错误。
- 这是验收工具的成功，不是正式插件的采集业务成功。

## 仍未销项
- **R101-A7/R30/T22/T23/T42/T51 → R104_NET_01～10**：需要再次通过私有正式 MV2 的一次性加密交接，在同一 Android 虚拟机环境运行 `r104-production-network-test.py`，取得真正的观察窗口、导出 ZIP、requests.json/HAR/Trace 与服务端独立日志，逐项审查。
- `R104_NET_07_trace_routes` 专门检查 Trace 是否包含相应 URL；若实际 Trace 设计只记录其他事件，则留档失败并进行设计研究，不能直接降标准销项。
- R94-04：Kiwi 内 512MiB+ MSE/Worker/OPFS/重启恢复/视频重建仍未验收。
- R77-02：真实视频对象与请求、文件关联仍未验收。
- R88-01：YouTube 403 与真实媒体下载仍未验收。
- UX-06/UX-07：原生 DevTools 触屏操作和宿主增强仍未验收。
- F01–F15 / T01–T54：各自原验收编号继续保留。

## 安全与跨会话
- 公共代码仓库只存不含私有正式插件的可复现实验程序，隔离 Draft PR 不合并主分支。
- 正式 MV2 使用已验证的 R103/R104 一次性加密交接；不在 Git 提交/CI Artifacts 保存明文源代码或私钥。
- 原 R103 完整未加密源码工程仍在用户 Google Drive 三分卷，R104 增量测试源码与原始 evidence 另行备份；新会话须一同恢复。
- 本阶段**尚未执行带正式 MV2 的 R104 真实捕获回归**，所以 A7 网络采集一致性不得标为完成。
