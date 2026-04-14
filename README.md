# nvidia-smi TUI

A terminal dashboard for monitoring NVIDIA GPU stats, built with [Textual](https://github.com/Textualize/textual).

## Features

- Live VRAM and GPU utilization bars (htop-style)
- Sparkline history graphs for GPU and VRAM usage
- Process table showing what's using the GPU
- WSL2 support (scrapes `nvidia-smi` output directly due to WDDM limitations)

## Requirements

- Python 3.8+
- `textual`
- `nvidia-smi` in your PATH (or on WSL2, the Linux nvidia-smi provided by the CUDA WSL driver)

## Installation

```bash
pip install textual
```

## Usage

```bash
python3 smi.py
```

## Keybindings

| Key | Action |
|-----|--------|
| `d` | Toggle dark/light mode |
| `q` | Quit |

## Notes

- On WSL2, per-process VRAM usage will show as `N/A` — this is a driver limitation with WDDM and cannot be worked around.
- The sparklines scale relative to the data in the current 120-second window, not absolute 100% usage.
