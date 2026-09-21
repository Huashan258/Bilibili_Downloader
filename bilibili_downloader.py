from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


BV_RE = re.compile(r"(?<![0-9A-Za-z])(BV[0-9A-Za-z]{10})(?![0-9A-Za-z])", re.IGNORECASE)
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "downloads"
FFMPEG_NAMES = ("ffmpeg.exe", "ffmpeg")
MEDIA_TYPE_LABELS = {
    "mp4": "MP4",
    "mp3": "MP3",
    "both": "MP4 + MP3",
}


def normalize_bilibili_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("链接不能为空。")

    if re.fullmatch(r"BV[0-9A-Za-z]{10}", value, flags=re.IGNORECASE):
        return f"https://www.bilibili.com/video/{value}"

    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    is_bilibili = host == "b23.tv" or host == "bilibili.com" or host.endswith(".bilibili.com")
    if not is_bilibili:
        raise ValueError("请输入哔哩哔哩视频链接、b23.tv 短链接或 BV 号。")

    query = parse_qs(parsed.query)
    bvid = next(iter(query.get("bvid", [])), "")
    if "/festival/" in parsed.path and re.fullmatch(
        r"BV[0-9A-Za-z]{10}", bvid, flags=re.IGNORECASE
    ):
        return value

    if re.fullmatch(r"BV[0-9A-Za-z]{10}", bvid, flags=re.IGNORECASE):
        return f"https://www.bilibili.com/video/{bvid}"

    if "/festival/" in parsed.path:
        match = BV_RE.search(value)
        if match:
            return f"https://www.bilibili.com/video/{match.group(1)}"

    return value


def locate_ffmpeg(user_location: str | None) -> str | None:
    if user_location:
        location = Path(user_location).expanduser().resolve()
        if location.is_file():
            return str(location)
        if location.is_dir() and any((location / name).is_file() for name in FFMPEG_NAMES):
            return str(location)
        raise ValueError(f"指定位置未找到 FFmpeg：{location}")

    for name in FFMPEG_NAMES:
        candidate = SCRIPT_DIR / name
        if candidate.is_file():
            return str(SCRIPT_DIR)

    try:
        import imageio_ffmpeg

        bundled_ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        if bundled_ffmpeg.is_file():
            return str(bundled_ffmpeg)
    except (ImportError, OSError, RuntimeError):
        pass

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return str(Path(system_ffmpeg).resolve())
    return None


def build_format_selector(media_type: str, max_height: int | None) -> str:
    if media_type == "mp3":
        return "bestaudio/best"

    height_filter = f"[height<={max_height}]" if max_height else ""
    return (
        f"bestvideo[ext=mp4]{height_filter}+bestaudio[ext=m4a]/"
        f"best[ext=mp4]{height_filter}/"
        f"bestvideo{height_filter}+bestaudio/best{height_filter}"
    )


def build_ydl_options(args: argparse.Namespace, output_dir: Path, ffmpeg_location: str) -> dict[str, Any]:
    options: dict[str, Any] = {
        "format": build_format_selector(args.media_type, args.max_height),
        "paths": {"home": str(output_dir)},
        "outtmpl": {"default": "%(title).150B [%(id)s].%(ext)s"},
        "trim_file_name": 180,
        "windowsfilenames": sys.platform.startswith("win"),
        "noplaylist": not args.all_parts,
        "overwrites": args.overwrite,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 3,
        "concurrent_fragment_downloads": args.fragments,
        "socket_timeout": 30,
        "ffmpeg_location": ffmpeg_location,
        "merge_output_format": "mp4",
    }

    if args.media_type in ("mp3", "both"):
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(args.audio_quality),
            },
            {"key": "FFmpegMetadata"},
        ]
        if args.media_type == "mp3":
            options["final_ext"] = "mp3"
        else:
            options["keepvideo"] = True

    if args.cookies:
        options["cookiefile"] = str(Path(args.cookies).expanduser().resolve())
    elif args.browser:
        options["cookiesfrombrowser"] = (args.browser, args.browser_profile)

    return options


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载哔哩哔哩视频，保存为 MP4、提取为 MP3，或同时保留两种格式。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="视频 URL、带 bvid 的活动页 URL、b23.tv 短链接或 BV 号",
    )
    parser.add_argument(
        "-t",
        "--type",
        dest="media_type",
        choices=("mp4", "mp3", "both"),
        help="输出格式；both 表示同时保存 MP4 和 MP3，命令行未指定时默认 MP4",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT_DIR),
        help="保存目录",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        help="MP4 最大分辨率高度，例如 1080；不填则选择账号可用的最佳画质",
    )
    parser.add_argument(
        "--audio-quality",
        type=int,
        choices=(64, 96, 128, 160, 192, 256, 320),
        default=192,
        help="MP3 码率（kbps）",
    )
    parser.add_argument(
        "--ffmpeg-location",
        help="ffmpeg 可执行文件或其所在目录；通常无需填写",
    )
    parser.add_argument(
        "--all-parts",
        action="store_true",
        help="下载多 P 视频的全部分 P；默认只下载当前/首个分 P",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已存在的文件",
    )
    parser.add_argument(
        "--fragments",
        type=int,
        choices=range(1, 17),
        default=4,
        metavar="1-16",
        help="分片并发数",
    )

    cookie_group = parser.add_mutually_exclusive_group()
    cookie_group.add_argument(
        "--browser",
        choices=("chrome", "chromium", "edge", "firefox", "brave", "opera", "vivaldi", "safari"),
        help="读取已登录浏览器的 Cookie，以使用账号可看的清晰度；请先关闭该浏览器",
    )
    cookie_group.add_argument(
        "--cookies",
        help="Netscape 格式 cookies.txt 的路径",
    )
    parser.add_argument(
        "--browser-profile",
        help="浏览器配置目录名称或路径，例如 Default；需与 --browser 一起使用",
    )

    args = parser.parse_args()
    if args.browser_profile and not args.browser:
        parser.error("--browser-profile 必须和 --browser 一起使用。")
    if args.max_height is not None and args.max_height < 144:
        parser.error("--max-height 不能小于 144。")
    return args


