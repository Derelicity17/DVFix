# DVFix

DVFix converts Dolby Vision video to HDR10 while preserving the rest of the file as much as possible.

It is built for local media files and keeps the workflow simple:

- run it directly against a file or directory
- launch it with no input to get guided setup
- inspect what it would do before converting anything
- validate your FFmpeg/toolchain before you start a batch

`dvfix.py` is the main entry point. `dvfix.ps1` is the Windows launcher. `dvfix.sh` is the Unix shell launcher.

## Start Here

If you just want to run it:

### Windows

```powershell
.\dvfix.ps1
.\dvfix.ps1 input.mkv
.\dvfix.ps1 "D:\Videos"
```

### Linux

```bash
sh ./dvfix.sh
sh ./dvfix.sh input.mkv
sh ./dvfix.sh /mnt/media/Movies
```

Running DVFix with no input starts a guided flow that can:

- start a conversion
- inspect a file or directory without converting
- run environment checks before processing media

## Common Tasks

Convert a single file:

```powershell
.\dvfix.ps1 input.mkv
```

```bash
sh ./dvfix.sh input.mkv
```

Inspect a file without converting:

```powershell
.\dvfix.ps1 --info input.mkv
```

```bash
sh ./dvfix.sh --info input.mkv
```

Check whether your system is ready:

```powershell
.\dvfix.ps1 --check
```

```bash
sh ./dvfix.sh --check
```

Process a directory recursively:

```powershell
.\dvfix.ps1 "D:\Videos"
```

```bash
sh ./dvfix.sh /mnt/media/Movies
```

Create a quick Profile 5 sample:

```powershell
.\dvfix.ps1 input.mkv --sample 30
```

```bash
sh ./dvfix.sh input.mkv --sample 30
```

## Output Naming

By default, DVFix writes output next to the source file and adds `.noDV` before the extension:

`movie.mkv` -> `movie.noDV.mkv`

If you pass an output name for a single-file run, DVFix still writes it to the input directory and adds `.noDV` if needed.

## What DVFix Does

- **Profile 7**: extracts the HEVC stream, removes EL/RPU with `dovi_tool`, then remuxes the HDR10 base layer
- **Profile 8**: strips Dolby Vision RPU metadata in-place with FFmpeg
- **Profile 5**: re-encodes the video stream to HDR10 because there is no HDR10 base layer to preserve

For non-sample workflows, DVFix preserves audio, subtitles, attachments, chapters, and container metadata.

## Requirements

### Required Everywhere

- Python 3
- `ffmpeg` and `ffprobe` on `PATH`, or placed next to `dvfix.py`

### Required For Specific Inputs

- `dovi_tool` for Profile 7 inputs
- FFmpeg with the `dovi_rpu` bitstream filter for Profile 8 inputs
- FFmpeg with `libplacebo` for normal Profile 5 HDR conversion

### Platform Notes

Windows:

- `.\dvfix.ps1` is the easiest launcher
- Profile 5 with `libplacebo` requires a Vulkan runtime that provides `vulkan-1.dll`

Linux:

- `sh ./dvfix.sh` is the documented launcher
- Profile 5 with `libplacebo` requires a working Vulkan loader such as `libvulkan.so.1`
- If you are not using NVENC, choose an encoder your FFmpeg build supports, for example `--encoder libx265 --preset medium`

## Checks And Inspection

Use `--check` before a big run if you want DVFix to verify the local toolchain first.

It checks for:

- `ffmpeg`
- `ffprobe`
- `dovi_tool`
- the selected encoder
- `dovi_rpu` support for Profile 8
- `libplacebo` support for Profile 5
- Vulkan loader availability

Use `--info` when you want DVFix to probe input, report the detected Dolby Vision profile, and show the planned action without writing output.

## Profile 5 Notes

Profile 5 is the most demanding path.

- It must re-encode video.
- The default encoder is `hevc_nvenc`.
- On systems without NVENC, you should override `--encoder` and usually `--preset`.
- If `libplacebo` cannot run, DVFix can still continue with `--p5-force-tag`, but colors may be wrong.

Quick FFmpeg sanity check:

```bash
ffmpeg -hide_banner -f lavfi -i color=c=black:s=16x16:d=0.1 -vf libplacebo -frames:v 1 -f null -
```

If that fails with `vkGetInstanceProcAddr`, your FFmpeg build is not linked against the Vulkan loader.

## Options

- `--check` Validate tools and common codec capabilities, then exit.
- `--info` Inspect input and print the planned action without converting anything.
- `--encoder` Video encoder for re-encode workflows. Default: `hevc_nvenc`.
- `--preset` Encoder preset for re-encode workflows. Default: `p7`.
- `--cq` Constant-quality value for re-encode workflows. Default: `19`.
- `--p5-force-tag` Skip Dolby Vision processing for Profile 5 and only tag HDR10. Colors may be wrong.
- `--sample N` Encode only the first `N` seconds.
- `--sample-rand N` Build a sample clip from `N` random segments.
- `--sample-seg-len N` Segment length for `--sample-rand`. Default: `2`.
- `--sample-seed N` Seed for repeatable random sampling.
- `--replace` Delete the original file after a successful conversion.
- `--temp` Use a custom temp directory.
- `--keep-temp` Keep temp files for debugging.
- `--yes` Skip prompts.
- `--overwrite` Replace an existing output file.
- `--dry-run` Print commands without running them.
- `--no-color` or `--plain` Disable ANSI terminal styling.

## Notes

- This repo is code-only and does not include third-party binaries.
- Only single-video-stream inputs are supported.
- Sample mode is currently supported only for Profile 5.
