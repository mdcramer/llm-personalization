# Project Notes

Please do not edit files in a way that reintroduces LF/CRLF warnings in GitHub Desktop.

This repo is Windows-first and should use CRLF in the working tree.

Before making any edits:

1. Read `.gitattributes` and respect it.
2. After any file edits, normalize the touched files back to CRLF with UTF-8 without BOM.

Use this PowerShell snippet for specific files:

```powershell
$files = @(
  'C:\Users\markd\Documents\GitHub\llm-personalization\memory.py',
  'C:\Users\markd\Documents\GitHub\llm-personalization\app.py',
  'C:\Users\markd\Documents\GitHub\llm-personalization\chat_service.py',
  'C:\Users\markd\Documents\GitHub\llm-personalization\templates\index.html',
  'C:\Users\markd\Documents\GitHub\llm-personalization\config.txt',
  'C:\Users\markd\Documents\GitHub\llm-personalization\README.md',
  'C:\Users\markd\Documents\GitHub\llm-personalization\prompts\cluster_labeling.txt'
)
foreach ($path in $files) {
  if (Test-Path $path) {
    $content = Get-Content -LiteralPath $path -Raw
    $normalized = $content -replace "`r?`n", "`r`n"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $normalized, $utf8NoBom)
  }
}
```

Also verify `.gitattributes` contains:

```gitattributes
# Keep text files in CRLF format for this Windows-first repo
* text=auto eol=crlf
```

Important:

- Do not change `.gitattributes` unless necessary.
- Do not leave files in LF after patching.
- After `apply_patch` edits, always run the CRLF normalization pass on touched files.
