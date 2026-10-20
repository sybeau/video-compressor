# 第三方组件声明

本仓库包含（或依赖）以下第三方组件，其版权归各自作者所有。

## 1. ffmpeg

- 文件：`bin/ffmpeg.exe`
- 版本：4.2.2（Windows x64 静态构建）
- 来源：通过 `imageio-ffmpeg` 分发的预编译二进制
- 项目主页：https://ffmpeg.org/
- 源码获取：https://ffmpeg.org/download.html
- 许可证：**GPL v2 或更高版本**（该构建启用了 GPL 组件）

> 说明：本工具仅以**独立进程调用**方式使用 ffmpeg，未修改其源码，也未将其链接进本项目代码。
> 若你再次分发本仓库（含该二进制），请保留本声明，并遵守 GPL 的相关要求（提供许可证文本与源码获取途径）。

## 2. Python

- 目录：`runtime/`
- 版本：3.13.7 embeddable（Windows x64）
- 来源：https://www.python.org/downloads/windows/
- 许可证：PSF License Agreement
- 说明：仅作为运行本工具的独立解释器，未修改。

## 3. 本项目自身代码

- 文件：`video-compress.py`、`compress-video.bat`、`README.md`
- 许可证：见仓库根目录 `LICENSE`（MIT）

---

如对授权有疑问，请以各组件官方发布的许可证原文为准。
