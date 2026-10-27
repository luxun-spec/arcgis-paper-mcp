# 连接与排查

## 本地队列

同一 Windows 用户运行 MCP 服务和 ArcGIS Pro。桥接器默认队列：`~/.arcgis-paper-mcp/queue`。两个客户端要共享同一个队列，但一个队列只启动一个桥接器；不同 Pro 实例必须使用不同队列。

自定义队列，在 Pro Python 窗口：

```python
from arcgis_paper_mcp.bridge import start
start(r"D:\private\paper-queue")
```

MCP 客户端配置的 `env` 同步设置：

```json
{"PAPER_MCP_QUEUE":"D:/private/paper-queue","PAPER_MCP_TIMEOUT":"600"}
```

队列文件采用原子写入，领取任务后改为 `.running.json`。任务在领取前过期会拒绝执行。超时不是撤销：正在运行的 ArcPy 可能继续完成。先查看 `.running.json` 和输出目录，再决定是否重试。桥接器意外退出时，停止所有桥接器、确认没有运行任务，再手工清理残留队列文件；不要盲目恢复旧任务。

这是本机信任边界，并非对其他本机用户的权限隔离。使用有用户权限保护的私人目录，不要共享给不可信程序，不要放在公共同步盘。没有远程网络监听，但允许的操作会读取数据并创建输出。

## 快照与当前工程

`start()` 在 Pro Python 线程访问一次 `CURRENT`，保存到队列内唯一命名的 APRX 快照。工作线程只打开快照文件路径，不传递 CURRENT 引用或调用 GUI。源工程的图层不会被删改；生成结果应从输出 APRX 打开。桥接器关闭后可清理不再使用的 `pro-snapshot-*.aprx`。保存快照并不把引用数据打包进去。

## 常见问题

| 情况 | 检查 |
| --- | --- |
| 连接超时 | Pro 是否打开、是否执行 start()、两端队列是否一致；先调用 ping |
| ArcPy 导入即退出 | 直接在 Pro 自带 Python 中执行 `import arcpy`；核实有效授权、用户配置目录权限；与 MCP 协议故障分开处理 |
| 找不到 arcpy | 使用 Pro 自带 Python，或通过 Pro 启动桥接器；不要给普通 venv 安装 arcpy |
| 独立模式缺 project | 提供已有 APRX 作种子，不能用任意空文本文件冒充 APRX |
| 坐标系 Unknown | 根据数据真实来源定义正确坐标系；不能猜测后重投影 |
| 无经纬网、比例尺、指北针 | 检查 manifest warnings 与 ArcGIS 2D 样式；不同版本的样式可能不同 |
| 水文分析拒绝 DEM | 必须投影到米，核实 Spatial Analyst；经纬度 DEM 要先明确重投影和分辨率 |
| 输出目录非空 | 换一个新文件夹；不自动删除研究成果 |
| Pro 工作线程报错 | 关闭桥接器，使用独立 Python 模式；保留错误信息以便排查 |

执行慢时增大 `PAPER_MCP_TIMEOUT`，最大 86400 秒；不建议把高分辨率大区域 DEM 直接用于首轮调试。先小范围验证数据、图框、投影和图例。
