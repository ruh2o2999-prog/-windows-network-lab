# Kiwi 插件 R113｜两轮深度检索与 MSE→OPFS→重启恢复融合决策

**研发规范**：V8.12 统一源码版。**文档状态**：研究完成；候选融合尚未安装和验收。**原问题**：R94-04、R94-03、R77-02，均保留原验收文本及既有状态。**目标产品**：Kiwi Android MV2 扩展；不另造浏览器或 APK。

## 一、基线核验（源代码而非推测）

1. R112 实测：V0.4.59-rc1 Android Kiwi 11 扩展 origin 的 `mse-journal-r94.js`，完成 116,985 字节 H.264/AAC fMP4 的原生 OPFS 分片写入，杀死浏览器后从新进程恢复，SHA 一致，R112 13/13 SUB_PASS。它不是主线程真实 MSE `appendBuffer` 贯通证明，也不是大文件 G5。
2. `src/mse-page-r94.js`：MAIN world 对 `URL.createObjectURL`、`MediaSource.addSourceBuffer`、`SourceBuffer.appendBuffer` 做钩子；按用户授权启动，64KiB 分片、8MiB 队列、逐片 ACK、媒体对象/单 SourceBuffer 身份约束；单独的多轨直接拒绝，Worker MSE 尚未覆盖。
3. `src/response-bridge.js`：`window.postMessage` Transferable ArrayBuffer → 编码 Base64 → `chrome.runtime.sendMessage`；返回 ACK 给页面世界。Base64 传输存在体积/CPU 成本，但有既有协议可用。
4. `src/mse-host-r94.js`：只接受插件自身用户界面授权的 START/STOP，后台校验 Tab/URL/frame/blob 所属；`background.js` 当前仍实例化 `KiwiMseJournalR94.create(...,sharded:true)`，即一分片一文件的 R94 模式。
5. `src/mse-journal-r94.js`：OPFS 分桶式分片落盘、按 seq/append 校验、重开恢复、重组、拒绝多轨直接合并。
6. `src/mse-opfs-fast-r100-worker.js`：历史工程已有**真正可执行的 Dedicated Worker** WAL 实现，使用 `createSyncAccessHandle()`、32B 分片头、CRC32、严格序列和 `flush()`、重启扫描损坏/截断、状态锁定，支持 `appendBatch` 1–16 分片。SHA-256 `e53eaa8c7a52d5aea6e25659ec2c488a081defd9046d906e98b1a08535d49e38`。
7. **正式包缺口**：V0.4.59-rc1 的 ZIP 包含 R94 的 page/host/journal/bridge，却**不包含** `mse-opfs-fast-r100-worker.js`；背景主进程没有 Worker 适配器。当前“已写出的 R100 能力”尚未成为用户安装版本功能。
8. 历史 R100 桌面 Chromium G4 `docs/r100/real_chromium_fastwal/R100_FastWAL_G4_summary.json`：原始压力 `bytes=33,554,432 (32 MiB), parts=512`，确实跨进程恢复并拒绝无授权继续写。**摘要标题提到 512MiB 不是 512MiB 实测证据**；其 `g5Android=NOT_TESTED`。R112 后 Android 小文件 OPFS 已有证据，但 ≥512MiB 仍未实测。

## 二、第一轮：Chromium 官方技术能力与边界

