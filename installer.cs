// 屏幕贴图 离线安装程序（C#5 / WinForms，无网络、无管理员默认装到用户目录）
// 编译：csc /nologo /target:winexe /codepage:65001 /r:System.Windows.Forms.dll /r:System.Drawing.dll /out:setup.exe installer.cs
// 运行：默认=安装界面；/uninstall "<目录>"=卸载（安装程序自身传入）
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

namespace ScreenPinSetup
{
    internal static class Program
    {
        private const string AppExe = "屏幕贴图.exe";           // 安装后的主程序名
        private const string SrcPortable = "屏幕贴图-便携版.exe"; // 与安装程序同目录的源
        private const string ResetBat = "重置程序.bat";

        [STAThread]
        private static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            if (args != null && args.Length >= 2 && args[0] == "/uninstall")
            {
                Uninstall(args[1]);
                return;
            }
            if (args != null && args.Length >= 2 && (args[0] == "/S" || args[0] == "/s"))
            {
                // 静默安装：/S <目录> [桌面快捷方式 1/0] [开始菜单快捷方式 1/0]
                bool desk = args.Length < 3 || args[2] != "0";
                bool menu = args.Length < 4 || args[3] != "0";
                Environment.ExitCode = SilentInstall(args[1], desk, menu);
                return;
            }
            Application.Run(new SetupForm());
        }

