#!/usr/bin/env python3
"""Rebuild this repository's README and banners from the packages it contains.

    python3 scripts/update_readme.py             check every package, then rewrite the files
    python3 scripts/update_readme.py --validate  only check every package

The same file runs in homebrew-tap and scoop-bucket. It needs only the standard library.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SHA256 = re.compile(r"(sha256:)?[0-9a-fA-F]{64}")
SCOOP_ARCHITECTURES = {"64bit": "x64", "arm64": "arm64", "32bit": "x86"}
BANNER_ROWS = 4


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    description: str
    homepage: str
    systems: tuple[str, ...]
    architectures: tuple[str, ...]
    source: str
    install: str

    @property
    def runs_on(self) -> str:
        systems = ", ".join(self.systems)
        return f"{systems} ({', '.join(self.architectures)})" if self.architectures else systems


@dataclass(frozen=True)
class Profile:
    manager: str
    manager_url: str
    slug: str
    display: str
    tagline: str
    command: str
    accent: tuple[str, str]
    badge: str


def repository_slug(default: str) -> str:
    slug = os.environ.get("GITHUB_REPOSITORY")
    if slug:
        return slug
    config = ROOT / ".git" / "config"
    if config.is_file():
        match = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?\s", config.read_text("utf-8"))
        if match:
            return match.group(1)
    return default


def ruby_field(source: str, name: str) -> str:
    match = re.search(rf'^\s*{name}\s+"((?:[^"\\]|\\.)*)"', source, re.MULTILINE)
    return re.sub(r"\\(.)", r"\1", match.group(1)) if match else ""


def require(problems: list[str], where: str, **fields: str) -> None:
    for field, value in fields.items():
        if not value:
            problems.append(f"{where}: missing {field}")


def read_homebrew(address: str, problems: list[str]) -> list[Package]:
    packages = []
    for path in sorted([*ROOT.glob("Casks/*.rb"), *ROOT.glob("Formula/*.rb")]):
        where = path.relative_to(ROOT).as_posix()
        source = path.read_text("utf-8")
        is_cask = path.parent.name == "Casks"
        name = path.stem
        if is_cask:
            token = re.search(r'^\s*cask\s+"([^"]+)"\s+do\b', source, re.MULTILINE)
            if token is None or token.group(1) != name:
                problems.append(f'{where}: must declare cask "{name}"')
        version = ruby_field(source, "version")
        if not version and not is_cask:
            found = re.search(r"[-_/]v?(\d+(?:\.\d+)+)", ruby_field(source, "url"))
            version = found.group(1) if found else ""
        fields = {
            "version": version,
            "desc": ruby_field(source, "desc"),
            "homepage": ruby_field(source, "homepage"),
            "url": ruby_field(source, "url"),
        }
        require(problems, where, **fields)
        digests = re.findall(r'^\s*sha256\s+(?:"([^"]*)"|(:no_check))', source, re.MULTILINE)
        if not digests:
            problems.append(f"{where}: missing sha256")
        for digest, no_check in digests:
            if not no_check and not SHA256.fullmatch(digest):
                problems.append(f"{where}: invalid sha256 {digest!r}")
        systems = tuple(
            label for block, label in (("on_macos", "macOS"), ("on_linux", "Linux"))
            if re.search(rf"^\s*{block}\b", source, re.MULTILINE)
        ) or (("macOS",) if is_cask else ("macOS", "Linux"))
        architectures = tuple(
            label for block, label in (("on_intel", "x64"), ("on_arm", "arm64"))
            if re.search(rf"^\s*{block}\b", source, re.MULTILINE)
        )
        flag = "--cask " if is_cask else ""
        packages.append(
            Package(
                name=name,
                version=version,
                description=fields["desc"],
                homepage=fields["homepage"],
                systems=systems,
                architectures=architectures,
                source=where,
                install=f"brew install {flag}{address}/{name}",
            )
        )
    return packages


def read_scoop(problems: list[str]) -> list[Package]:
    folder = ROOT / "bucket" if (ROOT / "bucket").is_dir() else ROOT
    packages = []
    for path in sorted(p for p in folder.glob("*.json") if not p.name.startswith(".")):
        where = path.relative_to(ROOT).as_posix()
        try:
            manifest = json.loads(path.read_text("utf-8"))
        except ValueError as error:
            problems.append(f"{where}: invalid JSON ({error})")
            continue
        if not isinstance(manifest, dict):
            problems.append(f"{where}: must contain one JSON object")
            continue
        require(
            problems,
            where,
            **{key: str(manifest.get(key) or "") for key in ("version", "description", "homepage")},
        )
        license_value = manifest.get("license")
        if isinstance(license_value, dict):
            license_value = license_value.get("identifier")
        require(problems, where, license=str(license_value or ""))
        architecture = manifest.get("architecture") or {}
        for scope, entry in [*architecture.items(), ("", manifest)]:
            if scope == "" and architecture:
                continue
            label = f"{where} ({scope})" if scope else where
            require(problems, label, url=str(entry.get("url") or ""))
            hashes = entry.get("hash")
            hashes = hashes if isinstance(hashes, list) else [hashes]
            if not all(isinstance(h, str) and SHA256.fullmatch(h) for h in hashes):
                problems.append(f"{label}: missing or invalid hash")
        packages.append(
            Package(
                name=path.stem,
                version=str(manifest.get("version", "")),
                description=str(manifest.get("description", "")),
                homepage=str(manifest.get("homepage", "")),
                systems=("Windows",),
                architectures=tuple(
                    SCOOP_ARCHITECTURES[key]
                    for key in SCOOP_ARCHITECTURES
                    if key in architecture
                ),
                source=where,
                install=f"scoop install {path.stem}",
            )
        )
    return packages


def load() -> tuple[Profile, list[Package], list[str]]:
    problems: list[str] = []
    if (ROOT / "Casks").is_dir() or (ROOT / "Formula").is_dir():
        slug = repository_slug("kaanxsrd/homebrew-tap")
        owner, repository = slug.split("/", 1)
        address = f"{owner}/{repository.removeprefix('homebrew-')}"
        profile = Profile(
            manager="Homebrew",
            manager_url="https://brew.sh",
            slug=slug,
            display=address,
            tagline="Every tool, one brew install away.",
            command="brew install",
            accent=("#fbb040", "#f97316"),
            badge="homebrew",
        )
        return profile, read_homebrew(address, problems), problems
    slug = repository_slug("kaanxsrd/scoop-bucket")
    profile = Profile(
        manager="Scoop",
        manager_url="https://scoop.sh",
        slug=slug,
        display=slug.split("/", 1)[1],
        tagline="Every tool, one scoop install away.",
        command="scoop install",
        accent=("#5cc2ff", "#8b7cf6"),
        badge="windows",
    )
    return profile, read_scoop(problems), problems


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def badge(label: str, message: str, color: str, target: str, logo: str = "") -> str:
    def part(text: str) -> str:
        return quote(text.replace("-", "--").replace(" ", "_"), safe="·+_")

    url = f"https://img.shields.io/badge/{part(label)}-{part(message)}-{color}?style=flat-square"
    if logo:
        url += f"&logo={logo}&logoColor=white"
    return f"[![{label}]({url})]({target})"


def distinct(packages: list[Package], attribute: str) -> list[str]:
    seen: dict[str, None] = {}
    for package in packages:
        seen.update(dict.fromkeys(getattr(package, attribute)))
    return list(seen)


def homebrew_usage(profile: Profile) -> tuple[str, str, str]:
    install = (
        "```sh\n"
        f"brew install --cask {profile.display}/<package>\n"
        "```\n\n"
        "Homebrew adds this tap by itself the first time, so there is no separate `brew tap` step."
    )
    upgrade = (
        "```sh\n"
        "brew update && brew upgrade --cask <package>\n"
        "brew uninstall --cask <package>\n"
        f"brew untap {profile.display}   # optional: remove this tap\n"
        "```"
    )
    publish = (
        "Have the project's release pipeline commit one file: `Casks/<package>.rb` for a binary, "
        "or `Formula/<package>.rb` for a formula. It needs a `desc`, `homepage`, `url` and "
        "`sha256`, and the file name must match the package name."
    )
    return install, upgrade, publish


def scoop_usage(profile: Profile) -> tuple[str, str, str]:
    owner = profile.slug.split("/", 1)[0]
    install = (
        "```powershell\n"
        f"scoop bucket add {owner} https://github.com/{profile.slug}\n"
        "scoop install <package>\n"
        "```\n\n"
        "You only need to add the bucket once."
    )
    upgrade = (
        "```powershell\n"
        "scoop update; scoop update <package>\n"
        "scoop uninstall <package>\n"
        f"scoop bucket rm {owner}   # optional: remove this bucket\n"
        "```"
    )
    publish = (
        "Have the project's release pipeline commit one file: `<package>.json` in the root of "
        "this repository. It needs a `version`, `description`, `homepage`, `license`, and a `url` "
        "with a SHA-256 `hash`, either directly or for each entry under `architecture`."
    )
    return install, upgrade, publish


def render_readme(profile: Profile, packages: list[Package]) -> str:
    install, upgrade, publish = (
        homebrew_usage(profile) if profile.manager == "Homebrew" else scoop_usage(profile)
    )
    systems = distinct(packages, "systems")
    architectures = distinct(packages, "architectures")
    platform_label = " · ".join(systems) or "All"
    platform_message = " + ".join(architectures) or "any"
    count = len(packages)
    noun = "package" if count == 1 else "packages"
    accent = profile.accent[0].removeprefix("#")
    rows = "\n".join(
        f"| [**{cell(p.name)}**]({p.homepage}) | `{cell(p.version)}` | {cell(p.runs_on)} "
        f"| {cell(p.description)} | `{cell(p.install)}` |"
        for p in packages
    )
    table = (
        "| Package | Version | Runs on | What it does | Install |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"{rows}"
        if packages
        else "_No packages yet._"
    )
    tool = "a cask" if profile.manager == "Homebrew" else "a manifest"
    return f"""<!-- Generated by scripts/update_readme.py after every package change. Edit that script, not this file. -->
