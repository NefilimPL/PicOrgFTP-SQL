# build_exe_mysql.py
import subprocess, os, sys, tempfile
from PIL import Image

def ask_yes_no(prompt, default=True):
    hint = "t/N" if default else "T/n"
    ans = input(f"{prompt} ({hint}): ").strip().lower()
    if not ans:
        return default
    return ans.startswith("t")

def ask_for_file(prompt, extensions):
    while True:
        p = input(prompt).strip().strip('"')
        if os.path.isfile(p) and p.lower().endswith(extensions):
            return p
        print(f"❌ Zły plik. Wymagane: {', '.join(extensions)}")

def resource_sep():
    return ';' if os.name == 'nt' else ':'

def convert_to_ico(path):
    try:
        from PIL import Image as PILImage
        img = PILImage.open(path).convert("RGBA")
        sizes = [(256,256),(128,128),(64,64),(32,32),(16,16)]
        canv = []
        for s in sizes:
            c = PILImage.new("RGBA", s, (255,255,255,0))
            t = img.copy()
            t.thumbnail(s, PILImage.Resampling.LANCZOS)
            x = (s[0]-t.width)//2; y=(s[1]-t.height)//2
            c.paste(t, (x,y), t)
            canv.append(c)
        out = os.path.join(tempfile.gettempdir(), "temp_icon.ico")
        canv[0].save(out, format="ICO", sizes=sizes)
        return out
    except Exception as e:
        print("❌ Błąd ikony:", e); return ""

def make_runtime_hook():
    code = """
# runtime-hook: upewnij się, że locale ENG jest załadowane
try:
    import importlib, mysql.connector.errors as _err
    _ce = importlib.import_module("mysql.connector.locales.eng.client_error")
    _DICT = getattr(_ce, "client_error", None)
    if isinstance(_DICT, dict) and hasattr(_err, "get_client_error"):
        def _get_client_error_fixed(ec):
            try:
                return _DICT.get(ec)
            except Exception:
                return None
        _err.get_client_error = _get_client_error_fixed
except Exception:
    pass
"""
    fd, path = tempfile.mkstemp(prefix="hook_mysql_", suffix=".py")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(code)
    return path

def main():
    print("== PyInstaller Builder (MySQL) ==")
    script = ask_for_file("🔹 Ścieżka do .py/.pyw aplikacji:\n> ", (".py",".pyw"))
    dstdir = os.path.dirname(script)
    base = os.path.splitext(os.path.basename(script))[0]
    exe_ext = ".exe" if os.name=="nt" else ""

    windowed = ask_yes_no("🔹 Aplikacja bez konsoli (GUI)?", True)
    onefile  = ask_yes_no("🔹 Zbudować 1 plik (onefile)?", True)
    add_icon = ask_yes_no("🔹 Dodać ikonę (.ico/.png/.jpg)?", False)

    icon = ""
    if add_icon:
        icon_in = ask_for_file("   ↳ Podaj ikonę:\n> ", (".ico",".png",".jpg",".jpeg"))
        icon = icon_in if icon_in.lower().endswith(".ico") else convert_to_ico(icon_in)

    cmd = [sys.executable, "-m", "PyInstaller", script, f"--distpath={dstdir}"]
    if onefile: cmd.append("--onefile")
    if windowed: cmd.append("--windowed")
    if icon: cmd.append(f"--icon={icon}")

    # === CRUCIAL: mysql-connector + locales ===
    cmd += [
        "--hidden-import=mysql.connector",
        "--collect-submodules=mysql.connector",
        "--collect-submodules=mysql.connector.locales",
        "--collect-data=mysql.connector",
        "--collect-data=mysql.connector.locales",
        "--hidden-import=mysql.connector.locales.eng.client_error",
    ]
    # opcjonalnie inne języki:
    for lang in ("fra","ita","jpn","por","rus","spa","zho"):
        cmd.append(f"--hidden-import=mysql.connector.locales.{lang}.client_error")

    # runtime hook z wymuszeniem ENG
    hook = make_runtime_hook()
    cmd.append(f"--runtime-hook={hook}")

    # spróbuj dorzucić CA z certifi (opcjonalny fallback do TLS)
    try:
        import certifi
        ca = certifi.where()
        if os.path.isfile(ca):
            cmd.append(f"--add-data={ca}{resource_sep()}certifi/cacert.pem")
    except Exception:
        pass

    print("\n🚀 Komenda:\n ", " ".join(cmd), "\n")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print("❌ Błąd PyInstaller:", e); return

    exe = (os.path.join(dstdir, base+exe_ext) if onefile
           else os.path.join(dstdir, base, base+exe_ext))
    print("\n✅ Gotowe!\n📁", exe)

if __name__ == "__main__":
    main()
