#!/usr/bin/env python3
import argparse
import ctypes
import json
import os
import platform
import random
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

APP_NAME = "DVFix"
APP_VERSION = "0.6.1"
USE_COLOR = False
TITLE_ART = (
    " ____   __     ______ _      ",
    "|  _ \\  \\ \\   / /  ___(_)_  __",
    "| | | |  \\ \\ / /| |_  | \\ \\/ /",
    "| |_| |   \\ V / |  _| | |>  < ",
    "|____/     \\_/  |_|   |_/_/\\_\\",
)


def eprint(msg):
    print(msg, file=sys.stderr)


def configure_output(no_color):
    global USE_COLOR
    USE_COLOR = False
    if no_color or os.environ.get("NO_COLOR"):
        return
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return
    USE_COLOR = True
    if os.name != "nt":
        return
    try:
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        USE_COLOR = False


def paint(text, color):
    if not USE_COLOR:
        return text
    colors = {
        "blue": "\033[34m",
        "cyan": "\033[36m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "red": "\033[31m",
        "dim": "\033[2m",
        "reset": "\033[0m",
    }
    return f"{colors[color]}{text}{colors['reset']}"


def line(text=""):
    print(text)


def rule(label):
    line(paint(f"==== {label} ====", "cyan"))


def print_title_art(tagline=None):
    line("")
    for art_line in TITLE_ART:
        line(paint(art_line, "cyan"))
    if tagline:
        line(paint(f"  {tagline}", "blue"))


def kv(key, value):
    line(f"  {key:<12} {value}")


def log(level, message, color):
    line(f"{paint(f'[{level}]', color)} {message}")


def info(message):
    log("INFO", message, "blue")


def step(message):
    log("STEP", message, "cyan")


def success(message):
    log("OK", message, "green")


def warn(message):
    log("WARN", message, "yellow")


def fail(message):
    log("FAIL", message, "red")


def command_line(cmd):
    if os.name == "nt":
        formatted = subprocess.list2cmdline(cmd)
    else:
        formatted = shlex.join(cmd)
    line(paint(f"  $ {formatted}", "dim"))


def format_seconds(seconds):
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {rem:.0f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m {rem:.0f}s"


def format_duration_value(duration_value):
    try:
        seconds = float(duration_value)
    except (TypeError, ValueError):
        return None
    return format_seconds(seconds)


def format_size_bytes(size_value):
    try:
        size = float(size_value)
    except (TypeError, ValueError):
        return None
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    return f"{size:.1f} {units[unit_index]}"


def find_tool(name):
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
    return path


def which_or_die(name):
    path = find_tool(name)
    if not path:
        eprint(f"Missing required tool: {name}. Make sure it is on PATH.")
        raise SystemExit(2)
    return path


def run(cmd, dry_run=False, label=None):
    if label:
        step(label)
    command_line(cmd)
    if dry_run:
        info("Dry-run enabled; command was not executed.")
        return 0
    started = time.time()
    proc = subprocess.run(cmd)
    elapsed = time.time() - started
    if proc.returncode == 0:
        success(f"{label or 'Command'} completed in {format_seconds(elapsed)}.")
    else:
        fail(
            f"{label or 'Command'} failed with exit code {proc.returncode} after {format_seconds(elapsed)}."
        )
    return proc.returncode


def ffmpeg_list_contains(ffmpeg, flag, name):
    try:
        out = subprocess.check_output([ffmpeg, "-hide_banner", flag], stderr=subprocess.STDOUT).decode(
            "utf-8", errors="ignore"
        )
    except subprocess.CalledProcessError:
        return False
    for line_text in out.splitlines():
        if name in line_text.split():
            return True
    return False


def ffmpeg_has_filter(ffmpeg, name):
    return ffmpeg_list_contains(ffmpeg, "-filters", name)


def ffmpeg_has_bsf(ffmpeg, name):
    return ffmpeg_list_contains(ffmpeg, "-bsfs", name)


def ffmpeg_has_encoder(ffmpeg, name):
    return ffmpeg_list_contains(ffmpeg, "-encoders", name)


def ffmpeg_libplacebo_usable(ffmpeg):
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=16x16:d=0.1",
        "-vf",
        "libplacebo",
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return True, None
    out = (proc.stderr or "") + (proc.stdout or "")
    if "vkGetInstanceProcAddr" in out:
        return (
            False,
            "libplacebo exists but FFmpeg is not linked against the Vulkan loader "
            "(vkGetInstanceProcAddr). Use a Vulkan-enabled FFmpeg build.",
        )
    if "Failed creating Vulkan device" in out or "Failed initializing vulkan device" in out:
        return (
            False,
            "Vulkan device initialization failed. Update GPU drivers or Vulkan runtime.",
        )
    return False, "libplacebo filter failed to initialize."


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


def ffprobe_json(ffprobe, input_path, quiet=False):
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
        if not quiet:
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


def is_no_dv_name(path):
    base = os.path.basename(path)
    root, _ext = os.path.splitext(base)
    return root.endswith(".noDV")


def resolve_output_path(input_path, output_arg):
    if output_arg:
        desired_name = ensure_no_dv_suffix(output_arg)
        output_path = os.path.join(
            os.path.dirname(os.path.abspath(input_path)), desired_name
        )
    else:
        output_path = default_output_path(input_path)
    output_dir = os.path.dirname(os.path.abspath(output_path))
    input_dir = os.path.dirname(os.path.abspath(input_path))
    if output_dir != input_dir:
        output_path = os.path.join(input_dir, os.path.basename(output_path))
        warn(f"Output directory forced to input directory: {output_path}")
    return output_path


def format_stream_info(video_stream):
    codec = video_stream.get("codec_name") or "unknown"
    width = video_stream.get("width")
    height = video_stream.get("height")
    pix_fmt = video_stream.get("pix_fmt") or "unknown"
    res = f"{width}x{height}" if width and height else "unknown"
    return f"{codec} {res} {pix_fmt}"


def print_detection(input_path, output_path, data, video_stream, dv_profile):
    fmt = data.get("format", {})
    fmt_name = fmt.get("format_name") or "unknown"
    duration = format_duration_value(fmt.get("duration"))
    size = format_size_bytes(fmt.get("size"))
    kv("Input", input_path)
    kv("Output", output_path)
    kv("Container", fmt_name)
    if duration:
        kv("Duration", duration)
    if size:
        kv("Size", size)
    kv("Video", format_stream_info(video_stream))
    tags = get_color_tags(video_stream)
    tag_line = ", ".join(f"{k}={v}" for k, v in tags.items() if v)
    if tag_line:
        kv("Color", tag_line)
    if dv_profile is None:
        kv("Dolby Vision", "not found")
    else:
        kv("Dolby Vision", f"profile {dv_profile}")


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


def collect_input_files(path):
    video_exts = {
        ".mkv",
        ".mp4",
        ".mov",
        ".m4v",
        ".ts",
        ".m2ts",
        ".avi",
        ".wmv",
        ".mxf",
        ".webm",
    }
    if os.path.isdir(path):
        files = []
        for root, _dirs, names in os.walk(path):
            for name in names:
                ext = os.path.splitext(name)[1].lower()
                if ext in video_exts:
                    files.append(os.path.join(root, name))
        files.sort()
        return files
    return [path]


def get_planned_action(dv_profile, args):
    if dv_profile is None:
        return "skip", "Skip: no Dolby Vision metadata found."
    if dv_profile == 7:
        if args.sample is not None or args.sample_rand is not None:
            return "skip", "Skip: sample mode is only supported for Profile 5."
        return "convert", "Convert Profile 7 by stripping EL/RPU and remuxing the HDR10 base layer."
    if dv_profile == 8:
        if args.sample is not None or args.sample_rand is not None:
            return "skip", "Skip: sample mode is only supported for Profile 5."
        return "convert", "Convert Profile 8 by stripping Dolby Vision RPU metadata in-place."
    if dv_profile == 5:
        if args.p5_force_tag:
            return "convert", "Convert Profile 5 by re-encoding and forcing HDR10 tags only."
        return "convert", "Convert Profile 5 by re-encoding to HDR10 with libplacebo."
    return "skip", f"Skip: unsupported Dolby Vision profile {dv_profile}."


def get_profile_requirements(dv_profile, args):
    if dv_profile == 7:
        return ["dovi_tool"]
    if dv_profile == 8:
        return ["ffmpeg bitstream filter dovi_rpu"]
    if dv_profile == 5:
        requirements = [f"encoder {args.encoder}"]
        if not args.p5_force_tag:
            requirements += ["ffmpeg filter libplacebo", "Vulkan loader"]
        return requirements
    return []


def print_info_plan(dv_profile, args, output_exists):
    _action_kind, action_text = get_planned_action(dv_profile, args)
    kv("Plan", action_text)
    requirements = get_profile_requirements(dv_profile, args)
    if requirements:
        kv("Needs", ", ".join(requirements))
    if output_exists:
        kv("Guard", "Output already exists and would be skipped without --overwrite.")


def print_header(mode_name, args, input_count=None):
    taglines = {
        "check": "environment audit",
        "info": "inspection mode",
        "convert": "conversion mode",
    }
    print_title_art(taglines.get(mode_name))
    rule(f"{APP_NAME} {APP_VERSION}")
    kv("Mode", mode_name)
    kv("Platform", f"{platform.system()} {platform.release()}")
    if args.input:
        kv("Input", args.input)
    if input_count is not None:
        kv("Files", input_count)
    kv("Encoder", args.encoder)
    kv("Preset", args.preset)
    if args.temp:
        kv("Temp", args.temp)
    if args.dry_run:
        kv("Dry-run", "enabled")
    if args.info:
        kv("Conversion", "disabled")


def print_batch_progress(results, total_count, info_mode):
    if info_mode:
        info(
            f"Batch progress: {sum(results.values())}/{total_count} complete | "
            f"inspected {results['inspected']} | skipped {results['skipped']} | failed {results['failed']}"
        )
    else:
        info(
            f"Batch progress: {sum(results.values())}/{total_count} complete | "
            f"converted {results['converted']} | skipped {results['skipped']} | failed {results['failed']}"
        )


def print_summary(results, info_mode, total_elapsed):
    rule("Summary")
    if info_mode:
        kv("Inspected", results["inspected"])
    else:
        kv("Converted", results["converted"])
    kv("Skipped", results["skipped"])
    kv("Failed", results["failed"])
    kv("Elapsed", format_seconds(total_elapsed))


def run_environment_check(ffmpeg, ffprobe, args):
    overall_ok = True
    rule("Environment Check")
    if ffmpeg:
        success(f"ffmpeg found: {ffmpeg}")
    else:
        fail("ffmpeg not found.")
        overall_ok = False
    if ffprobe:
        success(f"ffprobe found: {ffprobe}")
    else:
        fail("ffprobe not found.")
        overall_ok = False

    dovi_tool = find_tool("dovi_tool")
    if dovi_tool:
        success(f"dovi_tool found: {dovi_tool}")
    else:
        warn("dovi_tool not found. Profile 7 inputs will fail until it is installed.")

    if ffmpeg:
        if ffmpeg_has_encoder(ffmpeg, args.encoder):
            success(f"Encoder available: {args.encoder}")
        else:
            fail(f"Encoder not available: {args.encoder}")
            overall_ok = False

        if ffmpeg_has_bsf(ffmpeg, "dovi_rpu"):
            success("Bitstream filter dovi_rpu is available for Profile 8 stripping.")
        else:
            warn("Bitstream filter dovi_rpu is missing. Profile 8 stripping will fail.")

        if ffmpeg_has_filter(ffmpeg, "libplacebo"):
            success("Filter libplacebo is available for Profile 5 HDR conversion.")
            usable, reason = ffmpeg_libplacebo_usable(ffmpeg)
            if usable:
                success("libplacebo runtime check passed.")
            else:
                warn(f"libplacebo runtime check failed: {reason}")
        else:
            warn(
                "Filter libplacebo is missing. Profile 5 will need --p5-force-tag or a different FFmpeg build."
            )

    if has_vulkan_loader():
        success("Vulkan loader detected.")
    else:
        warn("Vulkan loader not found. Profile 5 libplacebo runs will fail.")

    line("")
    if overall_ok:
        success("Environment check passed for probing and the selected encoder.")
        return 0
    fail("Environment check failed. Fix the required items above and rerun.")
    return 2


def process_file(input_path, output_arg, args, ffmpeg, ffprobe):
    started = time.time()
    if not os.path.exists(input_path):
        warn(f"Skipping missing file: {input_path}")
        return "skipped"
    if is_no_dv_name(input_path):
        warn(f"Skipping already-processed file: {input_path}")
        return "skipped"

    output_path = resolve_output_path(input_path, output_arg)
    output_exists = os.path.exists(output_path) and not args.overwrite

    try:
        data = ffprobe_json(ffprobe, input_path, quiet=True)
    except SystemExit:
        warn(f"Skipping non-media file: {input_path}")
        return "skipped"

    try:
        video = pick_video_stream(data)
    except SystemExit as exc:
        warn(f"Skipping: {exc}")
        return "skipped"

    if video.get("codec_name") != "hevc":
        warn("Skipping: input video is not HEVC.")
        kv("File", input_path)
        return "skipped"

    dv_profile = get_dv_profile(video)
    print_detection(input_path, output_path, data, video, dv_profile)
    if not has_complete_color_tags(get_color_tags(video)):
        warn("Input video is missing some color tags; output tags will fall back to HDR10 defaults.")

    action_kind, action_text = get_planned_action(dv_profile, args)
    if args.info:
        print_info_plan(dv_profile, args, output_exists)
        return "inspected"

    if output_exists:
        warn(f"Skipping existing output: {output_path} (use --overwrite to replace)")
        return "skipped"

    if action_kind == "skip":
        warn(action_text)
        return "skipped"

    def finalize_success():
        if args.replace:
            try:
                os.remove(input_path)
                success(f"Removed original: {input_path}")
            except OSError as exc:
                warn(f"Converted output created, but failed to remove original ({exc})")
        success(f"Finished {os.path.basename(input_path)} in {format_seconds(time.time() - started)}.")
        return "converted"

    # Profile 7: BL + EL (+ RPU). We must remove EL + RPU to get HDR10 base.
    if dv_profile == 7:
        step("Profile 7 workflow selected.")
        try:
            dovi_tool = which_or_die("dovi_tool")
        except SystemExit:
            fail("Profile 7 conversion requires dovi_tool.")
            return "failed"
        temp_root = args.temp or tempfile.gettempdir()
        temp_dir = tempfile.mkdtemp(prefix="dvfix_", dir=temp_root)
        kv("Temp", temp_dir)
        try:
            in_hevc = os.path.join(temp_dir, "input.hevc")
            bl_hevc = os.path.join(temp_dir, "bl.hevc")

            cmd1 = [
                ffmpeg,
                "-y",
                "-i",
                input_path,
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
            if run(cmd1, args.dry_run, "Step 1/3: Extract HEVC base stream") != 0:
                return "failed"

            cmd2 = [dovi_tool, "remove", in_hevc, "-o", bl_hevc]
            if run(cmd2, args.dry_run, "Step 2/3: Remove Dolby Vision EL/RPU") != 0:
                return "failed"

            cmd3 = [
                ffmpeg,
                "-y",
                "-i",
                bl_hevc,
                "-i",
                input_path,
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
            if run(cmd3, args.dry_run, "Step 3/3: Remux HDR10 base layer") != 0:
                return "failed"
        finally:
            if args.keep_temp:
                info(f"Keeping temporary files: {temp_dir}")
            else:
                shutil.rmtree(temp_dir, ignore_errors=True)
        return finalize_success()

    # Profile 8 (HDR10 base + DV metadata): strip DV metadata without re-encode.
    if dv_profile == 8:
        step("Profile 8 workflow selected.")
        if not ffmpeg_has_bsf(ffmpeg, "dovi_rpu"):
            fail("Profile 8 conversion requires the dovi_rpu bitstream filter in FFmpeg.")
            return "failed"
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            input_path,
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
        if run(cmd, args.dry_run, "Step 1/1: Strip Dolby Vision RPU metadata") != 0:
            return "failed"
        return finalize_success()

    # Profile 5 (single-layer DV): requires re-encode.
    if dv_profile == 5:
        step("Profile 5 workflow selected.")
        if not ffmpeg_has_encoder(ffmpeg, args.encoder):
            fail(f"Selected encoder is not available in FFmpeg: {args.encoder}")
            return "failed"
        if not confirm_reencode(output_path, args.yes):
            warn("Cancelled by user.")
            return "skipped"

        color_tags = get_color_tags(video)
        color_args = build_hdr10_color_args(color_tags)
        vf = None
        if args.p5_force_tag:
            warn(
                "Profile 5: forcing tag-only output (DV processing skipped; colors may be wrong)."
            )
        else:
            has_libplacebo = ffmpeg_has_filter(ffmpeg, "libplacebo")
            if not has_libplacebo:
                fail(
                    "Profile 5 requires ffmpeg with libplacebo to apply Dolby Vision metadata. "
                    "Install a libplacebo-enabled ffmpeg build or rerun with --p5-force-tag to "
                    "continue with likely-wrong colors."
                )
                return "failed"
            ok, reason = ffmpeg_libplacebo_usable(ffmpeg)
            if not ok:
                fail(
                    f"Profile 5: {reason} "
                    "Install a Vulkan-enabled FFmpeg build or use --p5-force-tag."
                )
                return "failed"
            if not has_vulkan_loader():
                fail(
                    "Profile 5 requires Vulkan (vulkan-1.dll) for libplacebo. "
                    "Install/repair your NVIDIA drivers or Vulkan runtime, or place "
                    "vulkan-1.dll next to ffmpeg.exe, then retry. "
                    "Use --p5-force-tag to continue with likely-wrong colors."
                )
                return "failed"
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
            info("Sample mode enabled; output will include only a subset of the video.")
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
                    input_path,
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
                run_label = "Step 1/1: Re-encode first sample segment to HDR10"
            else:
                duration = parse_duration_seconds(data)
                try:
                    starts = build_sample_segments(
                        duration, sample_rand, args.sample_seg_len, args.sample_seed
                    )
                except SystemExit as exc:
                    fail(str(exc))
                    return "failed"
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
                    input_path,
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
                run_label = "Step 1/1: Re-encode random sample montage to HDR10"
        else:
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                input_path,
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
            run_label = "Step 1/1: Re-encode video stream to HDR10"

        if run(cmd, args.dry_run, run_label) != 0:
            return "failed"
        return finalize_success()

    warn(f"Skip: unsupported Dolby Vision profile {dv_profile}.")
    return "skipped"


def confirm_reencode(output_path, assume_yes):
    if assume_yes:
        return True
    line("")
    warn("Profile 5 requires re-encoding the video stream to HDR10.")
    kv("Output", output_path)
    kv("Video", "Will be recompressed; audio, subtitles, chapters, and metadata remain untouched.")
    resp = read_prompt("Proceed with re-encoding? [y/N]: ").strip().lower()
    return resp in ("y", "yes")


def confirm_replace_all(assume_yes):
    if assume_yes:
        return True
    line("")
    warn("--replace will delete original files after successful conversion.")
    resp = read_prompt("Proceed with --replace? [y/N]: ").strip().lower()
    return resp in ("y", "yes")


def read_prompt(prompt):
    try:
        return input(prompt)
    except EOFError as exc:
        raise SystemExit("Wizard cancelled because no input was available on stdin.") from exc


def prompt_choice(prompt, options, default_index=1):
    line("")
    line(paint(prompt, "blue"))
    for index, (_value, label) in enumerate(options, start=1):
        default_tag = " [default]" if index == default_index else ""
        bullet = ">" if index == default_index else "-"
        line(f"  {bullet} [{index}] {label}{default_tag}")
    while True:
        response = read_prompt(f"Choose an option [{default_index}]: ").strip()
        if not response:
            return options[default_index - 1][0]
        if response.isdigit():
            index = int(response)
            if 1 <= index <= len(options):
                return options[index - 1][0]
        warn("Enter one of the listed option numbers.")


def prompt_yes_no(prompt, default=False):
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        response = read_prompt(f"{prompt} {suffix}: ").strip().lower()
        if not response:
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        warn("Enter y or n.")


def prompt_text(prompt, allow_blank=False):
    while True:
        response = read_prompt(f"{prompt}: ").strip()
        if response or allow_blank:
            return response
        warn("A value is required.")


def prompt_existing_path(prompt):
    while True:
        response = prompt_text(prompt)
        cleaned = response.strip().strip('"').strip("'")
        expanded = os.path.expanduser(cleaned)
        if os.path.exists(expanded):
            return expanded
        warn("That path does not exist. Try again.")


def run_wizard(args):
    print_title_art("guided mode")
    rule("Wizard")
    info("No input was provided, so DVFix is switching to guided mode.")
    kv("Goal", "Guide you into convert, inspect, or check without memorizing flags.")
    kv("Hint", "Press Enter to accept the default option shown in brackets.")

    rule("Mission")
    mode = prompt_choice(
        "What would you like to do?",
        [
            ("convert", "Convert a file or directory"),
            ("info", "Inspect input only (--info)"),
            ("check", "Run environment checks (--check)"),
            ("quit", "Exit"),
        ],
        default_index=1,
    )

    if mode == "quit":
        raise SystemExit(0)

    if mode == "check":
        args.check = True
        return args

    args.info = mode == "info"

    rule("Source")
    args.input = prompt_existing_path("Enter the input file or directory path")

    if os.path.isfile(args.input):
        output_name = prompt_text(
            "Optional output file name (leave blank for automatic .noDV naming)",
            allow_blank=True,
        )
        args.output = output_name or None
    else:
        args.output = None
        info("Directory input selected. Output names will be generated next to each file.")

    if not args.info:
        rule("Behavior")
        args.overwrite = prompt_yes_no("Overwrite existing outputs if they already exist?", default=False)
        args.replace = prompt_yes_no("Delete originals after successful conversion?", default=False)
        args.dry_run = prompt_yes_no("Show commands without executing them?", default=False)

    line("")
    rule("Launch Pad")
    kv("Mode", "info" if args.info else "convert")
    kv("Input", args.input)
    if args.output:
        kv("Output", ensure_no_dv_suffix(args.output))
    else:
        kv("Output", "automatic .noDV naming")
    if not args.info:
        kv("Overwrite", "yes" if args.overwrite else "no")
        kv("Replace", "yes" if args.replace else "no")
        kv("Dry-run", "yes" if args.dry_run else "no")

    if not prompt_yes_no("Start with these settings now?", default=True):
        raise SystemExit("Cancelled by user.")

    return args


def main():
    parser = argparse.ArgumentParser(
        description="Convert Dolby Vision to HDR10 while preserving all non-video streams."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Validate tools and common codec capabilities, then exit.",
    )
    mode_group.add_argument(
        "--info",
        action="store_true",
        help="Inspect input and print the planned action without converting anything.",
    )
    parser.add_argument("input", nargs="?", help="Input file or directory (MKV/MP4/…)")
    parser.add_argument("output", nargs="?", help="Output file (file input only)")
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
        "--replace",
        action="store_true",
        help="Delete original file after successful conversion",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them",
    )
    parser.add_argument(
        "--no-color",
        "--plain",
        dest="no_color",
        action="store_true",
        help="Disable ANSI styling in terminal output",
    )
    args = parser.parse_args()
    configure_output(args.no_color)

    if args.check:
        if args.input or args.output:
            parser.error("--check does not take input or output paths.")
    elif not args.input:
        args = run_wizard(args)

    if args.sample is not None and args.sample_rand is not None:
        parser.error("Use only one of --sample or --sample-rand.")
    if args.sample is not None and args.sample <= 0:
        parser.error("--sample must be greater than zero.")
    if args.sample_rand is not None and args.sample_rand <= 0:
        parser.error("--sample-rand must be greater than zero.")
    if args.sample_seg_len <= 0:
        parser.error("--sample-seg-len must be greater than zero.")
    if args.temp:
        if not os.path.isdir(args.temp):
            parser.error("--temp must point to an existing directory.")
        if not os.access(args.temp, os.W_OK):
            parser.error("--temp is not writable.")

    ffmpeg = which_or_die("ffmpeg") if not args.check else find_tool("ffmpeg")
    ffprobe = which_or_die("ffprobe") if not args.check else find_tool("ffprobe")

    if args.check:
        print_header("check", args)
        raise SystemExit(run_environment_check(ffmpeg, ffprobe, args))

    if args.sample is not None or args.sample_rand is not None:
        if args.replace:
            warn("--replace is ignored in sample mode.")
            args.replace = False

    if args.replace and not args.info and not confirm_replace_all(args.yes):
        raise SystemExit("Cancelled by user.")

    inputs = collect_input_files(args.input)
    if not inputs:
        raise SystemExit(f"No candidate video files found in: {args.input}")

    if os.path.isdir(args.input) and args.output:
        warn("Output argument is ignored when input is a directory.")

    total_started = time.time()
    results = {"converted": 0, "inspected": 0, "skipped": 0, "failed": 0}
    print_header("info" if args.info else "convert", args, input_count=len(inputs))
    for index, path in enumerate(inputs, start=1):
        line("")
        rule(f"File {index}/{len(inputs)}: {os.path.basename(path)}")
        status = process_file(
            path,
            args.output if not os.path.isdir(args.input) else None,
            args,
            ffmpeg,
            ffprobe,
        )
        results[status] += 1
        if len(inputs) > 1:
            print_batch_progress(results, len(inputs), args.info)

    line("")
    print_summary(results, args.info, time.time() - total_started)

    if results["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
