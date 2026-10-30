using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using ArcGIS.Desktop.Core;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Layouts;

namespace PaperMapPro;

public partial class PaperPaneView : UserControl
{
    private bool busy,stopRequested;
    private string pendingRequest,pendingProject,outputPath,stage;
    private JsonElement plan,result;
    private Layout resultLayout;
    private DateTime started;
    private readonly DispatcherTimer timer=new() {Interval=TimeSpan.FromSeconds(1)};
    private static string SettingsFile => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ArcGISPaperMCP","pane-settings.json");
    public PaperPaneView()
    {
        InitializeComponent();
        PythonPath.Text=WorkerClient.DefaultPython();
        OutputFolder.Text=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),"ArcGISPaperMaps");
        LoadSettings();
        Chat("助手","你好，请告诉我研究地区和制图要求。例如：帮我画一个云南省的研究区图，只用DEM。复杂需求可在下方设置模型。");
        timer.Tick+=(_,_)=>{
            var seconds=(int)(DateTime.Now-started).TotalSeconds;
            Elapsed.Text=$"已用 {seconds} 秒 · {stage}";
            if(outputPath!=null && Directory.Exists(Path.Combine(outputPath,"map")))
                Elapsed.Text=$"已用 {seconds} 秒 · 正在处理地形、排版并导出";
        };
    }
    private void Chat(string who,string text)
    {
        var p=new Paragraph {Margin=new Thickness(0,5,0,9)};
        p.Inlines.Add(new Bold(new Run(who+"\n")));p.Inlines.Add(new Run(Redact(text)));
        Conversation.Document.Blocks.Add(p);Conversation.ScrollToEnd();
    }
    private string Redact(string text)=>string.IsNullOrEmpty(ApiKey.Password)?text:text.Replace(ApiKey.Password,"[已隐藏]");
    private void Log(string text){RunLog.AppendText(DateTime.Now.ToString("HH:mm:ss")+"  "+Redact(text)+"\n");RunLog.ScrollToEnd();}
    private void Stage(string text){stage=text;Status.Text=text;Log(text);}
    private async Task Run(Func<Task> action)
    {
        if(busy)return;
        busy=true;stopRequested=false;started=DateTime.Now;Send.IsEnabled=false;Stop.IsEnabled=true;
        Parameters.IsEnabled=false;Connection.IsEnabled=false;Demand.IsEnabled=false;
        Progress.IsIndeterminate=true;timer.Start();
        try{await action();}
        catch(Exception ex){Status.Text="任务未完成";Chat("助手",ex.Message);Log(ex.Message);}
        finally{busy=false;Send.IsEnabled=true;Stop.IsEnabled=false;Parameters.IsEnabled=true;Connection.IsEnabled=true;Demand.IsEnabled=true;Progress.IsIndeterminate=false;timer.Stop();outputPath=null;}
    }
    private void CheckStop(){if(stopRequested)throw new InvalidOperationException("已停止后续步骤。已完成的数据和文件会保留。");}
    private async void Send_Click(object sender,RoutedEventArgs e)
    {
        if(busy)return;
        pendingRequest=Demand.Text.Trim();
        if(pendingRequest.Length==0){Chat("助手","请先输入你的制图需求。");return;}
        pendingProject=Project.Current?.URI;
        if(string.IsNullOrEmpty(pendingProject)||!File.Exists(pendingProject)){Chat("助手","请先打开并保存一个 ArcGIS Pro 工程。");return;}
        // Freeze every request parameter before awaiting a worker.
        var endpoint=Endpoint.Text.Trim();var model=Model.Text.Trim();var key=ApiKey.Password;
        var python=PythonPath.Text.Trim();var regionHint=Region.Text.Trim();
        if(!int.TryParse(Zoom.Text,out var selectedZoom)||selectedZoom<5||selectedZoom>12 ||
           !double.TryParse(Relief.Text,NumberStyles.Float,CultureInfo.InvariantCulture,out var selectedRelief)||!double.IsFinite(selectedRelief)||selectedRelief<0||selectedRelief>1)
            {Chat("助手","请检查瓦片级别（5–12）和晕渲强度（0–1）。");return;}
        var parameters=new {zoom=selectedZoom,relief_strength=selectedRelief,
            terrain_palette=((ComboBoxItem)Palette.SelectedItem).Tag.ToString(),grid_mode=((ComboBoxItem)GridMode.SelectedItem).Tag.ToString()};
        if((endpoint.Length==0)!=(model.Length==0)){Chat("助手","模型接口地址和模型名称需要同时填写；不使用模型时请同时留空。");return;}
        CandidatePanel.Visibility=Visibility.Collapsed;ResultPanel.Visibility=Visibility.Collapsed;
        Chat("你",pendingRequest);
        await Run(async()=>{
            Stage(endpoint.Length>0?"正在通过模型理解需求":"正在使用有限地名规则识别需求");
            plan=await WorkerClient.CallAsync(python,new {operation="plan",request=pendingRequest,endpoint,model,key,region_hint=regionHint,parameters});
            CheckStop();
            var unmet=plan.GetProperty("unmet_requirements");
            if(unmet.GetArrayLength()>0)throw new InvalidOperationException("当前入口尚不支持："+string.Join("、",unmet.EnumerateArray().Select(x=>x.GetString()))+"。请调整需求，不能将不完整地图当成已完成结果。");
            var region=plan.GetProperty("region").GetString();
            Zoom.Text=plan.GetProperty("zoom").GetInt32().ToString();
            Relief.Text=plan.GetProperty("relief_strength").GetDouble().ToString(CultureInfo.InvariantCulture);
            Palette.SelectedItem=Palette.Items.Cast<ComboBoxItem>().First(x=>x.Tag.ToString()==plan.GetProperty("terrain_palette").GetString());
            GridMode.SelectedItem=GridMode.Items.Cast<ComboBoxItem>().First(x=>x.Tag.ToString()==plan.GetProperty("grid_mode").GetString());
            Log($"执行参数：级别{Zoom.Text}，晕渲{Relief.Text}，配色{plan.GetProperty("terrain_palette").GetString()}，经纬网{plan.GetProperty("grid_mode").GetString()}");
            Chat("助手",$"研究地区：{region}。将获取公开边界、高程地形和区域定位矢量，再生成可编辑布局。高程不保证指定年份或30米分辨率。");
            Stage("正在联网检索研究区边界");
            var cache=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ArcGISPaperMCP","search");
            var rows=await WorkerClient.CallAsync(python,new {operation="search",region,cache_dir=cache});
            CheckStop();
            var choices=rows.EnumerateArray().Select(x=>new RegionChoice {Name=x.GetProperty("name").GetString(),Id=x.GetProperty("osm_id").ToString()}).ToList();
            if(choices.Count==0)throw new InvalidOperationException("没有找到地区多边形。请填写更明确的地区名或换用已有边界数据。");
            if(choices.Count>1){Candidates.ItemsSource=choices;CandidatePanel.Visibility=Visibility.Visible;Status.Text="等待选择研究地区";Chat("助手","发现多个地区，请在候选列表中选择，程序不会替你猜测边界。");return;}
            await Render(choices[0]);
        });
    }
    private async void Choose_Click(object sender,RoutedEventArgs e)
    {
        if(busy)return;
        if(Candidates.SelectedItem is not RegionChoice choice){Chat("助手","请先选择一个地区。");return;}
        await Run(async()=>await Render(choice));
    }
    private async Task Render(RegionChoice choice)
    {
        CheckStop();CandidatePanel.Visibility=Visibility.Collapsed;
        if(Project.Current?.URI!=pendingProject)throw new InvalidOperationException("当前工程已切换，请重新发送需求。");
        if(!int.TryParse(Zoom.Text,out var zoom)||zoom<5||zoom>12)throw new InvalidOperationException("瓦片级别应为5到12的整数。");
        if(!double.TryParse(Relief.Text,NumberStyles.Float,CultureInfo.InvariantCulture,out var relief)||!double.IsFinite(relief)||relief<0||relief>1)throw new InvalidOperationException("晕渲强度应在0到1之间。");
        var parent=OutputFolder.Text.Trim();if(parent.Length==0)throw new InvalidOperationException("请选择输出父目录。");
        outputPath=Path.Combine(parent,"map-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N")[..5]);
        var parameters=new {region=plan.GetProperty("region").GetString(),zoom,relief_strength=relief,
            terrain_palette=((ComboBoxItem)Palette.SelectedItem).Tag.ToString(),grid_mode=((ComboBoxItem)GridMode.SelectedItem).Tag.ToString(),unmet_requirements=Array.Empty<string>()};
        Stage("正在获取地形数据并调用 ArcGIS 制图");
        Log("选定地区："+choice.Name+"；输出："+outputPath);
        result=await WorkerClient.CallAsync(PythonPath.Text.Trim(),new {operation="render",plan=parameters,project=pendingProject,output_dir=outputPath,osm_id=choice.Id,request=pendingRequest});
        resultLayout=null;
        var png=result.GetProperty("exports").EnumerateArray().Select(x=>x.GetString()).First(x=>x.EndsWith(".png",StringComparison.OrdinalIgnoreCase));
        var image=new BitmapImage();image.BeginInit();image.CacheOption=BitmapCacheOption.OnLoad;image.UriSource=new Uri(png);image.DecodePixelWidth=650;image.EndInit();image.Freeze();Preview.Source=image;
        ResultPanel.Visibility=Visibility.Visible;
        var warnings=result.GetProperty("warnings").EnumerateArray().Select(x=>x.ToString()).ToList();
        Chat("助手","地图已生成，APRX、PNG、PDF、SVG 已保存。"+(warnings.Count>0?"\n提示："+string.Join("；",warnings):"无返回警告。"));
        if(!stopRequested){Stage("正在导入当前工程并显示布局");await ShowLayout();Status.Text="完成 · 地图已显示在 Pro";}
        else Status.Text="制图完成 · 已停止自动导入，可稍后显示布局";
    }
    private async Task ShowLayout()
    {
        if(result.ValueKind==JsonValueKind.Undefined)return;
        if(Project.Current?.URI!=pendingProject)throw new InvalidOperationException("地图已生成；当前工程已切换，未自动导入。请打开输出工程。");
        if(resultLayout!=null){await FrameworkApplication.Panes.CreateLayoutPaneAsync(resultLayout);return;}
        var file=result.GetProperty("pagx").GetString();
        var layout=await QueuedTask.Run(()=>{
            var existing=Project.Current.GetItems<LayoutProjectItem>().Select(x=>x.Name).ToHashSet();
            var item=ItemFactory.Instance.Create(file) as IProjectItem;
            if(!Project.Current.AddItem(item))throw new InvalidOperationException("布局导入失败。");
            var added=Project.Current.GetItems<LayoutProjectItem>().FirstOrDefault(x=>!existing.Contains(x.Name));
            if(added==null)throw new InvalidOperationException("布局导入失败，可从成果文件夹打开 APRX。");
            return added.GetLayout();
        });
        resultLayout=layout;
        await FrameworkApplication.Panes.CreateLayoutPaneAsync(layout);
        Log("已将布局导入当前工程；是否保存当前工程由你决定。");
    }
    private async void ShowLayout_Click(object sender,RoutedEventArgs e){await Run(async()=>await ShowLayout());}
    private void Stop_Click(object sender,RoutedEventArgs e){stopRequested=true;Stop.IsEnabled=false;Chat("助手","将停止后续步骤。正在运行的下载或 ArcGIS 任务会先完成，避免损坏成果。");}
    private void Clear_Click(object sender,RoutedEventArgs e){if(!busy)Conversation.Document.Blocks.Clear();}
    private void Folder_Click(object sender,RoutedEventArgs e){var d=new Microsoft.Win32.OpenFolderDialog();if(d.ShowDialog()==true)OutputFolder.Text=d.FolderName;}
    private void Open(string path){try{Process.Start(new ProcessStartInfo(path){UseShellExecute=true});}catch(Exception ex){Chat("助手",ex.Message);}}
    private void Image_Click(object sender,RoutedEventArgs e){if(result.ValueKind!=JsonValueKind.Undefined)Open(result.GetProperty("exports").EnumerateArray().Select(x=>x.GetString()).First(x=>x.EndsWith(".png")));}
    private void Results_Click(object sender,RoutedEventArgs e){if(result.ValueKind!=JsonValueKind.Undefined)Open(Path.GetDirectoryName(result.GetProperty("project").GetString()));}
    private async void Ping_Click(object sender,RoutedEventArgs e){await Run(async()=>{Stage("正在检查 Pro Python 与授权");var r=await WorkerClient.CallAsync(PythonPath.Text.Trim(),new{operation="ping"});Status.Text="Pro "+r.GetProperty("version").GetString()+" · 连接正常";Chat("助手",Status.Text);});}
    private void Save_Click(object sender,RoutedEventArgs e)
    {
        try{
            if(Endpoint.Text.Contains('?')||Endpoint.Text.Contains('@')||Endpoint.Text.Contains('#'))throw new InvalidOperationException("接口地址不能包含凭据、参数或片段。");
            Directory.CreateDirectory(Path.GetDirectoryName(SettingsFile));
            File.WriteAllText(SettingsFile,JsonSerializer.Serialize(new{endpoint=Endpoint.Text.Trim(),model=Model.Text.Trim(),python=PythonPath.Text.Trim(),output=OutputFolder.Text.Trim()}));
            Chat("助手","已保存设置；API Key 未写入文件。");
        }catch(Exception ex){Chat("助手",ex.Message);}
    }
    private void LoadSettings()
    {
        try{using var d=JsonDocument.Parse(File.ReadAllText(SettingsFile));var r=d.RootElement;
            Endpoint.Text=r.GetProperty("endpoint").GetString();Model.Text=r.GetProperty("model").GetString();
            PythonPath.Text=r.GetProperty("python").GetString();OutputFolder.Text=r.GetProperty("output").GetString();
        }catch(IOException){}catch(JsonException){}catch(KeyNotFoundException){}
    }
    private class RegionChoice {public string Name {get;set;}public string Id {get;set;}}
}
