using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Launcher {
    [STAThread]
    private static void Main() {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, @".venv\Scripts\pythonw.exe");
        string panel = Path.Combine(root, @"manual_launcher\qingxiao_panel.py");
        if (!File.Exists(python) || !File.Exists(panel)) {
            MessageBox.Show("请保留完整项目文件夹并先运行 Setup.ps1 安装环境，不能只移动这一个 EXE。", "鸣潮手动助手");
            return;
        }
        try {
            ProcessStartInfo start = new ProcessStartInfo(python, "-X utf8 \"" + panel + "\"");
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.WorkingDirectory = root;
            start.EnvironmentVariables["PYTHONUTF8"] = "1";
            Process.Start(start);
        } catch (Exception error) {
            MessageBox.Show("启动失败：" + error.Message, "鸣潮手动助手");
        }
    }
}