- Chromium 102+ 的 OPFS `FileSystemFileHandle.createSyncAccessHandle()` 可在 Dedicated Worker 中对 OPFS 文件读写；在 Chromium 108+ `write/read/getSize/truncate/flush/close` 方法为同步形式。资料：https://developer.chrome.com/docs/capabilities/web-apis/file-system-access 和 https://developer.chrome.com/blog/sync-methods-for-accesshandles
- `flush()` 是明确的耐久写入边界，关闭 Worker 或浏览器不应作为唯一提交方式；具体实现和浏览器环境仍须实测。资料：https://developer.mozilla.org/en-US/docs/Web/API/FileSystemSyncAccessHandle/flush
- `navigator.storage.estimate()`/`persist()`用于容量检查和持久性请求；不能保证设备空间或阻止用户主动清除浏览器数据。资料：https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria
- `MediaSource.canConstructInDedicatedWorker` 意味着部分播放器的 SourceBuffer 在 Worker 内；页面主世界原型钩子不能保证覆盖此类 MSE。资料：https://developer.mozilla.org/en-US/docs/Web/API/MediaSource 和 https://www.w3.org/TR/media-source-2/
- Chrome 扩展 content script 默认隔离世界；主世界必须尽早注入，并结合安全的消息桥，既有 MV2 实机行为是最终依据。资料：https://developer.chrome.com/docs/extensions/reference/manifest/content-scripts 与 https://github.com/GoogleChrome/developer.chrome.com/blob/main/site/en/docs/extensions/mv2/content_scripts/index.md

## 三、第二轮：成熟开源项目源码与复用判断

| 已核查项目 | 实现/源码 | 可吸收的技术单元 | 不直接照搬的部分 |
|---|---|---|---|
| aeroxy/blob-downloader（MIT） | `src/entrypoints/hook.content.ts`、`bridge.content.ts`、`src/lib/blob-registry.ts`、`segment-store.ts`；https://github.com/aeroxy/blob-downloader | MAIN-world document_start、重复安装防护、SourceBuffer/Blob 和 `srcObject` 对象映射、append 顺序与初始化段保护 | 主要在页面内存保存分片，512MiB/track 默认限制，不跨重启，非我们的 OPFS 终态 |
| OPFS VFS | https://opfs.dev/docs/guides/persistence/ | durable flush、WAL 恢复与异常保留的设计与测试模式 | 不替换我们已有的 R100 WAL，不在未兼容时迁移文件格式 |
| pratherbytecraft/drip-fs | https://github.com/pratherbytecraft/drip-fs | 分块流式下载、MessageChannel 与 OPFS 中转，避免完整 Blob 常驻内存 | 面向浏览器/Service Worker 的技术路线需在 Kiwi MV2 验证，不直接假设适配 |
| gpac/mp4box.js | https://github.com/gpac/mp4box.js | fMP4 渐进解析、轨道/样本信息、结构校验，为音视频分轨重封装前置判断提供工具 | 并非拿到两个 SourceBuffer 就能自动拼出完整且同步正确的 MP4；封装逻辑需另行验证 |
| Media Bridge | https://github.com/jvillegasd/media-bridge | IndexedDB 分片记录、下载历史、重启后的任务状态、HLS/DASH 适配 | FFmpeg.wasm 大文件内存模式、MV3 offscreen 不作为 Kiwi MV2 的直接依赖 |

**许可要求**：后续如实际引入第三方代码，应先检查确切文件对应 LICENSE/版本，记录归属与修改；当前只借鉴架构和定位源码，不等于已经集成或验证。

## 四、融合决策（不推翻已验证的 R94/R112）

**主路线：`mse-page-r94.js` → `response-bridge.js` → `mse-host-r94.js`（严格授权/播放器身份）→ 新增 R100 Worker 适配器 → `mse-opfs-fast-r100-worker.js`（WAL、CRC、flush、恢复）→ 流式组装 → `mp4-verify-r94.js` 与独立 FFprobe/播放验收。**

