# v0.3：以数据与用途选择地图表达

不强制用户使用同一布局。`journal` 根据研究区投影后包络长宽比选择布局：横长区域（宽/高 > 1.6）使用横向主图、下方小位置图和横排图例；其他区域保留侧栏版式。`study_area`、`watershed` 仍可显式选择。此规则是可解释的初始启发式，不是对所有研究区域的自动美学最优解。

## 可调整参数

| 参数 | 可用值 | 默认与用途 |
| --- | --- | --- |
| terrain_palette | natural / earth / gray | natural：较柔和的绿—米白高程；earth：暖土色；gray：低彩度背景 |
| relief_strength | 0—1 | .35，显示阴影强度；不改变 DEM 高程值 |
| grid_mode | labels / full / off | labels：保留刻度与坐标标注，隐藏内部网线；full：显示网线；off：关闭网格 |
| template | journal / study_area / watershed | 按任务选择，非必须使用三级定位 |

三个风格参数既可用于本地 JSON，也可直接传给 `create_online_research_map`。`graticule=false` 优先关闭网格。降低研究区轮廓与指北针的视觉重量，宽版图例采用三栏，避免地形与标注争夺注意力。

显示用晕渲采用自定义四方位光照的加权混合，保留西北光照优势；不是 Esri 六方向函数的数值复刻。Web Mercator 高程按 DEM 中心纬度进行近似地面尺度修正；经纬度和大范围数据仍只能把此阴影当视觉背景，不能由此读取真实坡度。需要坡度等定量指标时，应明确投影、分辨率及分析算法。

## 检索与采用依据（2026-10-29）

| 来源 | 实际可读范围 | 采用的内容 |
| --- | --- | --- |
| [Esri Hillshade](https://doc.esri.com/en/arcgis-pro/latest/help/analysis/raster-functions/hillshade-function.html) | 官方正文 | 多方向光照改善过曝和深阴影区域；本项目独立实现显示算法 |
| [John Nelson：自定义地形晕渲](https://learn.arcgis.com/en/projects/illuminate-terrain-with-a-custom-hillshade/) | 官方教程正文 | 阴影、色彩和不同尺度细节应平衡，显示过程与原始数据分开 |
| [Esri：视觉层级与底图](https://learn.arcgis.com/en/projects/cartographic-creations-customize-a-basemap/) | 官方正文 | 背景克制，专题层次清晰；按使用目的决定视觉重量 |
| [B站：层次感配色](https://www.bilibili.com/video/BV1Vw411Q7e3/) | 搜索索引中的作者说明与公众号链接；直接读取返回412 | 作为配色与样式资料线索，未声称已观看完整视频或取得其工具箱 |
| [B站：清爽风底图](https://www.bilibili.com/video/BV1gpw1ekEQK/) | 作者公开描述可读；直接读取返回412 | 作者描述提到道路透明度、裁剪、标注；本轮未据此宣称实现自动道路标注 |
| [GIS荟公众号图文](https://mp.weixin.qq.com/s?__biz=Mzk0MzE3MTM1OA==&mid=2247494389&idx=1&sn=9f9d70cb03fa12927163ff7d5f461123) | 从作者B站简介定位；公众号正文未能读取 | 仅保留来源入口，不把未读内容作为技术证据 |
| [抖音地数空间第2集](https://www.douyin.com/video/7697130360156540200) | 上一轮通过公开播放器实际查看成图；第4、5集也检查了画面 | 小位置图、大专题图、紧凑图例及内置模板组织方式；不复制其私有资源 |

没有登录绕过、付费内容下载或第三方模板再分发。检索到资料不等于完整观看视频，本表将两者分开记录。
