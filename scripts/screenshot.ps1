# screenshot.ps1 -Out <png> [-Title <regex>]: the game window as a PNG (PrintWindow, the window may be
# covered). -Title picks the window whose title matches when several instances run (run_lan.bat:
# instance 2 is "ps3recomp P2 | ...", instance 1 matches '^ps3recomp \|').
param([string]$Out, [string]$Proc = "MotorStormApocalypse", [string]$Title = "")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class W {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
}
"@
$p = Get-Process $Proc -ErrorAction Stop | Where-Object { $_.MainWindowHandle -ne 0 -and (-not $Title -or $_.MainWindowTitle -match $Title) } | Select-Object -First 1
if (-not $p) { "no window"; exit 1 }
$r = New-Object W+RECT
[W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$w = $r.R - $r.L; $h = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$dc = $g.GetHdc()
[W]::PrintWindow($p.MainWindowHandle, $dc, 2) | Out-Null
$g.ReleaseHdc($dc); $g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
"saved $Out ($w x $h) title='$($p.MainWindowTitle)'"