def interactive_values(args: argparse.Namespace) -> tuple[str, str]:
    if args.url:
        return args.url, args.media_type or "mp4"

    url = input("粘贴视频链接或 BV 号(类似bvid=BV1qZe26UEXz&trackid需删除&之后的东西)：").strip()
    if args.media_type:
        return url, args.media_type

    while True:
        choice = input(
            "保存格式：1 = MP4，2 = MP3，3 = MP4 + MP3（同时保存，默认 1）："
        ).strip().lower()
        media_type = {
            "": "mp4",
            "1": "mp4",
            "mp4": "mp4",
            "2": "mp3",
            "mp3": "mp3",
            "3": "both",
            "both": "both",
        }.get(choice)
        if media_type:
            return url, media_type
        print("格式选择无效，请输入 1、2、3、mp4、mp3 或 both。")


def ask_to_continue(success: bool) -> bool:
    if success:
        prompt = "下一步：1 = 继续下载其他视频，2 = 结束程序（默认 2）："
    else:
        prompt = "本次下载未完成：1 = 尝试其他视频，2 = 结束程序（默认 2）："

    while True:
        choice = input(prompt).strip().lower()
        if choice in ("1", "y", "yes", "继续"):
            return True
        if choice in ("", "2", "n", "no", "结束"):
            return False
        print("选择无效，请输入 1 或 2。")


def main() -> int:
    if sys.version_info < (3, 10):
        print("错误：当前 yt-dlp 需要 Python 3.10 或更高版本。", file=sys.stderr)
        return 2

    args = parse_args()
    interactive_mode = args.url is None
    preset_media_type = args.media_type

    try:
        ffmpeg_location = locate_ffmpeg(args.ffmpeg_location)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    if not ffmpeg_location:
        print(
            "错误：未找到可用的 FFmpeg。无需手动配置 PATH，请先安装带二进制文件的 Python 包：\n"
            "  py -m pip install -U imageio-ffmpeg\n"
            "安装后重新运行本脚本即可。也仍可使用 --ffmpeg-location 指定现有 FFmpeg。",
            file=sys.stderr,
        )
        return 2

    try:
        import yt_dlp
        from yt_dlp.utils import DownloadError
    except ImportError:
        print(
            "错误：未安装 yt-dlp。请执行：\n"
            '  py -m pip install -U --pre "yt-dlp[default]" imageio-ffmpeg',
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if interactive_mode:
        print("哔哩哔哩视频下载器（请只下载你有权保存的内容）")

    while True:
        try:
            args.media_type = preset_media_type
            raw_url, args.media_type = interactive_values(args)
            url = normalize_bilibili_url(raw_url)
        except ValueError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            if interactive_mode:
                print()
                continue
            return 2
        except (EOFError, KeyboardInterrupt):
            print("\n已结束程序。")
            return 130

        ydl_options = build_ydl_options(args, output_dir, ffmpeg_location)
        print(f"解析链接：{url}")
        print(f"yt-dlp 版本：{yt_dlp.version.__version__}")
        print(f"输出格式：{MEDIA_TYPE_LABELS[args.media_type]}")
        print(f"保存目录：{output_dir}")

        result_code = 0
        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                error_code = ydl.download([url])
        except DownloadError as exc:
            result_code = 1
            print(f"\n下载失败：{exc}", file=sys.stderr)
            if "Unable to extract initial state" in str(exc):
                print(
                    "原因：B 站把该 BV 视频重定向到特殊活动页，但当前 yt-dlp 未能从标准视频页还原活动页数据。\n"
                    "请直接使用含 /festival/ 和 bvid= 的原始活动页链接；本版脚本会保留该链接，不再改写。\n"
                    "如果仍失败，请更新 yt-dlp，并关闭浏览器后加 --browser edge（或 chrome）重试。",
                    file=sys.stderr,
                )
            else:
                print(
                    "建议：先更新 yt-dlp；若该清晰度需要登录，请关闭浏览器后加 --browser edge（或 chrome）。",
                    file=sys.stderr,
                )
        except KeyboardInterrupt:
            result_code = 130
            print("\n已取消本次下载。", file=sys.stderr)
        else:
            if error_code:
                result_code = int(error_code)
                print(f"下载未完成，错误码：{error_code}", file=sys.stderr)
            else:
                print(f"\n完成，文件已保存到：{output_dir}")

        if not interactive_mode:
            return result_code

        try:
            if not ask_to_continue(result_code == 0):
                print("程序已结束。")
                return result_code
        except (EOFError, KeyboardInterrupt):
            print("\n程序已结束。")
            return result_code
        print()


if __name__ == "__main__":
    raise SystemExit(main())
