# DVFix

CLI utility to convert Dolby Vision to HDR10 while preserving everything else in the file.

## Requirements

- `ffmpeg` and `ffprobe` available on PATH or placed in the working directory.
- `dovi_tool` available on PATH or placed in the working directory for Dolby Vision Profile 7 sources.
- Windows PowerShell can run: `python` and this script.

## Usage

```powershell
.\dvfix.ps1 input.mkv
```

By default, output is written next to the input with `.noDV` added:
`movie.mkv` -> `movie.noDV.mkv`

If you provide an output name, `.noDV` will be appended if missing and it will still be written to the input directory.

## What it does

- **Profile 7**: Extracts the HEVC bitstream, removes EL + RPU via `dovi_tool`, remuxes the HDR10 base layer, and copies all other streams unchanged.
- **Profile 8**: Strips Dolby Vision RPU metadata in-place (no re-encode), and copies everything else unchanged.
- **Profile 5**: Re-encodes video to HDR10 (no other streams are touched). Uses NVENC by default and asks for confirmation before starting.

## Options

- `--encoder` Video encoder for re-encode (default: `hevc_nvenc`).
- `--preset` Encoder preset for re-encode (default: `p7`).
- `--cq` NVENC constant-quality value (default: `19`).
- `--p5-force-tag` For Profile 5, skip DV processing and only tag HDR10 (colors likely wrong).
- `--sample N` Encode only the first N seconds (quick test output).
- `--sample-rand N` Create a test clip from N random segments (requires re-encode).
- `--sample-seg-len N` Segment length for `--sample-rand` (default: 2 seconds).
- `--sample-seed N` Seed for random sampling (repeatable output).
- `--temp` Custom temp directory.
- `--keep-temp` Keep temp files for debugging.
- `--yes` Skip the Profile 5 confirmation prompt.
- `--overwrite` Overwrite output if it already exists.
- `--dry-run` Print commands without executing them.

## Notes

- The tool preserves audio, subtitles, attachments, chapters, and container metadata.
- Only single-video-stream inputs are supported.
- For Profile 8, the FFmpeg build must include the `dovi_rpu` bitstream filter.
- For Profile 5, the video must be re-encoded; this is unavoidable because there is no HDR10 base layer.
- For Profile 5, an FFmpeg build with `libplacebo` is required to apply Dolby Vision metadata.
- For Profile 5 on Windows, Vulkan runtime (`vulkan-1.dll`) must be available (usually installed with NVIDIA drivers).
- If you see `vkGetInstanceProcAddr` errors, your FFmpeg build isn't linked against the Vulkan loader; use a Vulkan-enabled FFmpeg build.
- Sample mode is currently supported only for Profile 5.
