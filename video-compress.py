#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
视频压缩 / 截取工具（交互式）

用法：把视频文件拖到 compress-video.bat 上，按屏幕提示操作。
也可直接运行：python video-compress.py "视频路径"

兼容 Python 3.8+，仅使用标准库。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))

VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv",
              ".flv", ".ts", ".webm", ".mpg", ".mpeg", ".3gp", ".rmvb")

LINE = "=" * 58


# --------------------------------------------------------------------------
# ffmpeg 定位：优先使用工具包内自带版本，保证可脱离 Python 环境独立运行
# --------------------------------------------------------------------------
def find_ffmpeg():
    candidates = [
        os.path.join(APP_DIR, "bin", "ffmpeg.exe"),
        r"D:\python\lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win64-v4.2.2.exe",
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG = find_ffmpeg()


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def human_size(num_bytes):
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return "%d B" % int(n)
            return "%.1f %s" % (n, unit)
        n /= 1024.0


def human_duration(seconds):
    seconds = float(seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return "%d:%02d:%04.1f" % (h, m, s)
    return "%02d:%04.1f" % (m, s)


def ask(prompt, allow_empty=False):
    """读取一行输入；EOF 时退出。"""
    try:
        value = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        sys.exit(0)
    value = value.strip().strip('"').strip("'")
    if not value and not allow_empty:
        return None
    return value


def parse_number(text):
    """把用户输入解析为浮点数，失败返回 None。支持 10 / 10.5 / 10MB。"""
    if text is None:
        return None
    t = text.strip().lower().replace("mb", "").replace("兆", "").strip()
    t = t.replace("％", "").replace("%", "")
    try:
        return float(t)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# 媒体探测
# --------------------------------------------------------------------------
def probe(path):
    """读取视频信息，返回 dict；失败返回 None。"""
    if not FFMPEG:
        return None
    try:
        proc = subprocess.run([FFMPEG, "-hide_banner", "-i", path],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return None
    text = proc.stderr.decode("utf-8", "replace")

    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0,
            "vbitrate": 0, "has_audio": False, "audio_kbps": 0}

    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if m:
        info["duration"] = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
                            + float(m.group(3)))
    m = re.search(r"Stream.*?Video:.*?(\d{2,5})x(\d{2,5})", text)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"Video:.*?,\s*([\d.]+)\s*kb/s", text)
    if m:
        info["vbitrate"] = int(float(m.group(1)))
    m = re.search(r"Video:.*?,\s*([\d.]+)\s*fps", text)
    if m:
        info["fps"] = float(m.group(1))
    m = re.search(r"Stream.*?Audio:.*?,\s*(\d+)\s*Hz", text)
    if m:
        info["has_audio"] = True
    m = re.search(r"Audio:.*?,\s*(\d+)\s*kb/s", text)
    if m:
        info["audio_kbps"] = int(m.group(1))

    if not info["duration"] or not info["width"] or not info["height"]:
        return None
    return info


