# 自然语言需求 → 在线数据 → ArcGIS Pro 成图

用户把需求交给 MCP 客户端中的 AI；AI 负责提取地名、年份、专题和精度要求，调用下面的工具。MCP 服务不内置大模型，不需要再填写一个大模型 API key。

1. `list_online_data_sources`：检查实际实现的数据源、授权和局限。
2. `search_online_regions(query, cache_dir)`：搜索真实边界；同名结果由 AI 展示给用户选择，不凭空猜测。Nominatim 不可达时仅允许精确匹配的 Natural Earth 国家级边界回退，不能用国家替代城市。
3. `create_online_research_map(region, output_dir, project_path, zoom, osm_id, request)`：下载边界、高程瓦片和定位矢量，在 ArcGIS Python 中完成转换、裁剪、投影和 journal 模板制图，保存 APRX、PNG、PDF、SVG、数据来源及缺项清单。
4. AI 读取返回的 `coverage`，把未满足的原始需求明确报告。不能把“基础地形图完成”描述为所有专题均已完成。

例如：“联网下载尼泊尔的边界和地形，制作论文区域概况图”。AI 将地名提取为 Nepal，先查看候选，再调用制图工具。独立模式中 `project_path` 是一个已有 APRX 的路径；Pro 快照桥接模式可省略。

## 当前实现范围

- OSM/Nominatim 面边界（社区数据、ODbL，非测绘权威边界）。公共服务按至少 1.1 秒间隔、单线程查找并缓存，不适合批量地名抓取。
- AWS Mapzen Terrain Tiles，Terrarium RGB 解码为实际米高程，不用截图充当 DEM。来源为 SRTM 等多源拼接，年份和原始精度不统一。缩放等级决定采样网格，不代表原始数据具有同等精度。
- Natural Earth 1:110m 国家定位矢量，仅适合小比例尺定位。
- 至多下载 64 张 256×256 瓦片；zoom 5—12，超限明确报错，由用户或 AI 明确调整，禁止悄悄降分辨率。
- 输入地名歧义、网络失败、没有面边界会停止并保留日志，不用合成数据代替。
- **尚未实现**指定年份卫星影像、土地利用自动下载、任意互联网资料搜索、付费平台认证以及直接获取观测采样点。河网可在真实 DEM 投影到米后通过既有水文工具派生，不能伪装成下载的实测河流。

## 数据与制图质量

每个任务都有 `data/data_sources.json` 和瓦片 SHA256；高程许可完整说明存入 `TERRAIN_ATTRIBUTION.md`。主图使用适宜的 UTM 分区（仅适合常规小区域，不适合极区或跨多分区的大范围定量分析），原始数据留存，派生数据独立输出。

journal 版式将地形主图放大、区域定位缩小，图例置于独立栏。参考了地数空间公开展示的“位置图、地形图与紧凑图例”的组织方式；没有取得其插件源码、模板或所谓预训练资产，也不声称复现了其内部实现。

已实际查看的公开案例：[第2集](https://www.douyin.com/video/7697130360156540200)、[第4集](https://www.douyin.com/video/7698293339149454634)、[第5集](https://www.douyin.com/video/7699747168701271296)。作者在第5集评论中说明使用内置模板；其全国30米DEM为作者自述，未在本项目中验证或再分发。

官方数据说明：[Nominatim 使用政策](https://operations.osmfoundation.org/policies/nominatim/)、[Terrain Tiles 格式](https://github.com/tilezen/joerd/blob/master/docs/formats.md)、[归属声明](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)。
