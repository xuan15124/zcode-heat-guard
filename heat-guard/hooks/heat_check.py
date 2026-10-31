#!/usr/bin/env python3
# heat-guard · ZCode 插件：本机发热时暂缓重活（PreToolUse 钩子 + 按需查询）
#
# 定位: 纯消费者。本机装了独立采样服务 heat-sampler(root LaunchDaemon) 就读它的
# metrics.json; 没装/数据过期就用 macmon 兜底现采一次(内存里用完即弃)。
# 安装/卸载本插件不会新增、停止或重启任何服务。
#
# 模式（由第一个参数决定）:
#   默认(无参数): 钩子模式。读数据→判定——
#                 过热: 输出 PreToolUse deny JSON 拦下这条 Bash;
#                 温热: 输出 additionalContext 提醒; 正常: 静默放行。
#   status      : 人类可读的一行状态(技能用, 现读)。
#   json        : 输出当前指标 JSON。
#
# 配置文件: 用户目录 .zcode 下 heat-guard.json，缺省键自动回落内置值, 改完即生效。
# 可配键: hot_temp_c / warm_temp_c(判热判温阈值, 取 CPU GPU 温度较大者),
#         hot_power_w / warm_power_w(温度拿不到时的功率兜底),
#         metrics_path(采样服务的数据文件), stale_after_s(数据视为过期的秒数),
#         warn_warm(温热时是否注入提醒)。

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
CONFIG_FILE = HOME / ".zcode" / "heat-guard.json"
DEFAULT_METRICS = HOME / ".cache" / "heat-sampler" / "metrics.json"

DEFAULTS = {
    "hot_temp_c": 80.0,
    "warm_temp_c": 70.0,
    "hot_power_w": 20.0,
    "warm_power_w": 10.0,
    "metrics_path": str(DEFAULT_METRICS),
    "stale_after_s": 300,
    "warn_warm": True,
}

# macmon 由 brew 安装, 路径固定白名单; 只作兜底, 免 sudo
MACMON_HB = "/opt/homebrew/bin/macmon"
MACMON_LOCAL = "/usr/local/bin/macmon"


def load_config():
    cfg = dict(DEFAULTS)
    try:
        user = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if v is not None})
    except (OSError, ValueError):
        pass
    return cfg


def read_sampler_metrics(cfg):
    """读独立采样服务的数据; 不存在/损坏返回 None。绝不写任何文件。"""
    try:
        data = json.loads(Path(cfg["metrics_path"]).read_text(encoding="utf-8"))
        if isinstance(data, dict) and int(data.get("ts") or 0) > 0:
            return data
    except (OSError, ValueError, TypeError):
        pass
    return None