        private static int SilentInstall(string dir, bool desk, bool menu)
        {
            string srcDir = AppDomain.CurrentDomain.BaseDirectory;
            string src = Path.Combine(srcDir, "屏幕贴图-便携版.exe");
            if (!File.Exists(src)) return 2;
            try
            {
                Directory.CreateDirectory(dir);
                File.Copy(src, Path.Combine(dir, "屏幕贴图.exe"), true);
                string bat = Path.Combine(srcDir, "重置程序.bat");
                if (File.Exists(bat)) File.Copy(bat, Path.Combine(dir, "重置程序.bat"), true);
                File.Copy(Application.ExecutablePath, Path.Combine(dir, "卸载屏幕贴图.exe"), true);
                if (menu)
                {
                    string smenuRoot = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
                    string smenuDir = Path.Combine(smenuRoot, "屏幕贴图");
                    Directory.CreateDirectory(smenuDir);
                    MakeShortcut(Path.Combine(smenuDir, "屏幕贴图.lnk"),
                        Path.Combine(dir, "屏幕贴图.exe"), dir, "", "屏幕贴图 - 图片视频贴屏工具");
                }
                if (desk)
                {
                    MakeShortcut(Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                        "屏幕贴图.lnk"),
                        Path.Combine(dir, "屏幕贴图.exe"), dir, "", "屏幕贴图 - 图片视频贴屏工具");
                }
                return 0;
            }
            catch
            {
                return 3;
            }
        }

        private static void Uninstall(string dir)
        {
            try
            {
                bool running = false;
                foreach (Process p in Process.GetProcessesByName("screenpin"))
                {
                    running = true;
                    try { p.CloseMainWindow(); } catch { }
                }
                foreach (Process p in Process.GetProcessesByName("屏幕贴图"))
                {
                    running = true;
                    try { p.CloseMainWindow(); } catch { }
                }
                if (running)
                {
                    MessageBox.Show("请先完全退出屏幕贴图（托盘图标右键→退出），再运行卸载。",
                        "屏幕贴图", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                // 删快捷方式
                string desk = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                    "屏幕贴图.lnk");
                string smenuRoot = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
                string smenuDir = Path.Combine(smenuRoot, "屏幕贴图");
                string smenu = Path.Combine(smenuDir, "屏幕贴图.lnk");
                try { if (File.Exists(desk)) File.Delete(desk); } catch { }
                try { if (File.Exists(smenu)) File.Delete(smenu); } catch { }
                try { if (Directory.Exists(smenuDir)) Directory.Delete(smenuDir, true); } catch { }
                // 程序目录自删（安装程序在目录里跑，交给 cmd 延迟删）
                string self = Application.ExecutablePath;
                string cmd = "ping 127.0.0.1 -n 3 >nul & rd /s /q \"" + dir + "\"";
                ProcessStartInfo psi = new ProcessStartInfo("cmd.exe",
                    "/c " + cmd);
                psi.CreateNoWindow = true;
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                try { Process.Start(psi); } catch { }
                MessageBox.Show("已卸载程序文件。\n（配置保留在 %LOCALAPPDATA%\\ScreenPin，如需一并清除请手动删除该目录）",
                    "屏幕贴图", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show("卸载出错：" + ex.Message, "屏幕贴图",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        internal static string MakeShortcut(string lnkPath, string target, string workDir, string args, string desc)
        {
            Type t = Type.GetTypeFromProgID("WScript.Shell");
            if (t == null) return "no WScript.Shell";
            object sh = Activator.CreateInstance(t);
            object sc = sh.GetType().InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, sh, new object[] { lnkPath });
            sc.GetType().InvokeMember("TargetPath", BindingFlags.SetProperty, null, sc, new object[] { target });
            sc.GetType().InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, sc, new object[] { workDir });
            if (!string.IsNullOrEmpty(args))
                sc.GetType().InvokeMember("Arguments", BindingFlags.SetProperty, null, sc, new object[] { args });
            if (!string.IsNullOrEmpty(desc))
                sc.GetType().InvokeMember("Description", BindingFlags.SetProperty, null, sc, new object[] { desc });
            sc.GetType().InvokeMember("Save", BindingFlags.InvokeMethod, null, sc, null);
            return null;
        }
    }

    internal sealed class SetupForm : Form
    {
        private readonly TextBox dirBox;
        private readonly CheckBox deskBox;
        private readonly CheckBox runBox;
        private readonly Button btnInstall;
        private readonly Button btnCancel;
        private readonly Label status;

        public SetupForm()
        {
            Text = "屏幕贴图 安装";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(460, 250);
            Font = new Font("Microsoft YaHei UI", 9F);

            Label title = new Label();
            title.Text = "屏幕贴图 " + "1.6" + "  离线安装";
            title.Font = new Font(Font, FontStyle.Bold);
            title.AutoSize = true;
            title.Location = new Point(18, 16);
            Controls.Add(title);

            Label hint = new Label();
            hint.Text = "安装到（不需要管理员权限）：";
            hint.AutoSize = true;
            hint.Location = new Point(18, 52);
            Controls.Add(hint);

            dirBox = new TextBox();
            dirBox.Location = new Point(18, 74);
            dirBox.Width = 424;
            dirBox.Text = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs", "屏幕贴图");
            Controls.Add(dirBox);

            deskBox = new CheckBox();
            deskBox.Text = "创建桌面快捷方式";
            deskBox.Checked = true;
            deskBox.AutoSize = true;
            deskBox.Location = new Point(18, 108);
            Controls.Add(deskBox);

            runBox = new CheckBox();
            runBox.Text = "安装完成后立即运行";
            runBox.Checked = true;
            runBox.AutoSize = true;
            runBox.Location = new Point(18, 134);
            Controls.Add(runBox);

            status = new Label();
            status.AutoSize = false;
            status.Location = new Point(18, 166);
            status.Size = new Size(424, 22);
            status.ForeColor = Color.DimGray;
            status.Text = "包含：主程序 + 重置程序 + 卸载程序";
            Controls.Add(status);

            btnInstall = new Button();
            btnInstall.Text = "安装";
            btnInstall.Location = new Point(246, 200);
            btnInstall.Size = new Size(96, 30);
            btnInstall.Click += BtnInstall_Click;
            Controls.Add(btnInstall);

            btnCancel = new Button();
            btnCancel.Text = "取消";
            btnCancel.Location = new Point(348, 200);
            btnCancel.Size = new Size(96, 30);
            btnCancel.Click += delegate { Close(); };
            Controls.Add(btnCancel);

            AcceptButton = btnInstall;
            CancelButton = btnCancel;
        }

        private void BtnInstall_Click(object sender, EventArgs e)
        {
            string dir = dirBox.Text.Trim();
            if (dir.Length == 0)
            {
                MessageBox.Show("请填写安装目录。", "屏幕贴图",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            string srcDir = AppDomain.CurrentDomain.BaseDirectory;
            string src = Path.Combine(srcDir, Program_SrcPortable());
            if (!File.Exists(src))
            {
                MessageBox.Show("没找到 " + Path.GetFileName(src) + "，\n请把安装程序和便携版放在同一个文件夹里再运行。",
                    "屏幕贴图", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            btnInstall.Enabled = false;
            btnCancel.Enabled = false;
            try
            {
                status.Text = "正在复制文件…";
                Application.DoEvents();
                Directory.CreateDirectory(dir);
                string dst = Path.Combine(dir, App_Exe());
                File.Copy(src, dst, true);
                string bat = Path.Combine(srcDir, Program_ResetBat());
                if (File.Exists(bat))
                    File.Copy(bat, Path.Combine(dir, ResetBatName()), true);
                // 卸载程序 = 自己的副本
                string self = Application.ExecutablePath;
                string unins = Path.Combine(dir, "卸载屏幕贴图.exe");
                File.Copy(self, unins, true);

                status.Text = "正在创建快捷方式…";
                Application.DoEvents();
                string smenuRoot = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
                string smenuDir = Path.Combine(smenuRoot, "屏幕贴图");
                Directory.CreateDirectory(smenuDir);
                Program.MakeShortcut(Path.Combine(smenuDir, "屏幕贴图.lnk"),
                    dst, dir, "", "屏幕贴图 - 图片视频贴屏工具");
                if (deskBox.Checked)
                    Program.MakeShortcut(Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                        "屏幕贴图.lnk"), dst, dir, "", "屏幕贴图 - 图片视频贴屏工具");

                status.Text = "安装完成。";
                bool run = runBox.Checked;
                Close();
                if (run)
                {
                    try
                    {
                        ProcessStartInfo psi = new ProcessStartInfo(dst);
                        psi.WorkingDirectory = dir;
                        Process.Start(psi);
                    }
                    catch { }
                }
            }
            catch (Exception ex)
            {
                status.Text = "安装失败。";
                btnInstall.Enabled = true;
                btnCancel.Enabled = true;
                MessageBox.Show("安装出错：\n" + ex.Message, "屏幕贴图",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private static string Program_SrcPortable() { return "屏幕贴图-便携版.exe"; }
        private static string Program_ResetBat() { return "重置程序.bat"; }
        private static string App_Exe() { return "屏幕贴图.exe"; }
        private static string ResetBatName() { return "重置程序.bat"; }
    }

    internal static class BindingFlagsAlias
    {
        // 占位避免误引用
    }
}
