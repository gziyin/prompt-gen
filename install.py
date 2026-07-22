#!/usr/bin/env python3
"""Install the `prompt-gen` global command for the current user.

Cross-platform, standard-library only. Writes a thin shim into the user's PATH
directory that forwards to this repo's real launcher (``bin/prompt-gen``), and
ensures that directory is on PATH. Idempotent and safe to re-run.

Usage:
    python install.py            # install / ensure installed (silent unless changed)
    python install.py --verbose  # show what it does
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
VERBOSE = "--verbose" in sys.argv


def log(msg: str) -> None:
    if VERBOSE:
        print(msg)


def detect_bin_dir() -> Path:
    """User-level bin directory that should be on PATH."""
    base = Path.home() / "bin" if os.name == "nt" else Path.home() / ".local" / "bin"
    base.mkdir(parents=True, exist_ok=True)
    return base


def real_launcher() -> Path:
    return REPO / "bin" / ("prompt-gen.cmd" if os.name == "nt" else "prompt-gen")


def write_shims(bin_dir: Path) -> bool:
    """Write the forwarding shim(s). Return True if anything was (re)written."""
    changed = False
    target = real_launcher()
    if os.name == "nt":
        cmd_path = bin_dir / "prompt-gen.cmd"
        content = f'@echo off\ncall "{target}" %*\n'
        if not cmd_path.exists() or cmd_path.read_text(encoding="utf-8") != content:
            cmd_path.write_text(content, encoding="utf-8")
            changed = True
            log(f"wrote {cmd_path}")
        # No-extension shim so Git Bash can also call `prompt-gen`
        sh_path = bin_dir / "prompt-gen"
        sh_content = f'#!/usr/bin/env bash\nexec "{REPO}/bin/prompt-gen" "$@"\n'
        if not sh_path.exists() or sh_path.read_text(encoding="utf-8") != sh_content:
            sh_path.write_text(sh_content, encoding="utf-8")
            sh_path.chmod(0o755)
            changed = True
            log(f"wrote {sh_path}")
    else:
        sh_path = bin_dir / "prompt-gen"
        content = f'#!/usr/bin/env bash\nexec "{REPO}/bin/prompt-gen" "$@"\n'
        if not sh_path.exists() or sh_path.read_text(encoding="utf-8") != content:
            sh_path.write_text(content, encoding="utf-8")
            sh_path.chmod(0o755)
            changed = True
            log(f"wrote {sh_path}")
    return changed


def ensure_on_path(bin_dir: Path) -> bool:
    if os.name == "nt":
        return _ensure_on_path_windows(bin_dir)
    return _ensure_on_path_posix(bin_dir)


def _ensure_on_path_windows(bin_dir: Path) -> bool:
    import subprocess

    ps = (
        "$p = [Environment]::GetEnvironmentVariable('PATH','User');"
        f" if ($p -notlike '*{bin_dir}*') {{"
        f" [Environment]::SetEnvironmentVariable('PATH', \"$p;{bin_dir}\", 'User');"
        " Write-Output 'CHANGED' }}"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        changed = "CHANGED" in out.stdout
        if changed:
            log("appended bin dir to User PATH")
        return changed
    except Exception as exc:  # noqa: BLE001 - best effort
        log(f"[warn] 无法修改 PATH: {exc}")
        return False


def _ensure_on_path_posix(bin_dir: Path) -> bool:
    if str(bin_dir) in os.environ.get("PATH", "").split(os.pathsep):
        return False
    line = f'export PATH="$HOME/.local/bin:$PATH"\n'
    rc_candidates = [
        Path.home() / ".bashrc",
        Path.home() / ".zshrc",
        Path.home() / ".profile",
    ]
    for rc in rc_candidates:
        if rc.exists():
            try:
                text = rc.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                text = ""
            if str(bin_dir) in text or ".local/bin" in text:
                return False
            with rc.open("a", encoding="utf-8") as fh:
                fh.write("\n# prompt-gen global command\n" + line)
            log(f"appended PATH line to {rc}")
            return True
    rc_candidates[0].write_text("# prompt-gen global command\n" + line, encoding="utf-8")
    log(f"created {rc_candidates[0]} with PATH line")
    return True


def main() -> int:
    bin_dir = detect_bin_dir()
    changed_shim = write_shims(bin_dir)
    changed_path = ensure_on_path(bin_dir)
    if changed_shim or changed_path or VERBOSE:
        print(f"✅ 已安装全局命令 prompt-gen -> {bin_dir / 'prompt-gen'}")
        print("   重开终端后即可在任意目录使用 `prompt-gen`")
        if changed_path:
            print("   （已把 bin 目录加入 PATH，首次需重开终端生效）")
    else:
        log("prompt-gen 已安装，无需更改。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
