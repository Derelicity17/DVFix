#!/usr/bin/env python3
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import ctypes


def eprint(msg):
    print(msg, file=sys.stderr)


def which_or_die(name):
    candidates = [name]
    if os.name == "nt" and not name.lower().endswith(".exe"):
        candidates.append(f"{name}.exe")

    search_dirs = []
    # Prefer working directory, then script directory, then PATH.
    search_dirs.append(os.getcwd())
    search_dirs.append(os.path.dirname(os.path.abspath(__file__)))

    for d in search_dirs:
        for c in candidates:
            p = os.path.join(d, c)
            if os.path.isfile(p):
                return p

    path = shutil.which(name)
    if not path and os.name == "nt" and name.lower().endswith(".exe"):
        path = shutil.which(name[:-4])
    if not path:
        eprint(f"Missing required tool: {name}. Make sure it is on PATH.")
        raise SystemExit(2)
    return path


def run(cmd, dry_run=False):
    if dry_run:
        print("DRY-RUN:", " ".join(cmd))
        return 0
    print(">", " ".join(cmd))
    proc = subprocess.run(cmd)
    return proc.returncode


def ffmpeg_has_filter(ffmpeg, name):
    try:
        out = subprocess.check_output(
            [ffmpeg, "-hide_banner", "-filters"], stderr=subprocess.STDOUT
        ).decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError:
        return False
    token = f" {name} "
    return token in out


def has_vulkan_loader():
    if os.name == "nt":
        dll_name = "vulkan-1.dll"
        try:
            ctypes.WinDLL(dll_name)
            return True
        except OSError:
            return False
    # Best-effort for non-Windows
    for lib in ("libvulkan.so.1", "libvulkan.so"):
        try:
            ctypes.CDLL(lib)
            return True
        except OSError:
            continue
    return False


def ffprobe_json(ffprobe, input_path):
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        input_path,
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        eprint("ffprobe failed:")
        eprint(exc.output.decode(errors="ignore"))
        raise SystemExit(exc.returncode)
    return json.loads(out.decode("utf-8", errors="ignore"))


def pick_video_stream(data):
    videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not videos:
        raise SystemExit("No video stream found.")
    if len(videos) > 1:
        raise SystemExit(
            "Multiple video streams found. This tool currently supports only one."
        )
    return videos[0]


def has_audio_stream(data):
    return any(s.get("codec_type") == "audio" for s in data.get("streams", []))


def get_dv_profile(video_stream):
    for sd in video_stream.get("side_data_list", []) or []:
        if sd.get("side_data_type") == "DOVI configuration record":
            try:
                return int(sd.get("dv_profile"))
            except (TypeError, ValueError):
                return None
    return None


def get_color_tags(video_stream):
    return {
        "color_primaries": video_stream.get("color_primaries"),
        "color_trc": video_stream.get("color_transfer"),
        "colorspace": video_stream.get("color_space"),
        "color_range": video_stream.get("color_range"),
    }


def build_color_args(tags):
    args = []
    if tags.get("color_primaries"):
        args += ["-color_primaries", tags["color_primaries"]]
    if tags.get("color_trc"):
        args += ["-color_trc", tags["color_trc"]]
    if tags.get("colorspace"):
        args += ["-colorspace", tags["colorspace"]]
    if tags.get("color_range"):
        args += ["-color_range", tags["color_range"]]
    return args


def build_hdr10_color_args(tags):
    args = [
        "-color_primaries",
        "bt2020",
        "-color_trc",
        "smpte2084",
        "-colorspace",
        "bt2020nc",
    ]
    if tags.get("color_range"):
        args += ["-color_range", tags["color_range"]]
    return args


def has_complete_color_tags(tags):
    return bool(
        tags.get("color_primaries")
        and tags.get("color_trc")
        and tags.get("colorspace")
    )


def default_output_path(input_path):
    in_dir = os.path.dirname(os.path.abspath(input_path))
    base = os.path.basename(input_path)
    root, ext = os.path.splitext(base)
    if ext:
        out_name = f"{root}.noDV{ext}"
    else:
        out_name = f"{base}.noDV"
    return os.path.join(in_dir, out_name)


def ensure_no_dv_suffix(path):
    base = os.path.basename(path)
    root, ext = os.path.splitext(base)
    if root.endswith(".noDV"):
        return base
    if ext:
        return f"{root}.noDV{ext}"
    return f"{base}.noDV"