- 阶段1：不改动真实页面 hook、业务按钮和原历史导出；把 R100 Worker 带入新隔离候选，在 MV2 `chrome-extension://` 受控背景/专用页面启动，验证真实 `createSyncAccessHandle`、32B WAL 头、CRC、flush 和冷重启扫描；若缺兼容则仍保留 R94 分桶模式作为明确标记的降级分支。
- 阶段2：在原 `mse-host-r94.js` 增设**已授权后的** Worker 后端适配器。复用现有 Base64 分片协议先求正确性，使用 R100 `appendBatch`（每批最多 16×64KiB），由**写盘成功并 flush 后**才回 ACK；限额队列、监测延迟和浏览器内存，不让页面承担 512MiB 级 Blob。
- 阶段3：采用真实视频 `<video>` + `MediaSource` + `SourceBuffer.appendBuffer` 的受控网页（非直接对 Worker 调 init/append 的测试）运行 fMP4。必须从初始化段开始，经真实页面主世界消息桥写入 OPFS，停止/重启后重组 SHA 与原媒体一致。保持 EME/DRM 拒绝、用户主动选择、真实播放器 blob 与 tab/frame 对应。
- 阶段4：运行单独的 ≥512MiB **真实 Android OPFS 压力与浏览器进程/后台恢复**。记录每个分片顺序/CRC、已提交偏移、内存峰值、存储余量与耗时；实际至少 536,870,912 字节，不能把 32MiB 冒充 512MiB。长媒体实际 MSE 语义与纯存储压力为两条独立证据，不混同。
- 阶段5：分轨视频+音频、多段切换、seek、去重、Worker MSE 分别作为原 `R94-03`/`R77-02` 问题继续攻坚。使用 MP4Box.js 识别轨道/时间戳，明确重封装路径；不得直接连接两个独立轨道字节流并声称可播放。

### 首轮 R113 建议的必要真实关卡

- `R113-WAL-01`：正式 Kiwi MV2 插件扩展源 Dedicated Worker 可成功 `createSyncAccessHandle`；写/flush/close/重开和 CRC 都是原生操作。
- `R113-WAL-02`：复用现有 R94 页钩子和消息桥写入 116,985 字节 H.264/AAC 测试流，提供完整 MSE `appendBuffer` 证据与插件侧持久记录；不能只让外部测试脚本直接写 OPFS。
- `R113-WAL-03`：浏览器 `am force-stop` 后重新打开同一个扩展身份，WAL 扫描恢复至少一条完整已提交序列，媒体 SHA 一致。
- `R113-WAL-04`：缺片/错序/CRC 失败/尾记录撕裂都必须拒绝假完整；恢复最多至最后可信提交边界。
- `R113-WAL-05`：R112 历史 13/13 关卡、R111 36/36 正文对账不得退化。
- `R113-WAL-06`：≥512MiB 时再以原 `R94-04` 子项评价，测量而非估计实际用量；高负载失败保留原记录，采用增量技术攻坚而不一遍遍重跑全流程。

## 五、重要约束与风险

1. 用户关闭/进程终止后可以恢复**已经提交到 OPFS 的字节**，不等于能自动继续捕获已经结束的网页会话；重新录制必须有用户授权及对已保存媒体的身份/序列去重证据。
2. `SourceBuffer.appendBuffer` 的 append 顺序不等于媒体时间戳顺序；seek、变速、ABR 切换、双 SourceBuffer 均不能直接拼接为完整影片。
3. OPFS 和浏览器来源绑定，清除插件数据/卸载、存储回收可能丢失；必须明确最终导出用户可见位置并核对下载回执。
4. 不处理 DRM 绕过，不将未经授权媒体保存列为默认业务；检测到 `encrypted`/EME 时拒绝或仅分析非内容元数据。
5. 不能用 GitHub 的绿色状态代替实际候选包 SHA、Runner 所用 Kiwi/Android 版本、真实录制文件与独立对账。

## 六、优先级与结论

**最短路径不再是继续检索其他 OPFS 库，而是把历史已验证的 R100 原生 WAL Worker 接回 V0.4.59-rc1 中现成的 R94 捕获桥，并按上述关卡做真实 Kiwi Android 验收。** 这是有成熟 Chromium API、外部开源经验和我们自己历史源码支撑的具体方案，但 R113 候选尚未实现，因此 R94-04 保持 `PARTIAL`，不能提前销项。
