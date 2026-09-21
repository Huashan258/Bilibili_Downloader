# Bilibili Downloader

一个简单的 B 站视频下载脚本，支持保存为 MP4、MP3，或同时保存两种格式。

## 安装

需要 Python 3.10 或更高版本：

```bash
py -m pip install -U --pre "yt-dlp[default]" imageio-ffmpeg
```

## 使用

```bash
py bilibili_downloader.py
```

按提示粘贴视频链接或 BV 号，然后选择：

- `1`：MP4
- `2`：MP3
- `3`：MP4 + MP3

文件默认保存在脚本旁的 `downloads` 文件夹。下载完成后可选择继续下载或结束程序。

> 请只下载你有权保存的内容。
