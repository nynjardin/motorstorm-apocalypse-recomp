# toolkit_diff.ps1: the local patches of the toolkit checkout (..\ps3recomp, docs\toolkit-patches.md)
# written into this repository, so that they are versioned with the port:
#   toolkit\ps3recomp_local.diff   `git diff HEAD` of the checkout (apply with `git apply` on BASE)
#   toolkit\new_files\...          the files the checkout does not track (same relative paths)
#   toolkit\BASE.txt               the upstream commit the diff applies to, date, file counts
# Run it before a commit that follows a change in the toolkit. Nothing in the checkout is touched.
param([string]$Toolkit = (Join-Path $PSScriptRoot '..\..\ps3recomp'))
$ErrorActionPreference = 'Stop'
$out = Join-Path $PSScriptRoot '..\toolkit'
New-Item -ItemType Directory -Force $out | Out-Null
$base = (git -C $Toolkit rev-parse HEAD).Trim()
# Raw bytes through cmd: PowerShell's own redirection would re-encode the diff. With the
# checkout's own line-ending settings (core.autocrlf): forcing them off made whole files differ.
$diff = Join-Path $out 'ps3recomp_local.diff'
cmd /c "git -C `"$Toolkit`" diff HEAD --binary > `"$diff`" 2>nul"
$new = Join-Path $out 'new_files'
if (Test-Path $new) { Remove-Item $new -Recurse -Force }
$untracked = @(git -C $Toolkit ls-files --others --exclude-standard)
foreach ($f in $untracked) {
    $dst = Join-Path $new $f
    New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
    Copy-Item (Join-Path $Toolkit $f) $dst
}
$changed = @(git -C $Toolkit diff HEAD --name-only)
@(
    "base commit (upstream sp00nznet/ps3recomp): $base",
    "written: $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    "modified files: $($changed.Count), untracked files: $($untracked.Count)",
    '',
    'To rebuild the patched toolkit: check that commit out, `git apply ps3recomp_local.diff`, copy new_files\ over it.',
    'What each patch is: docs\toolkit-patches.md.'
) | Set-Content (Join-Path $out 'BASE.txt') -Encoding utf8
"{0}: {1:N0} bytes, {2} modified, {3} untracked, base {4}" -f $diff, (Get-Item $diff).Length, $changed.Count, $untracked.Count, $base.Substring(0, 8)
