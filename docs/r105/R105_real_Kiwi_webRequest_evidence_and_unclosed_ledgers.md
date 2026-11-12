# R105：真实 Kiwi Android MV2 网络事件回调能力证明

2026-11-12。**注意：这是公开隔离 Canary 宿主探针，不是正式 V0.4.58 插件业务验收。**

## 前提与结果

- GitHub Actions Run `43173327115`、Job `131031557045` 初轮成功；**强化逐数相等 Run `43174346176` 复测成功**。
- 官方 Kiwi Android x64 release `14310011181`，Android 11 API 30 `google_apis` x86_64，Ubuntu 24.04 Runner + KVM。
- 在真实 Kiwi 浏览器中安装 MV2 扩展，启用后台页 `chrome.webRequest.onCompleted` 以及明确的 `webRequest`、本地 HTTP 主机权限。
- 通过 `adb reverse tcp:18764 tcp:18764` 访问受控 HTTP 服务；真实服务器产生和记录 `/r104/api/alpha.json`、`beta.txt`、`expected-404`、`tiny.svg` 每路径 9 次，合计 **36** 次。
- Kiwi 页面可访问性输出由真实扩展背景回调传递的计数：**36**；第二轮门禁硬性要求 `extension_count == server_count`，成功验证 **36/36**。
- HTTP 404 请求数量：服务器真实收到 **9** 次；强化复测中扩展 404 回调 **9** 次，硬性要求相等，**9/9 PASS**。
- 独立真实 Android 运行、扩展安装、页面脚本注入、ADB reverse、四类 HTTP 请求、MV2 事件监听均在 CI 返回 PASS。
- 初轮 Artifact ID `13923790661`；强化复测 Run `43174346176` Artifact ID `13924285746`，大小 2,323,446 字节；原始证据 ZIP `Kiwi_R105_Real_WebRequest_Android_Evidence.zip` 及强化复测 `Kiwi_R105_Exact_WebRequest_Android_Evidence.zip`，包含原执行脚本、HTML/UI XML、PNG、受控请求日志和状态文件。

## 严禁误销项

| 事项 | 状态 |
|---|---|
| R105 公共独立 MV2 宿主 webRequest 完成事件能力 | **SUB_PASS（强化复测 36/36）** |
| R105 404 完成事件能力 | **SUB_PASS** |
| R103 正式 MV2 插件安装/侧栏/下载/ZIP 结构 | **继承原证据 SUB_PASS** |
| R104 正式 MV2 requests.json + HAR + Trace **逐事件强一致** | **NOT_RUN** |
| A7 正式插件完整网络采集、响应正文、媒体等 | **PARTIAL，未整体销项** |
| R94-04、R77-02、R88-01、UX-06/UX-07 | 原编号保留，未销项 |

## 后续操作

在冻结的正式 V0.4.58 安装包中核对 `manifest.json` 的 `webRequest` 和主机权限、背景监听器是否注册、对事件是否按页面/Tab 与观察起止时间过滤、请求状态与去重规则、导出 JSON/HAR/Trace 的序列化。将 R104 受控服务器与 8 项严格事件核对器接入**同一**正式扩展的真实 Android 会话，取得真实导出后验证；有失败逐项归因，禁止仅因公共 Canary 36/36 通过就给 A7 整项销项。

## GitHub 源码

隔离 Draft PR `https://github.com/ruh2o2999-prog/-windows-network-lab/pull/9`，执行脚本 `kiwi-android-lab/kiwi-smoke.py`，受控服务器 `kiwi-r105-lab/network_fixture_server.py`，CI Workflow `.github/workflows/kiwi-r105-public-webrequest.yml`。不得将私有 R99/R100 源码上传本公开分支。
