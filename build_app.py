"""Build ImageTools.app (macOS) or ImageTools.exe (Windows)."""

import os
import sys
import shutil
from pathlib import Path

PROJECT = Path(__file__).parent
STATIC   = PROJECT / "static"
DIST     = PROJECT / "dist"
BUILD    = PROJECT / "build"

IS_MAC    = sys.platform == "darwin"
IS_WIN    = sys.platform == "win32"


def _require_pyinstaller():
    try:
        import PyInstaller  # noqa
        return
    except ImportError:
        pass
    sub = [sys.executable, "-m", "pip", "install", "pyinstaller"]
    print("PyInstaller not found — installing …")
    sys.stdout.flush()
    rc = os.spawnlp(os.P_WAIT, sub[0], *sub)
    if rc != 0:
        sys.exit(rc)


def _make_icon():
    """Generate platform icon from EditImage.svg using cairosvg + Pillow."""
    svg = STATIC / "EditImage.svg"
    if not svg.exists():
        print("  No EditImage.svg found — skipping icon")
        return None

    out = STATIC / ("app_icon.png" if IS_MAC else "app_icon.ico")

    # Install cairosvg at build time (lightweight pure-Python SVG→PNG)
    sub = [sys.executable, "-m", "pip", "install", "-q", "cairosvg"]
    rc = os.spawnlp(os.P_WAIT, sub[0], *sub)
    if rc != 0:
        print("  cairosvg install failed — skipping icon")
        return None

    import io
    from PIL import Image
    import cairosvg

    png_data = cairosvg.svg2png(url=str(svg), output_width=256, output_height=256)
    img = Image.open(io.BytesIO(png_data))

    if IS_MAC:
        img.save(out)
    else:
        img.save(out, format="ICO", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])

    print(f"  Icon generated: {out.name}")
    return out


def _set_macos_metadata(app: Path):
    """Set macOS Info.plist metadata."""
    plist = app / "Contents" / "Info.plist"
    raw = plist.read_text(encoding="utf-8")

    # PyInstaller generates basic plist — inject our keys
    import plistlib
    info = plistlib.loads(raw.encode("utf-8"))
    info["CFBundleName"]        = "ImageTools"
    info["CFBundleDisplayName"]  = "ImageTools"
    info["CFBundleIdentifier"]   = "com.imagetools.app"
    info["CFBundleShortVersionString"] = "1.0.0"
    info["CFBundleVersion"] = "1.0.0"
    info["NSHighResolutionCapable"] = True
    plist.write_bytes(plistlib.dumps(info))

    # Rename the executable inside the app so the app name matches
    print(f"  Updated Info.plist in {app.name}")


def main():
    print(f"Platform: {'macOS' if IS_MAC else 'Windows' if IS_WIN else sys.platform}")

    # Clean previous builds
    for d in [DIST, BUILD]:
        if d.exists():
            shutil.rmtree(d)
    print("Cleaned dist/ build/")

    _require_pyinstaller()
    import PyInstaller.__main__

    icon = _make_icon()

    args = [
        str(PROJECT / "main.py"),
        "--name", "ImageTools",
        "--windowed",
        "--noconfirm",
        "--clean",
        f"--workpath={BUILD}",
        f"--distpath={DIST}",
        f"--add-data={STATIC}{os.pathsep}static",
        "--hidden-import=PyQt6.QtSvg",
        "--hidden-import=PyQt6.QtSvgWidgets",
    ]

    if icon:
        args.append(f"--icon={icon}")

    if IS_MAC:
        args.append("--onedir")
    elif IS_WIN:
        args.append("--onefile")
    else:
        print("Unsupported platform for GUI packaging.")
        sys.exit(1)

    print(f"\nRunning PyInstaller with:\n  {' '.join(args)}\n")
    sys.stdout.flush()
    PyInstaller.__main__.run(args)

    if IS_MAC:
        app = DIST / "ImageTools.app"
        if app.exists():
            _set_macos_metadata(app)
            print(f"\n✅ {app}  ({_app_size(app)})")
        else:
            print(f"\n❌ App not found at {app}")
    else:
        exe = DIST / "ImageTools.exe"
        if exe.exists():
            sz = _fmt_size(exe.stat().st_size)
            print(f"\n✅ {exe}  ({sz})")
        else:
            print(f"\n❌ Exe not found at {exe}")

    # Clean up temp icon files
    for f in [STATIC / "app_icon.png", STATIC / "app_icon.ico"]:
        if f.exists():
            f.unlink()


def _app_size(app: Path) -> str:
    total = sum(f.stat().st_size for f in app.rglob("*") if f.is_file())
    return _fmt_size(total)


def _fmt_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


if __name__ == "__main__":
    main()
