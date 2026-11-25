# ui_auto.ps1 -Proc Lanceur [-List] [-Invoke <name regex>] [-Toggle <name regex>] [-SetValue <name regex> -Value <text>]
# Drive a window through Windows UI Automation (the accessibility tree), without moving the mouse or
# taking the focus: what the launcher's page shows (PrintWindow captures a WebView2 page as blank) and a
# "click" on one of its buttons. -List prints the named buttons, check boxes, fields and texts.
param([string]$Proc = 'Lanceur', [switch]$List, [string]$Invoke = '', [string]$Toggle = '', [string]$SetValue = '', [string]$Value = '', [int]$Max = 80)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$p = Get-Process $Proc -ErrorAction Stop | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { "no window"; exit 1 }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$kinds = 'button', 'check box', 'radio button', 'edit', 'text', 'combo box', 'list item', 'group', 'heading'
function Find-One([string]$rx) { $all | Where-Object { $_.Current.Name -match $rx -and $_.Current.LocalizedControlType -notin 'text', 'texte' } | Select-Object -First 1 }
if ($List) {
    $all | Where-Object { $_.Current.Name } | Select-Object -First $Max | ForEach-Object {
        $v = ''
        $pat = $null
        if ($_.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pat)) { $v = ' = "' + $pat.Current.Value + '"' }
        elseif ($_.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pat)) { $v = ' [' + $pat.Current.ToggleState + ']' }
        "{0,-14} {1}{2}{3}" -f $_.Current.LocalizedControlType, $_.Current.Name.Substring(0, [math]::Min(110, $_.Current.Name.Length)), $v, $(if (-not $_.Current.IsEnabled) { '  (disabled)' })
    }
}
if ($Invoke) {
    $e = Find-One $Invoke; if (-not $e) { "not found: $Invoke"; exit 1 }
    $e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); "invoked: $($e.Current.Name)"
}
if ($Toggle) {
    $e = Find-One $Toggle; if (-not $e) { "not found: $Toggle"; exit 1 }
    $e.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Toggle(); "toggled: $($e.Current.Name)"
}
if ($SetValue) {
    $e = Find-One $SetValue; if (-not $e) { "not found: $SetValue"; exit 1 }
    $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($Value); "set: $($e.Current.Name) = $Value"
}
