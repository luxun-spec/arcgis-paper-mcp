# 验证记录

## 2026-10-29 v0.3 增量验证

- 31 项自动化测试：30 通过、1 项需原生 ArcGIS 的测试跳过；包含横长区域布局、风格参数输入和 Mercator 地面尺度修正回归。
- 真实尼泊尔边界/地形数据在 ArcGIS Pro 3.6 实际导出自然风格、标签式经纬网和横向 journal 布局；APRX 重开检查通过，PNG/PDF/SVG 齐全，warnings=[]，退出码0。
- 实际查看最终 PNG，检查主图范围、横排图例、比例尺、坐标标注和阴影。earth/gray 使用同一渲染路径与不同颜色表，本轮未分别进行原生导出验收。
- 完成代码审查及公开发布前的跟踪文本凭据/本机个人路径检查；未发现严重问题。参考资料可访问范围及未读内容见 CARTOGRAPHY.md。

## 2026-10-29 v0.2 增量验证

- 28 项自动化测试：27 通过、1 项原生环境测试跳过，包括真实 MCP 工具枚举、新 journal 图框和联网输入校验。
- 实际执行 `create_online_map(region='Nepal', zoom=7)`：联网检索 OSM 面边界、下载与解码真实 Terrarium 高程瓦片、下载 Natural Earth 定位矢量，完成裁剪、投影和 journal 布局，导出 APRX/PNG/PDF/SVG，退出码 0，warnings=[]，synthetic=false。
- 保存了 `data_sources.json`、瓦片哈希、许可说明及 `coverage` 缺项清单。该案例测试的是多源高程概况图，不是30米原始DEM精度证明，不含指定年份影像或土地利用。
- 本次测试直接通过 ArcGIS Python 后端执行；新联网 MCP 工具已通过协议枚举，但未将网络下载流程再通过真实 MCP 客户端重复执行。

以下为 v0.1 历史记录。

验证日期：2026-10-27。环境：Windows、ArcGIS Pro 3.6 / Advanced、Python 3.13.7、MCP SDK 1.30.0。

| 验证项 | 实际结果 |
| --- | --- |
| 自动化测试 | 23 项：22 通过，1 项需 ArcGIS 的测试在普通环境中跳过 |
| ArcGIS 专用投影测试 | 在 Pro Python 中单独执行，全球正射定位中心坐标投影到原点，1 项通过 |
| MCP stdio 协议 | 初始化、工具枚举、模板调用、提示词枚举通过 |
| MCP → 独立 ArcGIS Python | 实际调用 ping_arcgis 和 inspect_dataset 均成功；检查到分级河流 2414 条及 grid_code 字段 |
| study_area 模板 | 原生 APRX、300 dpi PNG、PDF、SVG 均生成；manifest warnings=[] |
| watershed 模板 | 原生 APRX、300 dpi PNG、PDF、SVG 均生成；manifest warnings=[] |
| APRX 可编辑布局 | 保存后重新打开 APRX，确认生成的 Layout 可读取；不是仅检查文件存在 |
| 图像检查 | 查看两张实际 ArcGIS 导出的 PNG；检查标题、图框、图例、经纬网、比例尺与合成数据声明 |
| 水文分析 | Fill → D8 → FlowAccumulation → Strahler → StreamToFeature → Basin → RasterToPolygon 完整返回，退出码 0 |
| 水文阈值 | 500×500 米像元，20 km² / 0.25 km² = 80 个上游像元 |

首轮测试发现并修正：正射投影参数名、CIM 比例尺单位字典、图例需通过 CIM 设置的属性、本地化经纬网样式名称、删除再新建本地化项目项导致的 URI 冲突、子进程继承 MCP 标准输入引起的超时、非米高程的误标，以及不应对非 Concurrent Use 授权调用的许可归还。

当前策略保留种子工程原有项目项，并新建唯一名称的论文布局；不会编辑用户原始 APRX。测试前的沙箱限制已解除。当地 Pro 安装仍输出缺少 936.txt 码页表的原生日志，但最终两套制图和水文任务成功；这类安装日志不等同于 manifest 中的布局缺项警告。

已验证的连接方式为独立 ArcGIS Python。Pro Python 窗口快照桥接器已实现，但本次未在打开的 Pro GUI 会话中验收。其他 Pro 版本、中文标签、超大 DEM 和海量图例类别需在目标环境进一步验证。CI 没有 ArcGIS 授权，只运行纯 Python/MCP 测试。

预览图的研究区、DEM、河流、分区和采样点为合成数据，非真实观测或真实流域分析结果；全球/国家参考边界取自 [Natural Earth 1:110m](https://www.naturalearthdata.com/downloads/110m-cultural-vectors/)，用于演示定位，不作为权威研究边界。水文流程另以合成 DEM 实际计算，和示意河流/分区分开测试。
