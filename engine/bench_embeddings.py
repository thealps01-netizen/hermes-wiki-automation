"""Is this PC enough for the local embedding stack? Measures the machine and benchmarks the
actual Ollama embedding endpoint with a realistic batch, then estimates the wiki re-index time."""
import json, subprocess, time, urllib.request, shutil, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wikiconfig  # tek ayar kaynağı; proje yolu koda gömülü DEĞİL

def ps(cmd: str) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True).stdout.strip()

print("== donanım ==")
print("  CPU:", ps("(Get-CimInstance Win32_Processor).Name"))
print("  çekirdek (fiziksel/mantıksal):",
      ps("(Get-CimInstance Win32_Processor).NumberOfCores") + "/" + ps("(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors"))
os_ = json.loads(ps("Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json") or "{}")
if os_:
    print(f"  RAM: toplam {os_['TotalVisibleMemorySize']/1048576:.1f} GB | boşta {os_['FreePhysicalMemory']/1048576:.1f} GB")
du = shutil.disk_usage(pathlib.Path.home().anchor or "/")
print(f"  Disk {pathlib.Path.home().anchor} boşta {du.free/2**30:.1f} GB / {du.total/2**30:.1f} GB")
print("  Docker konteynerleri:")
print(subprocess.run(["docker", "stats", "--no-stream", "--format", "    {{.Name}}: CPU {{.CPUPerc}} RAM {{.MemUsage}}"],
                     capture_output=True, text=True).stdout.strip())

print("\n== embedding hızı (gerçek ölçüm) ==")
texts = ["LLM wiki sayfa vektörleme testi. " * 25 for _ in range(32)]
body = json.dumps({"model": "embeddinggemma", "input": texts}).encode()
req = urllib.request.Request("http://127.0.0.1:11434/v1/embeddings", data=body,
                             headers={"Content-Type": "application/json"})
t0 = time.perf_counter()
with urllib.request.urlopen(req, timeout=300) as r:
    data = json.load(r)
elapsed = time.perf_counter() - t0
n = len(data.get("data") or [])
tokens = (data.get("usage") or {}).get("total_tokens", 0)
print(f"  {n} metin ({tokens} token) -> {elapsed:.1f} saniye  =  {n/elapsed:.1f} metin/sn, {tokens/elapsed:.0f} token/sn")

# wiki büyüklüğü
import pathlib
pages = [p for p in wikiconfig.wiki_dir().rglob("*.md")]
chars = sum(len(p.read_text(encoding="utf-8", errors="ignore")) for p in pages)
est_chunks = max(1, chars // 1200)
print(f"\n== wiki tahmini ==")
print(f"  {len(pages)} sayfa, {chars/1000:.0f}K karakter -> ~{est_chunks} parça (chunk)")
print(f"  tahmini indeksleme süresi: {est_chunks/(n/elapsed)/60:.1f} dakika (mevcut hızla, varsayılan ayarlarla)")

print("\n== model başına bellek ihtiyacı ==")
print(subprocess.run(["docker", "exec", "ollama-embed", "ollama", "ps"], capture_output=True, text=True).stdout.strip() or "  (şu an yüklü model yok / boşta)")
