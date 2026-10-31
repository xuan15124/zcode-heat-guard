---
name: heat-guard
description: 查看本机实时温度/功率/风扇/节流状态。当 heat-guard 钩子拦下了命令、用户问「电脑多少度/发热了吗/风扇怎么这么响」、或准备跑重活前想确认机器状态时使用。
---

# 本机温度检查

用 Bash 工具现采一次（`$ZCODE_PLUGIN_ROOT` 是本插件安装目录）：

```bash
/usr/bin/python3 "$ZCODE_PLUGIN_ROOT/hooks/heat_check.py" --status
```

需要原始数据（喂给图表或进一步判断）时用 `--json`。

输出是一行：`CPU 温度 · GPU 温度 · 功率 · 风扇 · 节流 —— 判定(阈值)`。

汇报要点：

- **过热(hot)**：钩子会自动拦下重活；此时不要重试被拦的命令，向用户说明当前温度，建议等几分钟降温和/或先做轻量工作（改代码、看文件）。
- **温热(warm)**：可以干活，但主动建议把长编译/批量任务合并、延后。
- **正常(ok)**：直接给数据。
- **未知(unknown)**：说明温度传感器没读到（可能 macmon 缺失或 SMC 不可读），可以建议 `brew install macmon`。

阈值配置在 `~/.zcode/heat-guard.json`（hot_temp_c / warm_temp_c，默认 80 / 70），改完即生效，不用重启。
