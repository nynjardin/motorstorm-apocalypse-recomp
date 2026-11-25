param([string]$Out, [int]$Seconds = 120)
# Minimal DebugView: captures OutputDebugString from processes not under a debugger.
Add-Type @"
using System;
using System.IO;
using System.Text;
using System.Threading;
using System.IO.MemoryMappedFiles;
public static class DbWin {
  public static void Run(string outPath, int seconds) {
    bool created;
    using (var ready = new EventWaitHandle(false, EventResetMode.AutoReset, "DBWIN_BUFFER_READY", out created))
    using (var data = new EventWaitHandle(false, EventResetMode.AutoReset, "DBWIN_DATA_READY", out created))
    using (var mmf = MemoryMappedFile.CreateOrOpen("DBWIN_BUFFER", 4096))
    using (var view = mmf.CreateViewAccessor(0, 4096))
    using (var w = new StreamWriter(outPath, false, Encoding.UTF8)) {
      w.AutoFlush = true;
      var end = DateTime.UtcNow.AddSeconds(seconds);
      var buf = new byte[4092];
      ready.Set();
      while (DateTime.UtcNow < end) {
        if (!data.WaitOne(500)) continue;
        int pid = view.ReadInt32(0);
        view.ReadArray(4, buf, 0, buf.Length);
        int n = Array.IndexOf(buf, (byte)0); if (n < 0) n = buf.Length;
        w.Write("[" + pid + "] " + Encoding.Default.GetString(buf, 0, n));
        ready.Set();
      }
    }
  }
}
"@
[DbWin]::Run($Out, $Seconds)
