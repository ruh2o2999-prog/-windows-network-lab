# Kiwi R111｜V8.12 真实 Android 双 ZIP 原件加密交接、独立复核和销项报告

日期：2026-11-13。产品形态保持 Kiwi Browser Android MV2 扩展，**未修改浏览器、未创建 APK**。

## 1. 本轮目标与修复内容

R110 已在 Android 11 的真实 Kiwi 模拟器中证明 V0.4.59-rc1 能解决历史导出 `00_本次观察结果.txt` 冲突，但该次 GitHub Artifact 只有 SHA、CRC 与对账报告，缺少两份真实 ZIP 原始字节。R111 不修改插件业务源码和候选版本，只修复**原始证据跨 Runner 保存及离线独立复核**这一缺口。

- 复用原 GitHub 隔离分支 `kiwi-r110-index-collision-rc1` 的成功工作流，不重新造 Canary 或测试浏览器。
- Runner 先跑真实 Kiwi、真实观察、原生历史任务、ADB pull、R108 的五项事件与正文对账；**所有要求的 G4 子门均 PASS 时**，才允许 R111 归档。
- 原始 ZIP 只在临时 Runner `/tmp` 出现。用受控接收公钥进行 OpenSSL CMS AES-256 加密，公开 GitHub Artifact 只保留 `.p7m` 密文、原始 SHA 清单与可公开测试截图/结构化记录，**不上传私有插件明文、私钥或原始 ZIP**。
- 接收端用未上传 GitHub 的私钥解密，再检查原下载清单、CRC、ZIP 成员、真实任务请求集合、CDP 响应正文、任务结束状态。
- 原始恢复 ZIP 仅备份至用户受控的 Google Drive 项目目录，不把明文交给公开 GitHub。

## 2. 真实运行与原始制品

| 项目 | 已核实证据 |
|---|---|
| 当前规范 | 《研发规范 V8.12 统一源码维护完整执行包》 |
| 真实 Android 运行 | GitHub Actions Run `43283530409`；Job `kiwi-production-android` conclusion `success` |
| 原始证据 Artifact | `13975025037`（GitHub 原报告总包 5,845,099 字节） |
| 验收宿主 | Android 11 API30 Google APIs x86_64 虚拟机；实际官方 Kiwi 浏览器 |
| 测试插件 | V0.4.59-rc1 候选，SHA256 `caa0e128b1d1a9d185f0d18ea6af39d36a63fa2abeb587acab2f8dc5ff0720e9` |
| 正式回滚基线 | V0.4.58 SHA256 `32219f852321aea68843acfac91a33c86be2563c4f4a609988fed109d7edc479`，不覆盖 |
| 原始采集会话 | `capture-95-5db9ac32`（冷重启前后同一 ID） |
| 重启前 ZIP | `604dd400cade7c109720aa234206acb89477a9d1fc7079d4344fcccdb230ccb2`，918,937 字节，125 项 |
| 冷重启后历史 ZIP | `e87ea25b09187bfcaba5fed2ce0db625ff0f103bdf93f3de3d6db4b171107e3c`，389,199 字节，58 项 |
| 原始测试数据 | 所有 36 条请求的 URL 主机都是 `127.0.0.1`；原 ZIP Cookie、localStorage、sessionStorage 均为空 |

## 3. 脱离 CI 的独立验证结果

本轮**下载了 GitHub Artifact 的原始 ZIP**，并从中提取 R111 `.p7m`，用单独保管的接收私钥在独立工作环境解密。不是从 Runner 的 PASS 日志推断数据正确。

1. 两份加密档案指纹、实际字节数与 Runner 清单一致。
2. 解密后两份 ZIP 实际 SHA256 与 Android ADB 下载原始记录逐字节一致，ZIP CRC 全部 PASS。
3. 原始会话 `captureSessionId` 相同；请求集合 36/36 不丢失、不重复。
4. `cdp_response_index.json` 中 36 项响应正文 SHA 和长度分别与两份原始 ZIP 的真实二进制文件对应，重启前后精确相等。
5. 结束时间与关闭状态相同；原 `r108_offline_recovery_parity.py` 五项门禁 **5/5 PASS**，没有将新写的加密程序自证当独立验证。
6. 两份原始 ZIP 的 SHA 不相同，且不是复制同一文件充数。已另加“相同 ZIP 不接受”回归要求。

接收端负例也已运行：错误私钥、密文被篡改、缺清单，均真实阻断。发送端的错误证书、缺原件、业务门禁 FAIL、原件哈希不匹配，同样拒绝归档。

## 4. 原编号销项边界

本轮按《R111_原编号增量销项台账.csv》记录。`R109-INDEX-01`、`R108-EXPORT-01`、`R108-ZIP-01` 的**本次 Android11+RC1+已结束受控任务**子项达到 `SUB_PASS`，但不等于产品全面 G5 / 全平台最终发布。R07、R17、R26、T17、T37 的其他场景仍 `PARTIAL`；`R94-04`、`R77-02`、`R88-01`、`UX06/UX07` 原状态不动，Android16/OEM 真机不在本轮证据范围内。

## 5. 研发与安全边界

本轮真实通过的是**Android 11 x86_64 官方 Kiwi 虚拟环境**，不能称为 Android16 三星真机通过。候选版本未正式发布。`R111_证据归档接收公钥.crt` 可公开，**私钥不在此交付包、GitHub 分支或 Drive**。由于本包已经保存了测试用的实际 ZIP 原始数据，不必依赖临时私钥才能复验业务内容。

GitHub 工程和测试源码：https://github.com/ruh2o2999-prog/-windows-network-lab/tree/kiwi-r110-index-collision-rc1

真实 Android Run：https://github.com/ruh2o2999-prog/-windows-network-lab/actions/runs/43283530409

### 下一阶段

返回未销项主线，优先按原需求与成熟源码对照攻坚媒体身份与 MSE/OPFS 重启恢复；保持 R111 原始双 ZIP、独立核对脚本及证据作为历史采集链的已验证基线，不再重复测试导航和索引冲突。