# --------------------------------------------------------------------------
# 编码执行（带进度显示）
# --------------------------------------------------------------------------
def run_ffmpeg(cmd, duration, label):
    full = list(cmd)
    full[1:1] = ["-progress", "pipe:1", "-nostats", "-loglevel", "error"]

    proc = subprocess.Popen(
        full,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    interactive = sys.stdout.isatty()
    last_pct = -1
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("out_time_ms="):
            try:
                micro = int(line.split("=", 1)[1])
            except (ValueError, IndexError):
                continue
            if duration > 0:
                pct = int(micro / 1000000.0 / duration * 100)
                if pct > 100:
                    pct = 100
                if pct != last_pct:
                    last_pct = pct
                    if interactive:
                        sys.stdout.write("\r  %s %3d%%" % (label, pct))
                        sys.stdout.flush()

    err = proc.stderr.read()
    proc.wait()

    if interactive and last_pct >= 0:
        sys.stdout.write("\n")
        sys.stdout.flush()

    if proc.returncode != 0:
        raise RuntimeError(err.strip()[-1500:] or "ffmpeg 异常退出")
    return err


def verify(path):
    """全片解码校验。"""
    try:
        proc = subprocess.run([FFMPEG, "-hide_banner", "-v", "error",
                               "-i", path, "-f", "null", "-"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        return False, str(exc)
    err = proc.stderr.decode("utf-8", "replace").strip()
    if proc.returncode == 0 and not err:
        return True, "全片解码正常"
    return False, (err[:300] or "退出码 %d" % proc.returncode)


def unique_path(path):
    """避免覆盖已有文件。"""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 2
    while os.path.exists("%s(%d)%s" % (root, i, ext)):
        i += 1
    return "%s(%d)%s" % (root, i, ext)


# --------------------------------------------------------------------------
# 压缩参数决策
# --------------------------------------------------------------------------
def pick_scale(vbr_kbps, src_w, src_h):
    """按目标码率选择输出分辨率；不放大源片。"""
    if vbr_kbps >= 2400:
        target = 1080
    elif vbr_kbps >= 950:
        target = 720
    elif vbr_kbps >= 520:
        target = 540
    else:
        target = 360
    if target >= src_h:
        return "", "%dx%d（保持原分辨率）" % (src_w, src_h)
    w = int(round(target * float(src_w) / src_h / 2)) * 2
    return ("scale=%d:%d:flags=lanczos" % (w, target),
            "%dx%d" % (w, target))


def compute_compress_plan(info, target_mb, audio_kbps=96):
    """由目标体积反推码率与输出分辨率，返回计划 dict。"""
    duration = info["duration"]
    budget = target_mb * 8192.0 / duration            # kbps 总量
    audio = audio_kbps if info["has_audio"] else 0
    vbr = int(budget * 0.98 - audio)                  # 预留 2% 封装开销
    low_quality = False
    if vbr < 120:
        vbr = 120
        low_quality = True

    scale_filter, res_label = pick_scale(vbr, info["width"], info["height"])
    return {
        "target_mb": target_mb,
        "vbr": vbr,
        "audio": audio,
        "scale_filter": scale_filter,
        "res_label": res_label,
        "low_quality": low_quality,
    }


def compress_video(src, info, plan):
    """两遍编码压缩到目标体积。"""
    duration = info["duration"]
    vbr = plan["vbr"]
    audio_kbps = plan["audio"]
    scale_filter = plan["scale_filter"]
    audio_bps = 96 if audio_kbps else 0

    stem, _ = os.path.splitext(src)
    dst = unique_path(stem + "_压缩.mp4")

    tmpdir = tempfile.mkdtemp(prefix="vidpass_")
    passlog = os.path.join(tmpdir, "log")
    tmp_out = dst + ".part"
    started = time.time()
    try:
        base = [FFMPEG, "-hide_banner", "-y", "-i", src]
        vcodec = ["-c:v", "libx264", "-preset", "slow", "-profile:v", "high",
                  "-pix_fmt", "yuv420p", "-b:v", "%dk" % vbr,
                  "-maxrate", "%dk" % int(vbr * 1.3),
                  "-bufsize", "%dk" % (vbr * 2)]
        vf = ["-vf", scale_filter] if scale_filter else []

        cmd1 = (base + vcodec + ["-pass", "1", "-passlogfile", passlog]
                + vf + ["-an", "-f", "null", os.devnull])
        run_ffmpeg(cmd1, duration, "第一遍分析")

        acodec = (["-c:a", "aac", "-b:a", "%dk" % audio_bps, "-ac", "2"]
                  if audio_kbps else ["-an"])
        cmd2 = (base + vcodec + ["-pass", "2", "-passlogfile", passlog]
                + vf + acodec + ["-movflags", "+faststart", "-f", "mp4", tmp_out])
        run_ffmpeg(cmd2, duration, "第二遍编码")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if not os.path.isfile(tmp_out) or os.path.getsize(tmp_out) == 0:
        raise RuntimeError("未生成有效输出文件")
    os.replace(tmp_out, dst)
    return dst, time.time() - started


def trim_video(src, info, start, end):
    """截取片段：重编码保证切点精确，码率不超过源片以免体积虚增。"""
    duration = end - start
    stem, _ = os.path.splitext(src)
    dst = unique_path("%s_截取_%g-%gs.mp4" % (stem, start, end))
    tmp_out = dst + ".part"

    cmd = [FFMPEG, "-hide_banner", "-y",
           "-ss", "%.3f" % start, "-i", src, "-t", "%.3f" % duration,
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p"]
    # 以源片码率为上限，避免重编码后体积反而膨胀
    if info["vbitrate"] > 0:
        cap = int(info["vbitrate"] * 1.05)
        cmd += ["-maxrate", "%dk" % cap, "-bufsize", "%dk" % (cap * 2)]
    if info["has_audio"]:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", "-f", "mp4", tmp_out]

    started = time.time()
    run_ffmpeg(cmd, duration, "截取编码")

    if not os.path.isfile(tmp_out) or os.path.getsize(tmp_out) == 0:
        raise RuntimeError("未生成有效输出文件")
    os.replace(tmp_out, dst)
    return dst, time.time() - started


# --------------------------------------------------------------------------
# 交互流程
# --------------------------------------------------------------------------
def show_banner():
    print()
    print(LINE)
    print("            视 频 压 缩 / 截 取 工 具")
    print(LINE)


def show_info(src, info):
    size = os.path.getsize(src)
    print()
    print("[ 原始信息 ]")
    print("  文件      %s" % os.path.basename(src))
    print("  位置      %s" % os.path.dirname(src))
    print("  分辨率    %d x %d" % (info["width"], info["height"]))
    print("  时长      %s（共 %.1f 秒）"
          % (human_duration(info["duration"]), info["duration"]))
    print("  大小      %s" % human_size(size))
    if info["fps"]:
        print("  帧率      %.3g fps" % info["fps"])
    if info["vbitrate"]:
        print("  视频码率  %d kbps" % info["vbitrate"])
    print("  音轨      %s" % ("有" if info["has_audio"] else "无"))
    return size


def ask_target_mb(src_size_mb):
    """压缩目标：按比例 或 按目标体积。返回 (target_mb, 描述)。"""
    while True:
        print()
        print("[ 压缩方式 ]")
        print("  1) 按比例    —— 输入百分比，如 80 表示压缩到原体积的 80%")
        print("  2) 按目标大小 —— 输入数字，单位为 MB（兆字节），如 10 表示 10MB")
        print("  0) 返回上一步")
        choice = ask("请输入序号 [1]：", allow_empty=True)
        if choice is None or choice == "":
            choice = "1"

        if choice == "0":
            return None, None

        if choice == "1":
            print()
            print("  原体积 %s，可输入 1-99 的百分比。" % human_size(src_size_mb * 1048576))
            while True:
                raw = ask("请输入压缩比例（单位：%，例如 40）：")
                pct = parse_number(raw)
                if pct is None:
                    print("  [输入有误] 请输入数字，例如 40")
                    continue
                if pct <= 0 or pct >= 100:
                    print("  [超出范围] 比例需在 1-99 之间。若想放大请用别的工具。")
                    continue
                target = src_size_mb * pct / 100.0
                if target < 0.5:
                    print("  [目标过小] 预计仅 %.2f MB，画质会严重受损。换个大一点的吧。"
                          % target)
                    continue
                return target, "原体积的 %g%%（约 %.1f MB）" % (pct, target)

        if choice == "2":
            print()
            print("  单位说明：数字 = MB（兆字节）。例如输入 10 → 目标 10MB。")
            print("  当前文件 %s，目标应小于该值。" % human_size(src_size_mb * 1048576))
            while True:
                raw = ask("请输入目标大小（单位：MB）：")
                mb = parse_number(raw)
                if mb is None:
                    print("  [输入有误] 请输入纯数字，例如 10")
                    continue
                if mb <= 0:
                    print("  [输入有误] 数值需大于 0。")
                    continue
                if mb >= src_size_mb:
                    print("  [超出范围] 目标 %.1f MB 不小于原文件 %.1f MB，"
                          "请填更小的值。" % (mb, src_size_mb))
                    continue
                if mb < 0.5:
                    print("  [目标过小] 小于 0.5MB 基本无法保证可看性，请加大。")
                    continue
                return mb, "%.1f MB" % mb

        print("  [输入有误] 请输入 0、1 或 2。")


def ask_trim_range(duration):
    """截取区间：起始秒,结束秒。返回 (start, end) 或 None。"""
    print()
    print("[ 截取区间 ]")
    print("  格式：起始秒,结束秒  （英文或中文逗号均可）")
    print("  示例：30,90  表示从第 30 秒截到第 90 秒")
    print("  本片总时长 %.1f 秒" % duration)
    print("  输入 0 可返回上一步")

    while True:
        raw = ask("请输入区间：")
        if raw is None:
            print("  [输入有误] 不能为空，请按 起始秒,结束秒 的格式输入。")
            continue
        if raw == "0":
            return None
        text = raw.replace("，", ",").replace("、", ",").replace(" ", "")
        parts = text.split(",")
        if len(parts) != 2:
            print("  [格式错误] 需用逗号分隔两个数字，例如 30,90")
            continue

        start = parse_number(parts[0])
        end = parse_number(parts[1])
        if start is None or end is None:
            print("  [格式错误] 起始与结束都必须是数字（单位：秒）。")
            continue
        if start < 0 or end < 0:
            print("  [输入有误] 时间不能为负数。")
            continue
        if end <= start:
            print("  [输入有误] 结束时间必须大于起始时间（你输入的是 %g → %g）。"
                  % (start, end))
            continue
        if start >= duration:
            print("  [输入有误] 起始 %.1f 秒已超过总时长 %.1f 秒。"
                  % (start, duration))
            continue
        if end > duration:
            print("  [已修正] 结束 %.1f 秒超出总时长，自动改为 %.1f 秒。"
                  % (end, duration))
            end = duration
        if end - start < 0.5:
            print("  [区间过短] 至少需要 0.5 秒。")
            continue
        return start, end


def confirm(lines):
    print()
    print("[ 待执行 ]")
    for line in lines:
        print("  " + line)
    ans = ask("开始处理？(Y/n)：", allow_empty=True)
    if ans is None or ans == "":
        return True
    return ans.lower() in ("y", "yes", "是", "1")


def report(dst, seconds):
    size = os.path.getsize(dst)
    print()
    print("[ 处理完成 ]")
    print("  文件    %s" % dst)
    print("  大小    %s" % human_size(size))
    print("  耗时    %.1f 秒" % seconds)
    print("  校验    正在检查可播放性 …")
    ok, msg = verify(dst)
    print("           %s —— %s" % ("通过" if ok else "异常", msg))


def process_once(src):
    if not os.path.isfile(src):
        print("\n[错误] 找不到文件：%s" % src)
        return
    if not FFMPEG:
        print("\n[错误] 缺少 ffmpeg。请确认 bin\\ffmpeg.exe 存在。")
        return

    print("\n正在读取视频信息 …")
    info = probe(src)
    if info is None:
        print("\n[错误] 无法解析该文件，可能不是有效视频或已损坏。")
        return

    size = show_info(src, info)
    src_size_mb = size / 1048576.0

    while True:
        print()
        print("[ 请选择操作 ]")
        print("  1) 压缩视频")
        print("  2) 截取片段")
        print("  0) 退出")
        mode = ask("请输入序号 [1]：", allow_empty=True)
        if mode is None or mode == "":
            mode = "1"

        if mode == "0":
            return

        if mode == "1":
            target_mb, label = ask_target_mb(src_size_mb)
            if target_mb is None:
                continue
            plan = compute_compress_plan(info, target_mb)
            audio_bps = 96 if plan["audio"] else 0
            lines = [
                "压缩 %s" % os.path.basename(src),
                "→ 目标 %s" % label,
                "→ 视频 %dkbps + 音频 %dkbps，输出 %s"
                % (plan["vbr"], audio_bps, plan["res_label"]),
            ]
            if plan["low_quality"]:
                lines.append("→ [注意] 码率已压到下限 120kbps，画质会明显下降")
            if not confirm(lines):
                print("  已取消。")
                continue
            try:
                dst, elapsed = compress_video(src, info, plan)
            except RuntimeError as exc:
                print("\n[失败] 压缩出错：\n%s" % exc)
                continue
            report(dst, elapsed)
            return

        if mode == "2":
            rng = ask_trim_range(info["duration"])
            if rng is None:
                continue
            start, end = rng
            lines = [
                "截取 %s" % os.path.basename(src),
                "→ 第 %g 秒 到 第 %g 秒（时长 %g 秒）" % (start, end, end - start),
            ]
            if info["vbitrate"] > 0:
                lines.append("→ 画质 CRF 20，码率上限 %dkbps"
                             % int(info["vbitrate"] * 1.05))
            if not confirm(lines):
                print("  已取消。")
                continue
            try:
                dst, elapsed = trim_video(src, info, start, end)
            except RuntimeError as exc:
                print("\n[失败] 截取出错：\n%s" % exc)
                continue
            report(dst, elapsed)
            return

        print("  [输入有误] 请输入 1、2 或 0。")


def ask_file_path():
    while True:
        print()
        print("请把视频文件拖到本窗口，然后按回车：")
        raw = ask("路径：")
        if raw is None:
            print("  [输入有误] 路径不能为空。")
            continue
        path = raw.strip('"').strip("'")
        if os.path.isdir(path):
            print("  [输入有误] 这是文件夹，请拖入具体的视频文件。")
            continue
        if not os.path.isfile(path):
            print("  [找不到文件] %s" % path)
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext and ext not in VIDEO_EXTS:
            print("  [提示] 扩展名 %s 不常见，仍将尝试处理。" % ext)
        return path


def main():
    show_banner()

    args = [a for a in sys.argv[1:] if a.strip()]
    if len(args) > 1:
        print("\n[提示] 一次只处理一个文件，已取第一个：%s" % os.path.basename(args[0]))
    src = args[0] if args else ask_file_path()

    while True:
        process_once(src)
        print()
        ans = ask("还要处理其他文件吗？(y/N)：", allow_empty=True)
        if ans is None or ans.lower() not in ("y", "yes", "是", "1"):
            break
        src = ask_file_path()

    print("\n已退出。\n")


if __name__ == "__main__":
    main()
