# 单素材批量高光帧截取设计

## 背景

真实执行批次显示，高光帧后处理包含完整视频下载和每帧一次 FFmpeg 调用。单素材通常生成 0 秒封面与 5 个点击峰值帧，因而启动 5 到 6 个 FFmpeg 进程。高光任务必须完成后才允许下一 RPA 详情波次开始，这一批次屏障是既定业务约束，不能在本次修改中放开。

本次目标是仅将单素材内的 FFmpeg 调用粒度从每帧一次改为每素材一次，同时保持候选规则、精确时间语义、文件路径、manifest 合约和失败可用性不变。

## 非目标

- 不改变 `select_standard_highlight_candidates()` 的 0 秒封面加点击指数 Top5 规则。
- 不改变 `HIGHLIGHT_CONCURRENCY = 3`，也不改变下一 RPA 波次等待全部高光任务结束的逻辑。
- 不采用输入侧 `-ss`、`-noaccurate_seek`、HTTP Range 下载或 JPEG 质量参数调整。
- 不修改 `highlights-manifest.json` 的 schema、帧命名或报告资产消费方式。

## 设计

### 截帧执行器

在 `scripts/yuntu_highlights.py` 新增 `extract_frames_batch(video_path, requests, *, ffmpeg_bin=None)`。每个 request 包含目标秒数及对应 staging 路径。调用方先依据既有候选列表生成最终目标路径和随机 staging 输出路径。

执行器构建单条 FFmpeg 命令：

```text
-i source-video -threads 1 -filter_threads 1
-filter_complex "[0:v]split=N[s0]...[sN]; [s0]trim=start=T0,setpts=PTS-STARTPTS[o0]; ..."
-map [o0] -frames:v 1 -q:v 2 staging0.jpg
...
-map [oN] -frames:v 1 -q:v 2 stagingN.jpg
```

FFmpeg 保持默认精确解码行为。`trim=start=T` 在已输入的视频时间线上丢弃目标时刻前的帧，随后每个分支只输出首帧。一个进程只打开一次输入并只初始化一次解码器；解码持续到最晚目标时刻。每个分支可能处理输入流中的同一帧，但不会发生旧实现中六次独立的进程启动、文件打开和从起点解码。

候选秒点在标准规则下互不重复；通用调用若出现重复秒点，先按目标列表去重，保留首个输出请求，避免 FFmpeg 产生语义相同的重复支路。

### 发布与回退

批量命令只写 staging 文件，绝不直接覆盖正式 JPEG。命令成功后逐张验证：文件存在、长度大于零、前两字节为 `FF D8`、后两字节为 `FF D9`，并用 FFmpeg 的单帧解码检查确认图像可读。

仅当全部 staging 文件通过验证时，才逐张使用 `Path.replace()` 发布到现有正式路径。任一命令、输出或验证失败时，删除本轮 staging 文件并调用已有逐帧 `extract_frame()` 流程处理所有候选帧。逐帧路径继续保留已有的单帧失败记录与本地有效资产复用行为。

批量失败的异常原因应保留在 worker 侧日志/错误文本中，但对 manifest 的外部帧记录保持现有兼容格式。批量成功生成的新帧记录继续不新增 `frame_source`，与旧的实时提取帧一致。

### 调度与资源边界

`yuntu_batch.py` 不更改波次屏障：只有 `pending_details` 和 `pending_highlights` 都为空时，才能选择和提交下一详情波次。批量执行器使用 `-threads 1 -filter_threads 1`，使三素材并发时最多为三个解码线程和三个滤镜线程，降低高峰资源竞争及进程被杀风险。

## 测试与验收

新增单元测试覆盖：

1. 多个目标帧生成一条 FFmpeg 命令，且命令包含一组 `split/trim/setpts` 分支、资源限制和逐输出映射。
2. JPEG 验证拒绝空文件、缺失 SOI/EOI 标记及 FFmpeg 无法解码的文件。
3. 批量成功时只调用一次批量执行器，且 staging 文件全部通过后才发布。
4. 任一批量输出失败或不合法时，所有候选帧自动回退到逐帧提取，并不发布不完整的批量结果。
5. 既有候选选择、文件命名、manifest、本地复用和 RPA 波次屏障测试继续通过。

使用真实批次的素材执行手工基准：记录每素材视频下载耗时和批量截帧耗时；与逐帧基线比较帧数量、目标秒数、图像可解码性、尺寸和 SHA-256。SHA-256 不一致视为待调查差异，而不是默认允许的结果。