<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
  <img alt="{html.escape(profile.display)}: {count} {noun} for {html.escape(platform_label)}" src="assets/banner-light.svg" width="100%">
</picture>

<br>

**Every command-line tool from Vante, installed and updated with [{profile.manager}]({profile.manager_url}).**

<br>

{badge(profile.manager, profile.display, accent, profile.manager_url, profile.badge)}
{badge("packages", str(count), "8b7cf6", "#packages")}
{badge(platform_label, platform_message, "111111", "#packages")}
{badge("updates", "automatic", "0b9472", "#how-it-works", "githubactions")}

**[Packages](#packages)** ·
**[Install](#install)** ·
**[Upgrade](#upgrade-and-uninstall)** ·
**[How it works](#how-it-works)** ·
**[Add a package](#add-a-package)**

</div>

<br>

## Packages

{table}

## Install

{install}

## Upgrade and uninstall

{upgrade}

## How it works

```mermaid
flowchart LR
  A([A project tags a release]) --> B[Its pipeline commits {tool} here]
  B --> C{{Every package validated}}
  C --> D[This README and the banners rebuild]
  D --> E([Everyone can upgrade])
```

Each project's release pipeline publishes its own builds and commits the result here, with the download URLs and SHA-256 checksums of that release. GitHub Actions then checks every package and rebuilds this page, so the list above is always what the repository really contains.

## Add a package

{publish}

That is the only step. The package appears above after the next push, with its version and platforms read from that file. A malformed package fails the [workflow](.github/workflows/update-readme.yml) and leaves this page unchanged.

<details>
<summary><b>Publishing from a release pipeline</b></summary>

<br>

The pipeline needs a token with **Contents: read and write** on this repository. To publish under your own account rather than a bot, commit with your GitHub no-reply address:

```sh
git config user.name "$GITHUB_REPOSITORY_OWNER"
git config user.email "${{GITHUB_REPOSITORY_OWNER_ID}}+${{GITHUB_REPOSITORY_OWNER}}@users.noreply.github.com"
```

With GoReleaser, set the same identity under `commit_author`.

</details>

<div align="center">
<br>
<sub>Generated automatically. Please don't edit package files by hand: the next release replaces them.</sub>
</div>
"""


THEMES = {
    "dark": {
        "background": "#07090f",
        "dot": "#ffffff",
        "dot_opacity": "0.05",
        "text": "#f3f6fb",
        "muted": "#7c8696",
        "panel": "#ffffff",
        "panel_opacity": "0.04",
        "line": "#ffffff",
        "line_opacity": "0.11",
        "glyph": "#07090f",
    },
    "light": {
        "background": "#ffffff",
        "dot": "#0a1428",
        "dot_opacity": "0.07",
        "text": "#10151f",
        "muted": "#6b7482",
        "panel": "#0a1428",
        "panel_opacity": "0.025",
        "line": "#0a1428",
        "line_opacity": "0.12",
        "glyph": "#ffffff",
    },
}
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


def render_banner(profile: Profile, packages: list[Package], theme: str) -> str:
    c = THEMES[theme]
    start, end = profile.accent
    shown = packages[:BANNER_ROWS]
    extra = len(packages) - len(shown)
    rows_height = 46 * len(shown) + (30 if extra else 0)
    card_height = max(rows_height + 74, 130)
    card_y = (400 - card_height) // 2
    systems = " · ".join(distinct(packages, "systems")) or profile.manager
    count = len(packages)
    chips = [f"{count} package{'' if count == 1 else 's'}", systems, "auto-updated"]

    chip_parts = []
    x = 88
    for label in chips:
        width = len(label) * 9 + 32
        chip_parts.append(
            f'<rect x="{x}" y="288" width="{width}" height="38" rx="19" fill="{c["panel"]}" '
            f'fill-opacity="{c["panel_opacity"]}" stroke="{c["line"]}" '
            f'stroke-opacity="{c["line_opacity"]}"/>'
            f'<text x="{x + 16}" y="312" font-family="{MONO}" font-size="15" '
            f'fill="{c["text"]}">{html.escape(label)}</text>'
        )
        x += width + 10

    row_parts = []
    y = card_y + 66
    for package in shown:
        row_parts.append(
            f'<text x="812" y="{y + 24}" font-family="{MONO}" font-size="18" font-weight="600" '
            f'fill="{c["text"]}">{html.escape(package.name[:22])}</text>'
            f'<text x="1172" y="{y + 24}" text-anchor="end" font-family="{MONO}" font-size="16" '
            f'fill="url(#accent)">v{html.escape(package.version[:14])}</text>'
        )
        y += 46
    if extra:
        row_parts.append(
            f'<text x="812" y="{y + 18}" font-family="{MONO}" font-size="15" '
            f'fill="{c["muted"]}">+{extra} more</text>'
        )
    if not shown:
        row_parts.append(
            f'<text x="812" y="{y + 24}" font-family="{MONO}" font-size="16" '
            f'fill="{c["muted"]}">no packages yet</text>'
        )

    owner_part, _, name_part = profile.display.rpartition("/")
    title = (
        f'<tspan fill="{c["text"]}">{html.escape(owner_part)}/</tspan>'
        f'<tspan fill="url(#accent)">{html.escape(name_part)}</tspan>'
        if owner_part
        else f'<tspan fill="url(#accent)">{html.escape(name_part)}</tspan>'
    )
    title_size = 66 if len(profile.display) <= 14 else 56
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 400" width="1280" height="400" role="img">
<title>{html.escape(profile.display)}</title>
<defs>
<linearGradient id="accent" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{start}"/><stop offset="1" stop-color="{end}"/></linearGradient>
<radialGradient id="glow" cx="0.1" cy="0" r="0.75"><stop stop-color="{start}" stop-opacity="0.2"/><stop offset="1" stop-color="{start}" stop-opacity="0"/></radialGradient>
<pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="{c["dot"]}" fill-opacity="{c["dot_opacity"]}"/></pattern>
</defs>
<rect width="1280" height="400" fill="{c["background"]}"/>
<rect width="1280" height="400" fill="url(#glow)"/>
<rect width="1280" height="400" fill="url(#dots)"/>
<g transform="translate(88 92)">
<path d="M38 0 76 19v38L38 76 0 57V19Z" fill="url(#accent)"/>
<path d="M38 38 76 19M38 38 0 19M38 38v38" stroke="{c["glyph"]}" stroke-width="5" stroke-linejoin="round" stroke-opacity="0.75"/>
</g>
<text x="184" y="154" font-family="{SANS}" font-size="{title_size}" font-weight="800" letter-spacing="-2">{title}</text>
<text x="88" y="238" font-family="{SANS}" font-size="30" font-weight="600" letter-spacing="-0.5" fill="{c["text"]}">{html.escape(profile.tagline)}</text>
{"".join(chip_parts)}
<rect x="780" y="{card_y}" width="424" height="{card_height}" rx="18" fill="{c["panel"]}" fill-opacity="{c["panel_opacity"]}" stroke="{c["line"]}" stroke-opacity="{c["line_opacity"]}"/>
<text x="812" y="{card_y + 44}" font-family="{MONO}" font-size="13" letter-spacing="2" fill="{c["muted"]}">PACKAGES</text>
{"".join(row_parts)}
</svg>
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    profile, packages, problems = load()
    if problems:
        print("Invalid packages:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"{profile.display}: {len(packages)} valid package(s)")
    if "--validate" in argv:
        return 0
    write(ROOT / "README.md", render_readme(profile, packages))
    for theme in THEMES:
        write(ROOT / "assets" / f"banner-{theme}.svg", render_banner(profile, packages, theme))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
