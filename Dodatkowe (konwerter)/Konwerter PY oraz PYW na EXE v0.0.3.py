# Pomocniczy skrypt PyInstaller do tworzenia plików EXE z obsługą mysql-connector
import subprocess, os, sys, tempfile, shutil
from PIL import Image

def ask_yes_no(prompt, default=True):
    hint = "t/N" if default else "T/n"
    ans = input(f"{prompt} ({hint}): ").strip().lower()
    if not ans:
        return default
    return ans.startswith("t")

def ask_for_file(prompt, extensions, default_path="", preview_label="🔹 Wybrany plik:\n> {}"):
    if default_path:
        normalized = os.path.abspath(default_path)
        if os.path.isfile(normalized) and normalized.lower().endswith(extensions):
            print(preview_label.format(normalized))
            return normalized
    while True:
        p = input(prompt).strip().strip('"')
        if os.path.isfile(p) and p.lower().endswith(extensions):
            return os.path.abspath(p)
        print(f"❌ Zły plik. Wymagane: {', '.join(extensions)}")

def choose_icon(extensions):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    try:
        for name in os.listdir(base_dir):
            if name.lower().endswith(extensions):
                candidates.append(os.path.join(base_dir, name))
    except FileNotFoundError:
        candidates = []

    candidates.sort(key=lambda p: os.path.basename(p).lower())
    if candidates:
        print("   ↳ Wykryte pliki graficzne w folderze konwertera:")
        for idx, path in enumerate(candidates, 1):
            print(f"     [{idx}] {os.path.basename(path)}")
        print("     [0] Wskaż inny plik...")

        while True:
            choice = input("   ↳ Wybierz numer (Enter=1) lub wklej ścieżkę:\n> ").strip()
            if not choice:
                choice = "1"
            if choice.isdigit():
                idx = int(choice)
                if idx == 0:
                    break
                if 1 <= idx <= len(candidates):
                    selected = candidates[idx - 1]
                    print(f"   ✓ Wybrano: {selected}")
                    return selected
                print(f"❌ Nieprawidłowy numer (0-{len(candidates)}).")
            else:
                candidate = choice.strip('"')
                if os.path.isfile(candidate) and candidate.lower().endswith(extensions):
                    return candidate
                print(f"❌ Zły plik. Wymagane: {', '.join(extensions)}")

    return ask_for_file("   ↳ Podaj ikonę:\n> ", extensions, preview_label="   ✓ Wybrano: {}")

def resource_sep():
    return ';' if os.name == 'nt' else ':'

def find_localization_dirs(script_path):
    """Return (source, destination) pairs for localization folders."""

    results = []
    base_dir = os.path.dirname(os.path.abspath(script_path))
    candidates = [
        (os.path.join(base_dir, "picorgftp_sql", "Localization"),
         "picorgftp_sql/Localization"),
        (os.path.join(base_dir, "Localization"), "Localization"),
    ]
    for src, dest in candidates:
        if os.path.isdir(src):
            results.append((src, dest))
    return results

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


def safe_remove(path):
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"⚠️ Nie udało się usunąć pliku {path}: {exc}")


def safe_rmtree(path):
    if not os.path.isdir(path):
        return
    try:
        shutil.rmtree(path)
    except Exception as exc:
        print(f"⚠️ Nie udało się usunąć katalogu {path}: {exc}")


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
    default_script = ""
    if len(sys.argv) > 1:
        default_script = sys.argv[1]
        if not os.path.isfile(default_script):
            print(f"⚠️ Podany plik nie istnieje: {default_script}")
            default_script = ""

    script = ask_for_file(
        "🔹 Ścieżka do .py/.pyw aplikacji:\n> ",
        (".py", ".pyw"),
        default_script,
        "🔹 Ścieżka do .py/.pyw aplikacji:\n> {}"
    )
    dstdir = os.path.dirname(script)
    base = os.path.splitext(os.path.basename(script))[0]
    exe_ext = ".exe" if os.name=="nt" else ""

    windowed = ask_yes_no("🔹 Aplikacja bez konsoli (GUI)?", True)
    onefile  = ask_yes_no("🔹 Zbudować 1 plik (onefile)?", True)
    add_icon = ask_yes_no("🔹 Dodać ikonę (.ico/.png/.jpg)?", False)

    cleanup_files = []
    cleanup_dirs = []

    icon = ""
    if add_icon:
        icon_in = choose_icon((".ico",".png",".jpg",".jpeg"))
        if icon_in.lower().endswith(".ico"):
            icon = icon_in
        else:
            icon = convert_to_ico(icon_in)
            if icon:
                cleanup_files.append(icon)

    cmd = [sys.executable, "-m", "PyInstaller", script, f"--distpath={dstdir}"]
    if onefile: cmd.append("--onefile")
    if windowed: cmd.append("--windowed")
    if icon: cmd.append(f"--icon={icon}")

    # dołącz tłumaczenia, aby zmiana języka działała w pliku EXE
    localization_dirs = find_localization_dirs(script)
    if localization_dirs:
        print("🔹 Dodawanie katalogów tłumaczeń:")
        for src, dest in localization_dirs:
            cmd.append(f"--add-data={src}{resource_sep()}{dest}")
            print(f"   ↳ {src} ➜ {dest}")
    else:
        print('⚠️ Nie znaleziono katalogu "Localization" do spakowania.')

    # === CRUCIAL: mysql-connector + locales ===
    cmd += [
        "--hidden-import=mysql.connector",
        "--collect-submodules=mysql.connector",
        "--collect-submodules=mysql.connector.locales",
        "--collect-data=mysql.connector",
        "--collect-data=mysql.connector.locales",
        "--hidden-import=mysql.connector.locales.eng.client_error",
        "--hidden-import=tkinterdnd2",
        "--collect-submodules=tkinterdnd2",
    ]
    # opcjonalnie inne języki:
    for lang in ("fra","ita","jpn","por","rus","spa","zho"):
        cmd.append(f"--hidden-import=mysql.connector.locales.{lang}.client_error")

    # runtime hook z wymuszeniem ENG
    hook = make_runtime_hook()
    cleanup_files.append(hook)
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
    build_root = None
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print("❌ Błąd PyInstaller:", e)
    else:
        exe = (os.path.join(dstdir, base+exe_ext) if onefile
               else os.path.join(dstdir, base, base+exe_ext))
        print("\n✅ Gotowe!\n📁", exe)

        spec_path = os.path.join(os.getcwd(), f"{base}.spec")
        build_root = os.path.join(os.getcwd(), "build")
        build_target = os.path.join(build_root, base)

        cleanup_files.append(spec_path)
        cleanup_dirs.append(build_target)
    finally:
        for item in cleanup_files:
            safe_remove(item)
        for directory in cleanup_dirs:
            safe_rmtree(directory)
        if build_root and os.path.isdir(build_root) and not os.listdir(build_root):
            safe_rmtree(build_root)

if __name__ == "__main__":
    main()
