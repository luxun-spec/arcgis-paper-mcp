using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace PaperMapPro;

internal static class WorkerClient
{
    internal static string DefaultPython()
    {
        var bin=Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);
        return Path.Combine(bin,"Python","envs","arcgispro-py3","python.exe");
    }

    internal static async Task<JsonElement> CallAsync(string python,object request)
    {
        if (!File.Exists(python)) throw new InvalidOperationException("未找到 Pro Python，请检查连接设置。");
        var folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"ArcGISPaperMCP","jobs");
        Directory.CreateDirectory(folder);
        var response=Path.Combine(folder,Guid.NewGuid().ToString("N")+".json");
        var source=Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location),"python");
        var start=new ProcessStartInfo(python) {
            UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,
            RedirectStandardOutput=true,RedirectStandardError=true,
            StandardInputEncoding=new UTF8Encoding(false),StandardOutputEncoding=Encoding.UTF8,
            StandardErrorEncoding=Encoding.UTF8
        };
        start.ArgumentList.Add("-m");start.ArgumentList.Add("arcgis_paper_mcp.pro_worker");start.ArgumentList.Add(response);
        start.Environment["PYTHONPATH"]=source;
        start.Environment["PYTHONUTF8"]="1";
        using var child=new Process {StartInfo=start};
        try {
            child.Start();
            // Drain both streams immediately. Never display raw output: a remote model might echo secrets.
            var stdout=child.StandardOutput.ReadToEndAsync();var stderr=child.StandardError.ReadToEndAsync();
            await child.StandardInput.WriteAsync(JsonSerializer.Serialize(request));child.StandardInput.Close();
            await child.WaitForExitAsync();await Task.WhenAll(stdout,stderr);
            if (!File.Exists(response)) {
                var diagnostic=await stderr;
                var settings=JsonSerializer.SerializeToElement(request);
                if(settings.TryGetProperty("key",out var credential) && !string.IsNullOrEmpty(credential.GetString()))
                    diagnostic=diagnostic.Replace(credential.GetString(),"[已隐藏]");
                var diagnosticFile=Path.Combine(folder,"worker-startup-error.txt");
                await File.WriteAllTextAsync(diagnosticFile,diagnostic,Encoding.UTF8);
                throw new InvalidOperationException($"ArcGIS 工作进程退出（{child.ExitCode}），未返回结果。启动诊断：{diagnosticFile}");
            }
            using var json=JsonDocument.Parse(await File.ReadAllTextAsync(response,Encoding.UTF8));
            var root=json.RootElement;
            if(!root.GetProperty("ok").GetBoolean())throw new InvalidOperationException(root.GetProperty("error").GetString());
            return root.GetProperty("result").Clone();
        } finally { if(File.Exists(response))File.Delete(response); }
    }
}
