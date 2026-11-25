# desktop_shot.ps1 -Out <png> [-Scale 0.25]: the whole screen of the game window's monitor (what
# the user sees: screenshot.ps1 captures the window's own content, not where it sits). To check
# PORT_WINDOW=fullscreen: the picture centred at 16:9, black bands beside it (docs\lanceur.md).
# Prints the monitor's size and the game window's rectangle. -Scale shrinks the saved image.
param([string]$Out, [double]$Scale = 0.25, [string]$Proc = 'MotorStormApocalypse')
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class DS {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[DS]::SetProcessDPIAware() | Out-Null
$p = Get-Process $Proc -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
$screen = [System.Windows.Forms.Screen]::PrimaryScreen
if ($p) {
    $r = New-Object DS+RECT
    [DS]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $screen = [System.Windows.Forms.Screen]::FromHandle($p.MainWindowHandle)
    "window: {0},{1} {2}x{3}  title='{4}'" -f $r.L, $r.T, ($r.R - $r.L), ($r.B - $r.T), $p.MainWindowTitle
}
$b = $screen.Bounds
"monitor: {0},{1} {2}x{3}" -f $b.X, $b.Y, $b.Width, $b.Height
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)
$g.Dispose()
$w = [int]($b.Width * $Scale); $h = [int]($b.Height * $Scale)
$small = New-Object System.Drawing.Bitmap $bmp, $w, $h
$small.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose(); $small.Dispose()
"saved $Out ($w x $h)"
