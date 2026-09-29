#!/usr/bin/env python3
"""
Check upstream versions for this fork's hand-packaged -bin/binary
templates and, on a new version, rewrite the template's `version=` and
`checksum=` fields in place.

Only touches `version=` and `checksum=` — every `distfiles=` URL in these
templates already interpolates `${version}`, so bumping the version alone
repoints the download URLs; only the checksums need recomputing.

Usage:
    update_bin_packages.py check                 # print JSON, no changes
    update_bin_packages.py apply <pkgname>        # bump one template

"check" prints a JSON object per package: {pkgname: {current, latest,
needs_update, restricted}}. "apply" re-checks the given package, downloads
its new assets, hashes them, and rewrites its template file; it exits 0
and prints nothing further if no update is needed.
"""
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = {"User-Agent": "void-packages-bin-updater (github actions)"}


def http_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def http_text(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode()


def sha256_url(url):
    h = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def latest_github_tag(repo):
    return http_json(f"https://api.github.com/repos/{repo}/releases/latest")["tag_name"].lstrip("v")


def latest_claude_desktop_version():
    text = http_text(
        "https://downloads.claude.ai/claude-desktop/apt/stable/dists/stable/main/binary-amd64/Packages"
    )
    versions = re.findall(r"^Version: (\S+)$", text, re.M)

    def key(v):
        return [int(p) if p.isdigit() else p for p in re.split(r"[.+]", v)]

    return sorted(versions, key=key)[-1]


# Each package: how to find the latest version, and (for versioned
# packages) the ordered per-arch asset URLs to hash, in the exact order
# they appear in that arch's `distfiles=` in the template.
PACKAGES = {
    "vscode-bin": {
        "restricted": True,
        "latest_version": lambda: http_json(
            "https://update.code.visualstudio.com/api/update/linux-x64/stable/latest"
        )["productVersion"],
        "assets": lambda v: {
            "x86_64": [f"https://update.code.visualstudio.com/{v}/linux-x64/stable"],
            "aarch64": [f"https://update.code.visualstudio.com/{v}/linux-arm64/stable"],
        },
    },
    "sourcegit-bin": {
        "restricted": False,
        "latest_version": lambda: latest_github_tag("sourcegit-scm/sourcegit"),
        "assets": lambda v: {
            "x86_64": [
                f"https://github.com/sourcegit-scm/sourcegit/releases/download/v{v}/sourcegit_{v}-1_amd64.deb",
                f"https://raw.githubusercontent.com/sourcegit-scm/sourcegit/v{v}/LICENSE",
            ],
            "aarch64": [
                f"https://github.com/sourcegit-scm/sourcegit/releases/download/v{v}/sourcegit_{v}-1_arm64.deb",
                f"https://raw.githubusercontent.com/sourcegit-scm/sourcegit/v{v}/LICENSE",
            ],
        },
    },
    "opencode-desktop-bin": {
        "restricted": False,
        "latest_version": lambda: http_json("https://opencode.ai/update/api/latest/desktop/opencode")[
            "version"
        ],
        "assets": lambda v: {
            "x86_64": [f"https://opencode.ai/files/bin/{v}/opencode-desktop-linux-amd64.deb"],
            "aarch64": [f"https://opencode.ai/files/bin/{v}/opencode-desktop-linux-arm64.deb"],
        },
    },
    "pear-desktop-bin": {
        "restricted": False,
        "latest_version": lambda: latest_github_tag("pear-devs/pear-desktop"),
        "assets": lambda v: {
            "x86_64": [
                f"https://github.com/pear-devs/pear-desktop/releases/download/v{v}/youtube-music-{v}.tar.gz",
                f"https://github.com/pear-devs/pear-desktop/raw/v{v}/license",
            ],
            "aarch64": [
                f"https://github.com/pear-devs/pear-desktop/releases/download/v{v}/youtube-music-{v}-arm64.tar.gz",
                f"https://github.com/pear-devs/pear-desktop/raw/v{v}/license",
            ],
        },
    },
    "cherry-studio-bin": {
        "restricted": False,
        "latest_version": lambda: latest_github_tag("CherryHQ/cherry-studio"),
        "assets": lambda v: {
            "x86_64": [
                f"https://github.com/CherryHQ/cherry-studio/releases/download/v{v}/Cherry-Studio-{v}-linux-x64.deb",
                f"https://raw.githubusercontent.com/CherryHQ/cherry-studio/v{v}/LICENSE",
            ],
            "aarch64": [
                f"https://github.com/CherryHQ/cherry-studio/releases/download/v{v}/Cherry-Studio-{v}-linux-arm64.deb",
                f"https://raw.githubusercontent.com/CherryHQ/cherry-studio/v{v}/LICENSE",
            ],
        },
    },
    "claude-desktop": {
        "restricted": True,
        "latest_version": latest_claude_desktop_version,
        "assets": lambda v: {
            "x86_64": [
                f"https://downloads.claude.ai/claude-desktop/apt/stable/pool/main/c/claude-desktop/claude-desktop_{v}_amd64.deb"
            ],
            "aarch64": [
                f"https://downloads.claude.ai/claude-desktop/apt/stable/pool/main/c/claude-desktop/claude-desktop_{v}_arm64.deb"
            ],
        },
    },
    "nerd-fonts-sf-mono": {
        "restricted": True,
        # version= tracks the Nerd Fonts patcher release, not Apple's font
        # (SF-Mono.dmg is an unversioned "current" URL); only the second
        # checksum (FontPatcher.zip) ever changes on a version bump.
        "latest_version": lambda: latest_github_tag("ryanoasis/nerd-fonts"),
        "assets": None,
    },
    "zed": {
        "restricted": False,
        "latest_version": lambda: latest_github_tag("zed-industries/zed"),
        "assets": lambda v: {
            "x86_64": [f"https://github.com/zed-industries/zed/releases/download/v{v}/zed-linux-x86_64.tar.gz"],
            "aarch64": [f"https://github.com/zed-industries/zed/releases/download/v{v}/zed-linux-aarch64.tar.gz"],
        },
    },
    "helium-bin": {
        "restricted": False,
        "latest_version": lambda: latest_github_tag("imputnet/helium-linux"),
        "assets": lambda v: {
            "x86_64": [
                f"https://github.com/imputnet/helium-linux/releases/download/{v}/helium-bin_{v}-1_amd64.deb",
                f"https://raw.githubusercontent.com/imputnet/helium-linux/{v}/LICENSE.ungoogled_chromium",
            ],
            "aarch64": [
                f"https://github.com/imputnet/helium-linux/releases/download/{v}/helium-bin_{v}-1_arm64.deb",
                f"https://raw.githubusercontent.com/imputnet/helium-linux/{v}/LICENSE.ungoogled_chromium",
            ],
        },
    },
}


def read_template(pkgname):
    return (ROOT / "srcpkgs" / pkgname / "template").read_text()


def write_template(pkgname, text):
    (ROOT / "srcpkgs" / pkgname / "template").write_text(text)


def current_version(pkgname):
    text = read_template(pkgname)
    m = re.search(r"^version=(\S+)$", text, re.M)
    if not m:
        raise SystemExit(f"{pkgname}: no version= line found")
    return m.group(1)


def render_checksum_value(hashes):
    if len(hashes) == 1:
        return hashes[0]
    return '"' + "\n\t ".join(hashes) + '"'


def bump_arch_case_template(text, pkgname, new_version, per_arch_hashes):
    text = re.sub(r"^version=\S+$", f"version={new_version}", text, count=1, flags=re.M)
    text = re.sub(r"^revision=\S+$", "revision=1", text, count=1, flags=re.M)
    for arch, hashes in per_arch_hashes.items():
        pattern = re.compile(
            rf"({re.escape(arch)}\)\n.*?\n\tchecksum=)(\"[^\"]*\"|\S+)(\n\t;;)", re.DOTALL
        )
        new_text, n = pattern.subn(
            lambda m: m.group(1) + render_checksum_value(hashes) + m.group(3), text, count=1
        )
        if n != 1:
            raise SystemExit(f"{pkgname}: could not find checksum block for {arch}")
        text = new_text
    return text


def bump_nerd_fonts_sf_mono(text, new_version):
    text = re.sub(r"^version=\S+$", f"version={new_version}", text, count=1, flags=re.M)
    text = re.sub(r"^revision=\S+$", "revision=1", text, count=1, flags=re.M)
    patcher_url = (
        f"https://github.com/ryanoasis/nerd-fonts/releases/download/v{new_version}/FontPatcher.zip"
    )
    new_hash = sha256_url(patcher_url)
    # checksum="<dmg hash, unchanged>\n <patcher hash>"
    text, n = re.subn(
        r'(checksum="[0-9a-f]{64}\n )[0-9a-f]{64}(")', rf"\g<1>{new_hash}\2", text, count=1
    )
    if n != 1:
        raise SystemExit("nerd-fonts-sf-mono: could not find FontPatcher checksum")
    return text


def check_all():
    out = {}
    for pkgname, spec in PACKAGES.items():
        cur = current_version(pkgname)
        try:
            latest = spec["latest_version"]()
        except Exception as e:  # noqa: BLE001 - report and keep going
            out[pkgname] = {"current": cur, "error": str(e)}
            continue
        out[pkgname] = {
            "current": cur,
            "latest": latest,
            "needs_update": latest != cur,
            "restricted": spec["restricted"],
        }
    return out


def apply_one(pkgname):
    spec = PACKAGES[pkgname]
    cur = current_version(pkgname)
    latest = spec["latest_version"]()
    if latest == cur:
        return False

    text = read_template(pkgname)
    if pkgname == "nerd-fonts-sf-mono":
        text = bump_nerd_fonts_sf_mono(text, latest)
    else:
        per_arch_assets = spec["assets"](latest)
        per_arch_hashes = {
            arch: [sha256_url(u) for u in urls] for arch, urls in per_arch_assets.items()
        }
        text = bump_arch_case_template(text, pkgname, latest, per_arch_hashes)
    write_template(pkgname, text)
    print(f"{pkgname}: {cur} -> {latest}", file=sys.stderr)
    return True


def bump_all():
    """Apply every pending update; return (open_pkgs, restricted_pkgs)."""
    status = check_all()
    open_pkgs, restricted_pkgs = [], []
    for pkgname, info in status.items():
        if not info.get("needs_update"):
            continue
        if not apply_one(pkgname):
            continue  # raced with upstream between check_all() and apply_one()
        (restricted_pkgs if info["restricted"] else open_pkgs).append(pkgname)
    return open_pkgs, restricted_pkgs


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "check":
        print(json.dumps(check_all(), indent=2))
    elif cmd == "apply":
        pkgname = sys.argv[2]
        updated = apply_one(pkgname)
        print(json.dumps({"pkgname": pkgname, "updated": updated}))
    elif cmd == "bump-all":
        import os

        open_pkgs, restricted_pkgs = bump_all()
        result = {"open": open_pkgs, "restricted": restricted_pkgs}
        print(json.dumps(result, indent=2), file=sys.stderr)
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a") as f:
                f.write(f"open={json.dumps(open_pkgs)}\n")
                f.write(f"restricted={json.dumps(restricted_pkgs)}\n")
        else:
            print(json.dumps(result))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
