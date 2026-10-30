# Pro 内的需求窗口

入口：**论文制图 → 需求输入**。这是通过 ArcGIS Pro SDK 实现的原生侧栏，可像内容窗格一样停靠或浮动。

## 输入到地图

打开已保存的本地 APRX，输入研究地区和制图要求，点击“发送需求”。未配置模型时使用有限地名规则；复杂描述需配置兼容 Chat Completions、支持 JSON 模式的模型。没有远程模型也可在参数区明确填写地区，使用默认地形参数运行。

默认输出位于用户文档目录 `ArcGISPaperMaps` 下的唯一新目录。结果包含原生布局、地图图层和独立 APRX，以及 PNG、PDF、SVG、PAGX 和数据来源记录。任务完成后自动向当前工程添加新布局并显示；源工程不会自动保存或覆盖。如果期间切换了工程，程序保留输出但不自动导入。

多个地区候选会暂停，需明确选定。模型提出当前未支持的数据要求也会暂停；土地利用、指定年份、精确分辨率、遥感影像、气象、河流或采样点不能当成已有能力。省级规则只是地名匹配，不能推理复杂地理关系；歧义或缺少地区时请补充信息。

参数区的配色、级别、晕渲和经纬网作为解析时的当前偏好。需求中明确要求的参数可覆盖当前偏好；解析结果会同步到界面并记录在运行日志，再用于实际执行。规则模式识别灰度、暖色、关闭经纬网及“级别6”等有限表达；更复杂表述需模型。瓦片级别默认7，并非高程原始分辨率。最大64块瓦片，超出预算会停止；请缩小研究区或降低级别。

青藏高原使用张镱锂等2021年版完整自然地理边界（DOI 10.3974/geodb.2021.07.10.V1），包含喜马拉雅南坡、兴都库什和帕米尔等境外部分，跨九国，并非仅中国境内范围。边界年份不等于DEM观测年份。整区级别7需98瓦片；本机验收显式改为级别6、28瓦片，采用 Asia North Albers 等积投影（102025）。此数据运行时从出版机构下载，不随源码或插件再分发。若论文采用2014年版或中国境内范围，应换用与你的研究定义一致的边界。

“停止后续步骤”会在当前下载或 ArcGIS 工作进程完成后停止后续操作，不强行杀死正在写入成果的进程。已开始的制图可能继续完成；不会把这个按钮描述成即时撤销。

## 连接和隐私

自动使用当前 Pro 安装附带的 Python；可在设置中改为已授权的克隆环境。只使用 Pro SDK、本地 Python 和原有制图后端，无需运行 Codex、MCP 客户端或手工启动 Python 窗口桥接。已有 MCP stdio 接口不变。

API Key 通过子进程的标准输入传递，不写入请求文件。配置文件只保存接口地址、模型名、Pro Python 和输出位置，位于本机 LocalAppData 下 `ArcGISPaperMCP/pane-settings.json`。不要把 Key 放进需求文本、模型名或接口 URL。远程接口要求 HTTPS，本地 localhost 可使用 HTTP。禁止携带 Authorization 的重定向。需求与成功的成果来源保存在输出中，勿在需求中填写秘密。

## 从源码构建

本插件目标 **ArcGIS Pro 3.6 / .NET 8 / Windows x64**，不要把未经验证的目标版本改成其他 Pro 版本。

```powershell
dotnet build addin/PaperMapPro/PaperMapPro.csproj -c Release '-p:ArcGISProDir=C:/Program Files/ArcGIS/Pro'
```

生成 `addin/PaperMapPro/bin/Release/net8.0-windows/PaperMapPro.esriAddinX`。包内含独立的 Python 制图代码，不依赖用户本地源码目录，也不包含 Key 或个人路径。双击安装后重启 Pro 加载。若组织策略禁止未签名插件，由管理员决定是否允许；项目不改变 Pro 信任设置。

交互参考：[地数空间第4期视频](https://www.douyin.com/video/7698293339149454634)中可见的需求输入、对话和运行日志。并未取得其私有插件或复制其内部实现。原生侧栏依据 [Esri DockPane 文档](https://pro.arcgis.com/en/pro-app/3.6/sdk/api-reference/conceptdocs/docs/ProGuide-DockPanes.html)实现。
