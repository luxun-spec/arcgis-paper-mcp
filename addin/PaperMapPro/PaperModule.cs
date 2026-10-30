using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;

namespace PaperMapPro;

internal class PaperModule : Module { }
internal class PaperPane : DockPane
{
    protected PaperPane() { }
    internal static void Show() => FrameworkApplication.DockPaneManager.Find("PaperMapPro_Pane")?.Activate();
}
internal class ShowPane : Button
{
    protected override void OnClick() => PaperPane.Show();
}