def macmon_fallback():
    """没装采样服务时的兜底: macmon 现采一次, 只在内存里用, 不落盘。"""
    exe = None
    if os.path.isfile(MACMON_HB) and os.access(MACMON_HB, os.X_OK):
        exe = "hb"
    elif os.path.isfile(MACMON_LOCAL) and os.access(MACMON_LOCAL, os.X_OK):
        exe = "local"
    if exe is None:
        return None
    out = None
    try:
        if exe == "hb":
            out = subprocess.run(
                ["/opt/homebrew/bin/macmon", "pipe", "-s", "1", "-i", "300"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        else:
            out = subprocess.run(
                ["/usr/local/bin/macmon", "pipe", "-s", "1", "-i", "300"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("{"):
                data = json.loads(line)
                if isinstance(data, dict):
                    t = data.get("temp") or {}

                    def watt(key):
                        try:
                            v = float(data.get(key))
                            return round(v, 1) if v > 0 else None
                        except (TypeError, ValueError):
                            return None

                    return {
                        "ts": int(time.time()),
                        "cpu_temp": t.get("cpu_temp_avg"),
                        "gpu_temp": t.get("gpu_temp_avg"),
                        "cpu_power_w": watt("cpu_power"),
                        "gpu_power_w": watt("gpu_power"),
                        "all_power_w": watt("all_power"),
                        "fan_rpm": [f.get("rpm") for f in data.get("fans") or []],
                        # 系统已降频 = 一票判热, 兜底模式也要有
                        "throttle_pct": pmset_throttle(),
                        "temp_src": "macmon-fallback",
                    }
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def pmset_throttle():
    """pmset -g therm 的 CPU_Speed_Limit, 没有节流记录返回 None。"""
    try:
        out = subprocess.run(
            ["/usr/bin/pmset", "-g", "therm"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        m = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", out)
        if m:
            return int(m.group(1))
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def current_metrics(cfg):
    data = read_sampler_metrics(cfg)
    if data and (time.time() - int(data["ts"])) <= cfg["stale_after_s"]:
        return data
    return macmon_fallback()


def effective_temp(m):
    temps = [t for t in (m.get("cpu_temp"), m.get("gpu_temp")) if t is not None]
    return max(temps) if temps else None


def classify(cfg, m):
    """返回 hot / warm / ok / unknown。节流中直接判热。"""
    if not m:
        return "unknown"
    tp = m.get("throttle_pct")
    if tp is not None and tp < 100:
        return "hot"
    t = effective_temp(m)
    if t is not None:
        if t >= cfg["hot_temp_c"]:
            return "hot"
        if t >= cfg["warm_temp_c"]:
            return "warm"
        return "ok"
    # 温度拿不到(传感器不可读)→ 功率兜底
    p = (m.get("cpu_power_w") or 0) + (m.get("gpu_power_w") or 0)
    if p > 0:
        if p >= cfg["hot_power_w"]:
            return "hot"
        if p >= cfg["warm_power_w"]:
            return "warm"
    return "unknown"


def heat_line(m):
    bits = []
    if m.get("cpu_temp") is not None:
        bits.append("CPU %s°C" % m["cpu_temp"])
    if m.get("gpu_temp") is not None:
        bits.append("GPU %s°C" % m["gpu_temp"])
    if m.get("power"):
        bits.append(m["power"])
    if m.get("fan_rpm"):
        bits.append("风扇 %srpm" % "/".join(str(r) for r in m["fan_rpm"]))
    if m.get("throttle_pct") is not None and m["throttle_pct"] < 100:
        bits.append("已节流 %s%%" % m["throttle_pct"])
    if m.get("temp_src"):
        bits.append("(%s)" % m["temp_src"])
    return " · ".join(bits) or "本机指标暂不可用"


def status_text(cfg, m, verdict):
    names = {"hot": "过热", "warm": "温热", "ok": "正常", "unknown": "未知"}
    return "%s —— %s(阈值 温热%s/过热%s°C)" % (
        heat_line(m), names[verdict], cfg["warm_temp_c"], cfg["hot_temp_c"])


def hook_main(cfg):
    data = current_metrics(cfg)
    verdict = classify(cfg, data)

    if verdict == "hot":
        reason = "本机发热: %s。先暂缓这条命令——请延后执行、拆成更轻的步骤, 或先询问用户是否继续。" % heat_line(data)
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    if verdict == "warm" and cfg.get("warn_warm", True):
        json.dump({
            "additionalContext": "本机温热: %s。可以继续, 但重的活(长编译/批量任务)考虑合并延后。" % heat_line(data),
        }, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    return 0


def main():
    argv = sys.argv[1:]
    cfg = load_config()

    if "--json" in argv:
        print(json.dumps(current_metrics(cfg) or {}, ensure_ascii=False))
        return 0

    if "--status" in argv:
        data = current_metrics(cfg)
        print(status_text(cfg, data or {}, classify(cfg, data)))
        return 0

    # 钩子模式: 只处理必要的 stdin(没有就跳过), 别挂住
    try:
        if not sys.stdin.isatty():
            sys.stdin.read()
    except (OSError, ValueError):
        pass
    return hook_main(cfg)


if __name__ == "__main__":
    sys.exit(main())
