# DVFix

CLI utility to convert Dolby Vision to HDR10 while preserving everything else in the file.

`dvfix.py` is the main cross-platform entry point. `dvfix.ps1` is a Windows wrapper, and `dvfix.sh` is a Unix shell wrapper. Both wrappers forward arguments to `dvfix.py` so you can launch DVFix without typing the Python command directly.

## Requirements

### Common

- Python 3
- `ffmpeg` and `ffprobe` available on `PATH` or placed next to `dvfix.py`
- `dovi_tool` available on `PATH` or placed next to `dvfix.py` for Dolby Vision Profile 7 sources

### Windows

- `python` can run from PowerShell
- `.\dvfix.ps1` is available as a convenience launcher
- For Profile 5, a Vulkan runtime providing `vulkan-1.dll` is required when using `libplacebo`

### Linux

- Run the tool with `python3`
- For Profile 5, use an FFmpeg build with `libplacebo` and a working Vulkan loader such as `libvulkan.so.1`
- If you are not using NVENC on Linux, choose an encoder and preset that your FFmpeg build supports, for example `--encoder libx265 --preset medium`

## Quick Start

Run `dvfix.py` or `dvfix.sh` with no flags to launch the interactive wizard. The wizard can guide you into a conversion run, an `--info` scan, or an environment check.

### Windows

```powershell
python .\dvfix.py
.\dvfix.ps1 input.mkv
python .\dvfix.py --check
python .\dvfix.py --info input.mkv
```

### Linux

```bash
sh ./dvfix.sh
sh ./dvfix.sh input.mkv
sh ./dvfix.sh --check
sh ./dvfix.sh --info /path/to/input.mkv
```

## Launchers

- `dvfix.py` is the canonical entry point and works anywhere Python 3 is available.
- `dvfix.ps1` is the Windows convenience launcher.
- `dvfix.sh` is the Unix shell convenience launcher. It tries `python3` first, then falls back to `python`.
- On Unix-like systems, `sh ./dvfix.sh ...` is the safest documented form because it does not depend on the executable bit being preserved by the checkout.

## Interactive Wizard

Launching DVFix without an input path starts a guided flow with the DVFix ASCII title screen.

The wizard can:

- start a normal conversion run
- start an inspection-only `--info` run
- run the environment audit used by `--check`
- prompt for the input file or directory path
- prompt for an optional output filename for single-file runs
- prompt for basic conversion behaviors such as overwrite, replace, and dry-run

After the prompts, DVFix shows a launch summary and asks for confirmation before continuing.

By default, output is written next to the input with `.noDV` added:

`movie.mkv` -> `movie.noDV.mkv`

If you provide an output name, `.noDV` will be appended if missing and the output will still be written to the input directory.

You can also pass a directory to scan for video files recursively:

```powershell
.\dvfix.ps1 "D:\Videos"
```

```bash
sh ./dvfix.sh /mnt/media/Movies
```

## Diagnostics

Use `--check` to validate the local toolchain before converting anything:

```bash
sh ./dvfix.sh --check
```

The check reports:

- whether `ffmpeg`, `ffprobe`, and `dovi_tool` were found
- whether the selected encoder is available
- whether `dovi_rpu` is present for Profile 8
- whether `libplacebo` is present and usable for Profile 5
- whether a Vulkan loader is available

Use `--info` to inspect a file or directory and print the planned action without converting anything:

```bash
sh ./dvfix.sh --info input.mkv
```

## FFmpeg Builds For Profile 5

Profile 5 requires a `libplacebo`-enabled FFmpeg build plus Vulkan support.

DVFix prefers binaries in the working directory first, then the directory containing `dvfix.py`, then `PATH`. That means you can drop `ffmpeg` and `ffprobe` next to the script to override the system install.

Quick check:

```bash
ffmpeg -hide_banner -f lavfi -i color=c=black:s=16x16:d=0.1 -vf libplacebo -frames:v 1 -f null -
```

If you see `vkGetInstanceProcAddr` errors, your FFmpeg build is not linked against the Vulkan loader. Replace it with a Vulkan-enabled build and retry.

## What It Does

- **Profile 7**: Extracts the HEVC bitstream, removes EL + RPU via `dovi_tool`, remuxes the HDR10 base layer, and copies all other streams unchanged.
- **Profile 8**: Strips Dolby Vision RPU metadata in-place with FFmpeg and copies everything else unchanged.
- **Profile 5**: Re-encodes video to HDR10. Other streams are preserved for the full conversion path. The default encoder is `hevc_nvenc`, so non-NVENC systems should override `--encoder` and usually `--preset`.

## Options

- `--check` Validate tools and common codec capabilities, then exit.
- `--info` Inspect input and print the planned action without converting anything.
- `--encoder` Video encoder for re-encode workflows (default: `hevc_nvenc`).
- `--preset` Encoder preset for re-encode workflows (default: `p7`).
- `--cq` Constant-quality value for re-encode workflows (default: `19`).
- `--p5-force-tag` For Profile 5, skip DV processing and only tag HDR10. Colors are likely wrong.
- `--sample N` Encode only the first `N` seconds as a quick test clip.
- `--sample-rand N` Create a test clip from `N` random segments.
- `--sample-seg-len N` Segment length for `--sample-rand` (default: `2` seconds).
- `--sample-seed N` Seed for random sampling.
- `--replace` Delete the original file after a successful conversion.
- `--temp` Custom temp directory.
- `--keep-temp` Keep temp files for debugging.
- `--yes` Skip prompts.
- `--overwrite` Overwrite output if it already exists.
- `--dry-run` Print commands without executing them.
- `--no-color` or `--plain` Disable ANSI terminal styling.

## Notes

- This repo is code-only and does not include third-party binaries.
- The tool preserves audio, subtitles, attachments, chapters, and container metadata for the non-sample workflows.
- Only single-video-stream inputs are supported.
- For Profile 8, FFmpeg must include the `dovi_rpu` bitstream filter.
- For Profile 5, re-encoding is unavoidable because there is no HDR10 base layer.
- For Profile 5 on Windows, `vulkan-1.dll` must be available.
- For Profile 5 on Linux, a working Vulkan loader such as `libvulkan.so.1` must be available.
- Sample mode is currently supported only for Profile 5.
