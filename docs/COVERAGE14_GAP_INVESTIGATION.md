# 第14批：三份既有失败原件的有界调查

旧失败 PDF 均保留，没有 OCR、抄写图像金额或放宽读取上限。本调查中没有新增通过候选。过程原件、原生提取和渲染页保存于本批任务 `work/coverage14-gaps/`，不替换已有目录记录。

## 中国建筑 601668

[发行人定期报告目录](https://www.cscec.com.cn/tzzgxnew/dqbg_new/) 仍指向已在第13批核实的 [2025年度报告](https://www.cscec.com/tzzgxnew/dqbg_new/202604/3940000.html)。附件与既有巨潮原件 SHA-256 均为 `be7c5a9a87af23f0f08405942c4159aac7be9dbb72c6979da56b81e69f588815`，370 页。不得把该链接计为新版本；本轮未重复下载同一附件。没有核实到另一份不同、完整且原生可读的 A 股 CAS 原件。

## 中国东方航空 600115

[东航定期报告目录](https://global.ceair.com/global/static/AboutChinaEasternAirlines/intoEasternAirlines/InvestorRelations/periodicReports/) 提供 [官网完整2025年度报告](https://www.ceair.com/global/static/AboutChinaEasternAirlines/intoEasternAirlines/InvestorRelations/periodicReports/ShanghaiStockExchangeReleased/ShanghaiStockExchangeReleased2025/202604/P020260408479381018446.pdf)。真实下载 17,779,298 字节、236 页，SHA-256 `46ffdea7f9e60f353e9c6a680c443e7525d3571dd56a39b0eb5a2f5d7224b807`，不同于旧巨潮原件的 `dd6293baf3cdd9c53c95b154eed9fd58c042b4d05bf398c35cbe54490b5fb7d8`。

但财务页仍为图像：物理页 110 资产负债表续页、112 利润表已渲染目视核对，原生提取文字为零。新字节指纹不代表已修复文字层，因此未加入通过候选。

另真实下载 [港交所2025年报](https://www.hkexnews.hk/listedco/listconews/sehk/2026/0427/2026042702577_c.pdf)，19,982,667 字节、191 页，SHA-256 `c021b8875870dfa8571ad76ce06419f789832d32e5beea69abe1d4dc9faba9a2`。目录和物理页79审计意见明确主财务报表按国际财务报告准则编制。末尾 CAS 差异说明仅为补充财务资料，不是完整 CAS 三表，故排除，未以 IFRS 替代。

## 中国联通 600050

既有完整 A 股原件为 213 页，SHA-256 `f13c0ee26f35fa8d3486c0464f372dd6189c6f591e36dc38c3110c89d4638c4b`。第13批已记录的巨潮 `1225020077.PDF` 两节点404不再报作新原件；[上交所公布链接](https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-03-20/600050_20260320_R37Q.pdf) 本轮实际响应仍为3872字节的压缩 HTML，不能当作下载成功的 PDF。

本轮发现了可验证的原生读取线索：对同一既有 PDF 使用另一原生提取器 `pdfplumber`，物理页77–80的列头、收入和数字可读；物理页79完整渲染与文字结果一致，收入两期为392,222,880,560 / 389,589,219,642元。相比之下 PyMuPDF 在该页把部分列头、营业收入等映射成报告目录文字。此次没有 OCR，没有创建“修正版PDF”，没有从另一主体借值。

这只证明该原件存在更可靠的原生文字读取路径。尚未把新提取器接入生产，也未完成整份原件的身份、两期五项、三表勾稽和全部反例检验，因此联通状态仍为 `needs_review`。若继续推进，应在完整原件上限定检测并留存原生提取来源，不可把目视读数写回文字层或只凭几项金额相等放行。

## 本轮范围

调查随后转向新增样本中可直接修复的现金流与资产负债布局，见 `COVERAGE14_BALANCE_CASH_LAYOUTS.md`。已有成功替代版的人保和洛钼未重复计数。本调查未提交或部署，也未修改共享目录、注册表或发布标记。
