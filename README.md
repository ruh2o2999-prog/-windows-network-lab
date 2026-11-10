# Windows 公开 Runner 联网实测

此公开仓库只用于验证 GitHub Actions 免费 Windows Runner 是否能实际执行一个由源码生成的原生 Windows EXE，并完成 DNS / HTTPS / 文件下载 / SHA-256 / 结果归档。

**不包含**抖音下载器源代码、员工业务数据、真实账户或密钥。

## 测试结果

工作流 `.github/workflows/windows-network.yml` 在 `windows-2022` 和 `windows-2025` 分别编译并执行一份 Go 原生 Windows GUI 子系统 EXE。程序本身访问 `https://example.com/` 并输出 `evidence/network_report.json` 与 `evidence/example_html.html`。只有 JSON 中 `overall=PASS` 才判为成功。Artifacts 最短保留 1 天。

注意：第一轮只验证原生 EXE 的联网、下载及证据；不等于 Windows 7 兼容、真实业务站点或 GUI 截图验收。

手动触发：仓库 Actions → Windows native EXE DNS HTTPS download → Run workflow。
