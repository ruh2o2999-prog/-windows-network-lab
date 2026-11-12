# R106 候选技术路径：响应正文与真实媒体取证（仅技术研究，不是验收 PASS）

## R105 实证边界
R105 Run `43173327115` 已证明 Kiwi Android MV2 `chrome.webRequest.onCompleted` 在受控网站 36 次请求中发出 36 次回调；404 事件亦实际被监听。此路径主要用于 URL、请求ID、Tab、类型、响应状态、时间戳及部分响应头等**网络元数据**。

## 不能以 webRequest 代替正文
官方 Chrome 文档 `https://developer.chrome.com/docs/extensions/reference/api/webRequest` 定义网络生命周期事件，但并非完整响应正文存储接口。

`https://developer.chrome.com/docs/extensions/reference/api/devtools/network` 指出 DevTools HAR 默认不包含响应体，获取正文须在 DevTools 上下文调用 `request.getContent()`。如果 DevTools 在页面加载之后才开启，之前请求可能缺失；因此**不能把 DevTools 限制性路径当成普通浏览时的无条件正文采集保证**。

## 下一步多路径实际研究（全部 NOT_RUN）
1. **被动事件层**：MV2 `webRequest` 记录完成事件及 URL/状态/请求ID；先逐事件与真实服务器比较；R104 严格工具已就位。
2. **普通页面正文层**：经授权在页面主世界尽早 hook `fetch`、`XMLHttpRequest`，限量 `Response.clone()`/回调获取可读正文；确认 CSP、跨域、Service Worker、ReadableStream 和注入竞态；保存 payload hash，避免默认收集用户敏感原文。
3. **DevTools 深度层**：测试 Kiwi 本机 `devtools_page` 激活条件，以及 `chrome.devtools.network.onRequestFinished` + `request.getContent`；只在真实开放面板场景报告可用。
4. **CDP/调试权限层**：研究 `chrome.debugger`、`Network.getResponseBody` 在当前 Kiwi 版本上有无实际可用连接；需要隔离探针和真实证据，不能直接假定桌面 API 在 Android 支持。
5. **MSE/媒体层**：独立核验 `MediaSource`、`SourceBuffer.appendBuffer`、媒体映射/身份、分段持久化和重新组合；保持 R94-04 等原编号未销项。
6. **反例**：正文为空、流式截断、解码失败、跨 Tab 混入、媒体不对应、>48MiB/512MiB 退化等必须留下失败记录，不能用“文件存在”过关。

## 不可混淆的原编号
R105 公共宿主 API 子项通过 ≠ 正式插件 A7 通过；
R104 路由/请求元数据对账 ≠ 正文回读通过；
正文回读 ≠ MSE 音视频合轨与完整下载通过。
正式 V0.4.58 源码仍单独保留，原 R/F/T、UX、R77、R88、R94 不因本技术备注改变。
