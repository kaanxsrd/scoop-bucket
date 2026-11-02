<div align="center">

<a href="https://hookline.vante.app"><img alt="Hookline: Catch every webhook. Replay anything." src="https://hookline.vante.app/readme/banner-dark.webp" width="100%"></a>

<br>

**The official [Scoop](https://scoop.sh) bucket for the Hookline CLI on Windows.**

[![Scoop](https://img.shields.io/badge/scoop-hookline-4a90d9?style=flat-square&logo=windows&logoColor=white)](#install)
[![Version](https://img.shields.io/npm/v/hookline-cli?style=flat-square&label=version&color=8b7cf6)](https://hookline.vante.app/changelog)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-8b7cf6?style=flat-square)](https://www.gnu.org/licenses/gpl-3.0.html)

**[Hookline](https://hookline.vante.app)** ·
**[CLI docs](https://hookline.vante.app/docs/cli)** ·
**[Changelog](https://hookline.vante.app/changelog)**

</div>

<br>

[Hookline](https://hookline.vante.app) gives you a webhook URL that captures every request, shows it live and replays it anywhere. The `hookline` CLI forwards those webhooks to `localhost`, so you can develop against real Stripe, GitHub or Shopify events on your own machine.

## Install

```powershell
scoop bucket add hookline https://github.com/kaanxsrd/scoop-bucket
scoop install hookline
```

Then sign in and start forwarding:

```powershell
hookline login
hookline listen <slug> --forward http://localhost:3000/api/webhooks
```

The manifest installs the native binary for Windows on x64 or arm64.

## Upgrade and uninstall

```powershell
scoop update hookline
scoop uninstall hookline
scoop bucket rm hookline   # optional: remove this bucket
```

## Other ways to install

| Platform | Command |
| --- | --- |
| npm (any platform, Node 18+) | `npm install -g hookline-cli` |
| macOS and Linux (Homebrew) | `brew install --cask kaanxsrd/tap/hookline` |

## About this repository

[`hookline.json`](hookline.json) is generated and committed by the Hookline release pipeline on every release, with the download URLs and SHA-256 checksums of that release. Please don't edit it by hand. Report problems with the CLI through [hookline.vante.app](https://hookline.vante.app).
