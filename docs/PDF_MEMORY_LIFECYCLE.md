# 完整PDF解析的原生缓存与内存边界

2026-09-24。本次只调整 `src/pdf_extractor.py` 的资源生命周期；没有修改财务提取规则、原文、几何判断、人工复核状态、文件大小/页数/文本量上限。

## 问题与证据

连续上传中信证券2025、洛阳钼业2025港交所繁体原件、中信证券2024时，Render发生重启。部署方已从Render事件确认两次 `Ran out of memory (used over 512MB)`；不能把WebSocket断开或429单独当成内存诊断依据。本地没有追加线上请求。

本地fresh进程先导入完整 `src.app`，随后按上述顺序重复两轮，共6次真实 `build_manual_financial_snapshot`；每次清除前一份快照及PDF引用并执行垃圾回收。macOS 15.6.1 arm64、Python 3.14.2、PyMuPDF 1.28.2；以自进程 `mach_task_info` 读取RSS，`resource.getrusage`记录峰值。该数值不是Render Linux实测，也不保证所有年报或并发请求都低于512MB。

| 对照 | 应用导入RSS | 六次解析总峰值 | 六次总耗时 |
|---|---:|---:|---:|
| 修复前提交32f15fa的旧PDF提取器 | 160.8 MiB | 519.2 MiB | 12.183秒 |
| 解析中每8页清理原生store，并在起止清理 | 159.5 MiB | 269.0 MiB | 19.632秒 |

此前诊断对照中，只在每份完成后调用 `store_shrink(100)` 无法消除已经形成的RSS高水位；关闭几何检查也仍达到约540.5 MiB。因此保留几何规则，将清理放到全文解析期间。不同fresh进程的绝对RSS有波动，表格使用保存了完整结果的同流程最终对照。

PyMuPDF本地实现及native `fz_debug_store` 显示默认store上限268,435,456字节。中信2025提取结束后，Python可见活跃Page和Document对象均为0，native store仅余1000字节（显式清理后0）；这说明不能简单认定为Document未关闭，或认为结束后再清理就能把已经增长的进程RSS退还给操作系统。周期性驱逐可重新生成的原生资源降低了解析期间的高水位。

本地PyMuPDF 1.28.2的 `TOOLS.store_size()` / `store_maxsize()` 实现返回None，未用其伪造缓存大小。清理采用官方公开接口 [`TOOLS.store_shrink(100)`](https://pymupdf.readthedocs.io/en/latest/tools.html#Tools.store_shrink)，不依赖私有native接口；native debug只用于调查。

## 最小改动

- 继续由进程内同一串行锁保护整个PDF提取。取得锁后清理旧store；每完成8页，包括该页可选几何处理后清理；关闭文档后再清理。
- 清理只驱逐库缓存。已经返回的原始文本、页码及带来源坐标的几何记录保持不变；后续页面需要的资源由同一原件重新载入。
- 缓存清理失败或关闭失败时不返回部分结果。发生关闭/清理错误仍释放串行锁，避免后续请求永久被锁住。
- 只通过本函数自身的异常分支记录解析错误，不读取可能继承调用方异常的 `sys.exc_info()`。如果解析已抛异常，保留原异常及原因链，将额外资源清理错误作为异常注记；清理错误不覆盖原始解析错误。没有原始错误时，清理失败明确抛出错误。

这降低已复现的原生资源高水位，不等于给单个超复杂页面设定硬内存上限；8页内仍可能遇到非常复杂的PDF。上传组件、同时等待的请求及其他页面自身占用由应用层另外管理。不会宣称本次完整解决全部512MB环境风险。

## 正确性与失败恢复验证

最终对照六次全部仍为 `ready_for_human_review`：每份完整 `ExtractedPage` 列表的SHA-256相同，几何记录列表SHA-256相同；完整快照只在 `generated_at` 不同，财务金额、三表结果、来源、页码、单位、原始摘录、版本指纹及状态均相同。不是人工财务核验。

`tests/test_pdf_resource_cleanup.py` 新增10项：原文/页序不变、驱逐过程保持锁、开始/中途/结束清理失败、关闭失败、原解析异常与二次清理异常同时出现，以及调用方正在处理其他异常时清理失败仍必须拒绝返回、且不篡改调用方异常。另把真实隆基页片段的表头安排在第8页、负号续页在第9页，验证跨清理边界的原文及非空几何调整完整一致。

与现有PDF提取、几何测试合跑：**57 passed**。这是本地专门回归计数，不是整库测试或Render构建计数。

任务工作目录 `work/resource-coverage10/` 保留：

- `memory_probe.py`：fresh进程真实三原件两轮对照，旧实现从HEAD只读加载。
- `baseline_evidence.json` / `patched_evidence.json`：RSS阶段、采样点、完整快照及原文/几何SHA。
- `equivalence-and-rss.json`：逐份差异与RSS汇总。
- `baseline.json` / `shrink.json` / `no_geometry.json` / `periodic_store.json`：前期独立原因对照；这些不是最终补丁结果。
- `store_probe.py` / `store.stdout`：关闭后原生store及活跃Python页面/文档对象调查。
