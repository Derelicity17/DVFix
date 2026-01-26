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
- `--p5-convert` For Profile 5, apply zscale colorspace conversion (default: tag-only).
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
