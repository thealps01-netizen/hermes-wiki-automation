@echo off
rem Single entry point for the LLM Wiki MCP server (bundled with the desktop app).
rem All agents (Hermes, Claude Code, Codex) point at this file, so the app's install path with
rem spaces only has to be correct in one place. The server speaks MCP over stdio and talks to
rem the app's local HTTP API (http://127.0.0.1:19828) - the API must be enabled in the app.
setlocal
set NODE=%ProgramFiles%\nodejs\node.exe
if not exist "%NODE%" set NODE=node
rem The desktop app installs per user, under the user's own local app data folder.
set ENTRY=%LOCALAPPDATA%\LLM Wiki\mcp-server\dist\src\index.js
if not exist "%ENTRY%" (
  echo LLM Wiki MCP server not found: %ENTRY% 1>&2
  exit /b 2
)
set LLM_WIKI_API_BASE_URL=http://127.0.0.1:19828
rem Optional hardening: if you turn OFF "allow unauthenticated" in the app (Settings -> API Server),
rem put the token in %USERPROFILE%\.llmwiki-audit\llm-wiki-token.txt (single line, nothing else).
rem This launcher is the only place that needs it; the token never goes into agent configs.
if exist "%USERPROFILE%\.llmwiki-audit\llm-wiki-token.txt" (
  set /p LLM_WIKI_API_TOKEN=<"%USERPROFILE%\.llmwiki-audit\llm-wiki-token.txt"
)
"%NODE%" "%ENTRY%" %*
exit /b %ERRORLEVEL%