def format_stream_info(video_stream):
    codec = video_stream.get("codec_name") or "unknown"
    width = video_stream.get("width")
    height = video_stream.get("height")
    pix_fmt = video_stream.get("pix_fmt") or "unknown"
    res = f"{width}x{height}" if width and height else "unknown"
    return f"{codec} {res} {pix_fmt}"


def print_detection(input_path, data, video_stream, dv_profile):
    fmt = data.get("format", {})
    fmt_name = fmt.get("format_name") or "unknown"
    duration = fmt.get("duration")
    size = fmt.get("size")
    print("Detection:")
    print(f"  Input: {input_path}")
    print(f"  Container: {fmt_name}")
    if duration:
        print(f"  Duration: {duration} sec")
    if size:
        print(f"  Size: {size} bytes")
    vinfo = format_stream_info(video_stream)
    print(f"  Video: {vinfo}")
    tags = get_color_tags(video_stream)
    tag_line = ", ".join(
        f"{k}={v}" for k, v in tags.items() if v
    )
    if tag_line:
        print(f"  Color: {tag_line}")
    if dv_profile is None:
        print("  Dolby Vision: not found")
    else:
        print(f"  Dolby Vision: profile {dv_profile}")


def parse_duration_seconds(data):
    fmt = data.get("format", {})
    try:
        return float(fmt.get("duration"))
    except (TypeError, ValueError):
        return None


def build_sample_segments(total_duration, count, seg_len, seed=None):
    if total_duration is None:
        raise SystemExit("Cannot determine duration; sample-rand requires duration.")
    if total_duration <= seg_len:
        raise SystemExit("Duration too short for requested sample segment length.")
    rng = random.Random(seed)
    starts = []
    max_start = max(0.0, total_duration - seg_len)
    for _ in range(count):
        starts.append(rng.uniform(0.0, max_start))
    return starts


def confirm_reencode(output_path, assume_yes):
    if assume_yes:
        return True
    print("")
    print("Profile 5 detected. This requires re-encoding the video to HDR10.")
    print("Re-encoding means the video stream will be recompressed, which can change")
    print("quality and will take time. Audio, subtitles, chapters, and metadata stay")
    print("bit-for-bit the same.")
    print("")
    resp = input(f"Proceed with re-encoding to {output_path}? [y/N]: ").strip().lower()
    return resp in ("y", "yes")


