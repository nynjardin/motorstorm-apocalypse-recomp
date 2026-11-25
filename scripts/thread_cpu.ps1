# CPU time per host thread of the running game over a window: who is busy, by thread name
# (ps3_thread_name / SetThreadDescription). No suspension, no effect on the game.
#   scripts\thread_cpu.ps1 [-Seconds 10]
param([int]$Seconds = 10)
Add-Type -Namespace W -Name T -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr OpenThread(uint access, bool inherit, uint tid);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
[DllImport("kernel32.dll")] public static extern int GetThreadDescription(IntPtr h, out IntPtr desc);
[DllImport("kernel32.dll")] public static extern IntPtr LocalFree(IntPtr p);
'@
function Get-Name([int]$tid) {
    $h = [W.T]::OpenThread(0x0800, $false, [uint32]$tid)   # THREAD_QUERY_LIMITED_INFORMATION
    if ($h -eq [IntPtr]::Zero) { return '' }
    $p = [IntPtr]::Zero; $n = ''
    if ([W.T]::GetThreadDescription($h, [ref]$p) -ge 0 -and $p -ne [IntPtr]::Zero) {
        $n = [Runtime.InteropServices.Marshal]::PtrToStringUni($p); [void][W.T]::LocalFree($p)
    }
    [void][W.T]::CloseHandle($h); return $n
}
$p = Get-Process MotorStormApocalypse -ErrorAction Stop | Select-Object -First 1
$a = @{}; foreach ($t in $p.Threads) { try { $a[$t.Id] = $t.TotalProcessorTime.TotalMilliseconds } catch {} }
Start-Sleep $Seconds
$p.Refresh()
$rows = foreach ($t in $p.Threads) {
    try { $ms = $t.TotalProcessorTime.TotalMilliseconds } catch { continue }
    if ($a.ContainsKey($t.Id)) {
        $d = $ms - $a[$t.Id]
        if ($d -ge $Seconds * 10) { [pscustomobject]@{ Tid = $t.Id; Pct = [math]::Round($d / ($Seconds * 10), 1); Name = (Get-Name $t.Id) } }
    }
}
$rows | Sort-Object Pct -Descending | Format-Table -AutoSize | Out-String | Write-Host
"total: {0:N0}% of one core, {1} threads >= 1%" -f (($rows | Measure-Object Pct -Sum).Sum), @($rows).Count
