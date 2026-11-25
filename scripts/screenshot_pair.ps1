# screenshot_pair.ps1 -Prefix <path prefix>: EVERY game window captured back to back (a few ms apart),
# to compare what the instances show at the same instant (LAN tests: timers, positions).
# Saves <prefix>_h.png (instance 1, title "ps3recomp | ..."), <prefix>_j.png (instance 2, "ps3recomp
# P2 | ...") and <prefix>_p<k>.png (instance k >= 3); prints the time of each capture (ms since the
# first) and the window titles. screenshot.ps1 called twice is ~1 s apart (it compiles its helper
# each time): not usable for that. Sheets of a series: pair_sheet.py, pair_montage.ps1.
param([string]$Prefix, [string]$Proc = "MotorStormApocalypse")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WP {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
}
"@
function Inst-Of([string]$title) { if ($title -match '^ps3recomp P(\d+)') { [int]$Matches[1] } else { 1 } }
$ps = @(Get-Process $Proc -ErrorAction Stop | Where-Object { $_.MainWindowHandle -ne 0 } | Sort-Object { Inst-Of $_.MainWindowTitle })
if (-not $ps) { "no window"; exit 1 }
$shots = @()
foreach ($p in $ps) {                       # allocate first: the captures themselves stay close together
    $r = New-Object WP+RECT
    [WP]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
    $shots += [pscustomobject]@{ P = $p; Bmp = (New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)); Ms = 0.0; Title = '' }
}
$sw = [System.Diagnostics.Stopwatch]::StartNew()
foreach ($s in $shots) {
    $g = [System.Drawing.Graphics]::FromImage($s.Bmp)
    $dc = $g.GetHdc()
    $s.Ms = $sw.Elapsed.TotalMilliseconds
    [WP]::PrintWindow($s.P.MainWindowHandle, $dc, 2) | Out-Null
    $g.ReleaseHdc($dc); $g.Dispose()
}
foreach ($s in $shots) {
    $s.P.Refresh()
    $n = Inst-Of $s.P.MainWindowTitle
    $tag = if ($n -eq 1) { 'h' } elseif ($n -eq 2) { 'j' } else { "p$n" }
    $out = "${Prefix}_$tag.png"
    $s.Bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png); $s.Bmp.Dispose()
    "{0} at +{1:N0} ms  {2}" -f $out, $s.Ms, $s.P.MainWindowTitle
}