def main():
    parser = argparse.ArgumentParser(
        description="Convert Dolby Vision to HDR10 while preserving all non-video streams."
    )
    parser.add_argument("input", help="Input video file (MKV/MP4/…)")
    parser.add_argument("output", nargs="?", help="Output file (default: input.noDV.ext)")
    parser.add_argument(
        "--encoder",
        default="hevc_nvenc",
        help="Video encoder to use if re-encoding is required (default: hevc_nvenc)",
    )
    parser.add_argument(
        "--preset",
        default="p7",
        help="Encoder preset to use when re-encoding (default: p7)",
    )
    parser.add_argument(
        "--cq",
        default="19",
        help="Constant quality for NVENC VBR (default: 19)",
    )
    parser.add_argument(
        "--p5-force-tag",
        action="store_true",
        help="For Profile 5, skip DV processing and only tag HDR10 (colors likely wrong)",
    )
    parser.add_argument(
        "--sample",
        type=float,
        default=None,
        help="Encode only the first N seconds (quick test output)",
    )
    parser.add_argument(
        "--sample-rand",
        type=int,
        default=None,
        help="Create a test clip from N random segments (requires re-encode)",
    )
    parser.add_argument(
        "--sample-seg-len",
        type=float,
        default=2.0,
        help="Length in seconds for each random segment (default: 2)",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        help="Seed for random segment selection (repeatable samples)",
    )
    parser.add_argument(
        "--temp",
        default=None,
        help="Temporary directory (defaults to OS temp)",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary files (debug)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Assume yes for prompts (Profile 5 re-encode)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output if it already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them",
    )
    args = parser.parse_args()

    ffmpeg = which_or_die("ffmpeg")
    ffprobe = which_or_die("ffprobe")

    if not os.path.exists(args.input):
        raise SystemExit(f"Input file not found: {args.input}")

    if args.output:
        desired_name = ensure_no_dv_suffix(args.output)
        output_path = os.path.join(
            os.path.dirname(os.path.abspath(args.input)), desired_name
        )
    else:
        output_path = default_output_path(args.input)
    output_dir = os.path.dirname(os.path.abspath(output_path))
    input_dir = os.path.dirname(os.path.abspath(args.input))
    if output_dir != input_dir:
        output_path = os.path.join(input_dir, os.path.basename(output_path))
        print(f"Output directory forced to input directory: {output_path}")
    if os.path.exists(output_path) and not args.overwrite:
        raise SystemExit(
            f"Output already exists: {output_path} (use --overwrite to replace)"
        )

    data = ffprobe_json(ffprobe, args.input)
    video = pick_video_stream(data)

    if video.get("codec_name") != "hevc":
        raise SystemExit("Input video is not HEVC. Dolby Vision HEVC is required.")

    dv_profile = get_dv_profile(video)
    print_detection(args.input, data, video, dv_profile)
    if dv_profile is None:
        raise SystemExit("No Dolby Vision metadata found (DOVI configuration record).")

    if args.sample is not None and args.sample_rand is not None:
        raise SystemExit("Use only one of --sample or --sample-rand.")

    # Profile 7: BL + EL (+ RPU). We must remove EL + RPU to get HDR10 base.
    if dv_profile == 7:
        dovi_tool = which_or_die("dovi_tool")
        temp_root = args.temp or tempfile.gettempdir()
        temp_dir = tempfile.mkdtemp(prefix="dvfix_", dir=temp_root)
        try:
            in_hevc = os.path.join(temp_dir, "input.hevc")
            bl_hevc = os.path.join(temp_dir, "bl.hevc")

            cmd1 = [
                ffmpeg,
                "-y",
                "-i",
                args.input,
                "-map",
                "0:v:0",
                "-c:v",
                "copy",
                "-bsf:v",
                "hevc_mp4toannexb",
                "-f",
                "hevc",
                in_hevc,
            ]
            if run(cmd1, args.dry_run) != 0:
                raise SystemExit(1)

            cmd2 = [dovi_tool, "remove", in_hevc, "-o", bl_hevc]
            if run(cmd2, args.dry_run) != 0:
                raise SystemExit(1)

            cmd3 = [
                ffmpeg,
                "-y",
                "-i",
                bl_hevc,
                "-i",
                args.input,
                "-map",
                "1",
                "-map",
                "-1:v",
                "-map",
                "0:v:0",
                "-c",
                "copy",
                "-map_metadata",
                "1",
                "-map_chapters",
                "1",
                output_path,
            ]
            if run(cmd3, args.dry_run) != 0:
                raise SystemExit(1)
        finally:
            if not args.keep_temp:
                shutil.rmtree(temp_dir, ignore_errors=True)
        return

    # Profile 8 (HDR10 base + DV metadata): strip DV metadata without re-encode.
    if dv_profile == 8:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            args.input,
            "-map",
            "0",
            "-c",
            "copy",
            "-bsf:v",
            "dovi_rpu=strip",
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            output_path,
        ]
        if run(cmd, args.dry_run) != 0:
            raise SystemExit(1)
        return

    # Profile 5 (single-layer DV): requires re-encode.
    if dv_profile == 5:
        if not confirm_reencode(output_path, args.yes):
            raise SystemExit("Cancelled by user.")

        color_tags = get_color_tags(video)
        color_args = build_hdr10_color_args(color_tags)
        vf = None
        has_libplacebo = ffmpeg_has_filter(ffmpeg, "libplacebo")
        if not has_libplacebo:
            if args.p5_force_tag:
                print(
                    "Profile 5: libplacebo filter not available; "
                    "proceeding with tag-only output (colors likely wrong)."
                )
            else:
                raise SystemExit(
                    "Profile 5 requires ffmpeg with libplacebo to apply Dolby Vision metadata. "
                    "Install a libplacebo-enabled ffmpeg build or rerun with --p5-force-tag to "
                    "continue with likely-wrong colors."
                )
        else:
            if not has_vulkan_loader():
                if args.p5_force_tag:
                    print(
                        "Profile 5: Vulkan loader not found; "
                        "proceeding with tag-only output (colors likely wrong)."
                    )
                else:
                    raise SystemExit(
                        "Profile 5 requires Vulkan (vulkan-1.dll) for libplacebo. "
                        "Install/repair your NVIDIA drivers or Vulkan runtime, or place "
                        "vulkan-1.dll next to ffmpeg.exe, then retry. "
                        "Use --p5-force-tag to continue with likely-wrong colors."
                    )
            range_tag = color_tags.get("color_range")
            if range_tag == "pc":
                range_out = "full"
            else:
                range_out = "limited"
            vf = (
                "libplacebo=apply_dolbyvision=1"
                f":colorspace=bt2020nc:color_primaries=bt2020"
                f":color_trc=smpte2084:range={range_out}"
            )

        sample_duration = args.sample
        sample_rand = args.sample_rand

        if sample_duration is not None or sample_rand is not None:
            print("Sample mode enabled: output will include only a subset of the video.")
            has_audio = has_audio_stream(data)
            if sample_duration is not None:
                cmd = [
                    ffmpeg,
                    "-y",
                    "-ss",
                    "0",
                    "-t",
                    str(sample_duration),
                    "-i",
                    args.input,
                    "-map",
                    "0:v:0",
                ]
                if has_audio:
                    cmd += ["-map", "0:a?"]
                else:
                    cmd += ["-an"]
                cmd += [
                    "-c:v",
                    args.encoder,
                    "-profile:v",
                    "main10",
                    "-pix_fmt",
                    "p010le",
                    "-preset",
                    args.preset,
                    "-rc",
                    "vbr",
                    "-cq",
                    str(args.cq),
                    "-b:v",
                    "0",
                    "-c:a",
                    "copy",
                    "-map_metadata",
                    "0",
                    "-map_chapters",
                    "0",
                ]
                if vf:
                    cmd += ["-vf", vf]
                cmd += color_args + [output_path]
            else:
                duration = parse_duration_seconds(data)
                starts = build_sample_segments(
                    duration, sample_rand, args.sample_seg_len, args.sample_seed
                )
                has_audio = has_audio_stream(data)
                filters = []
                v_labels = []
                a_labels = []
                for i, start in enumerate(starts):
                    v_label = f"v{i}"
                    a_label = f"a{i}"
                    v_chain = (
                        f"[0:v]trim=start={start}:duration={args.sample_seg_len},"
                        "setpts=PTS-STARTPTS"
                    )
                    if vf:
                        v_chain += f",{vf}"
                    v_chain += f"[{v_label}]"
                    filters.append(v_chain)
                    v_labels.append(f"[{v_label}]")
                    if has_audio:
                        a_chain = (
                            f"[0:a]atrim=start={start}:duration={args.sample_seg_len},"
                            "asetpts=PTS-STARTPTS"
                            f"[{a_label}]"
                        )
                        filters.append(a_chain)
                        a_labels.append(f"[{a_label}]")
                concat = (
                    "".join(v_labels)
                    + "".join(a_labels)
                    + f"concat=n={len(starts)}:v=1:a={1 if has_audio else 0}[v][a]"
                )
                filters.append(concat)
                cmd = [
                    ffmpeg,
                    "-y",
                    "-i",
                    args.input,
                    "-filter_complex",
                    ";".join(filters),
                    "-map",
                    "[v]",
                ]
                if has_audio:
                    cmd += ["-map", "[a]", "-c:a", "aac"]
                else:
                    cmd += ["-an"]
                cmd += [
                    "-c:v",
                    args.encoder,
                    "-profile:v",
                    "main10",
                    "-pix_fmt",
                    "p010le",
                    "-preset",
                    args.preset,
                    "-rc",
                    "vbr",
                    "-cq",
                    str(args.cq),
                    "-b:v",
                    "0",
                ] + color_args + [output_path]
        else:
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                args.input,
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-map",
                "0:s?",
                "-map",
                "0:t?",
                "-map",
                "0:d?",
                "-c:v",
                args.encoder,
                "-profile:v",
                "main10",
                "-pix_fmt",
                "p010le",
                "-preset",
                args.preset,
                "-rc",
                "vbr",
                "-cq",
                str(args.cq),
                "-b:v",
                "0",
                "-c:a",
                "copy",
                "-c:s",
                "copy",
                "-c:t",
                "copy",
                "-c:d",
                "copy",
                "-map_metadata",
                "0",
                "-map_chapters",
                "0",
            ]
            if vf:
                cmd += ["-vf", vf]
            cmd += color_args + [
                output_path,
            ]

        if run(cmd, args.dry_run) != 0:
            raise SystemExit(1)
        return

    if args.sample is not None or args.sample_rand is not None:
        raise SystemExit("Sample mode is currently supported only for Profile 5.")

    raise SystemExit(f"Unsupported Dolby Vision profile: {dv_profile}")


if __name__ == "__main__":
    main()
