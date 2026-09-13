@echo off
rem fb2opt launcher for Windows: runs the extensionless fb2opt script
rem sitting next to this file. Prefers the py launcher, falls back
rem to python on PATH. The exit code of fb2opt is preserved.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0fb2opt" %*
) else (
  python "%~dp0fb2opt" %*
)
