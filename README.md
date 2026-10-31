# heat-guard · ZCode 发热守卫插件

机器发热时自动暂缓重活的 ZCode 插件：每次执行 Bash 前检查本机温度/节流状态，**过热直接拦下并提示延后**，温热时轻提醒。

与 [heat-sampler](https://github.com/xuan15124/heat-sampler)（Mac 采样服务）**互相独立**：

- 本机装了 heat-sampler → 直接读它的精准数据（最热核口径）
- 没装 → 插件自己用 macmon 兜底现采（免 sudo，多传感器平均口径）
- **安装/卸载本插件不会新增、停止或重启任何服务**

## 安装

```bash
git clone https://github.com/xuan15124/zcode-heat-guard.git
```

然后 ZCode → **插件市场 → 添加 → 添加插件市场**，粘贴 clone 出来的目录路径 → 安装 **heat-guard**。

## 行为

| 状态 | 条件 | 动作 |
|---|---|---|
| 过热 | CPU/GPU 最热 ≥80°C，或系统已节流 | **拒绝这条 Bash**，提示 agent 延后/拆小/问用户 |
| 温热 | ≥70°C | 放行 + 注入一句"重的活考虑合并延后" |
| 正常 | — | 静默放行 |

另附带技能 **heat-guard**：随时问"现在本机多少度"查看温度/功率/风扇。

## 配置 `~/.zcode/heat-guard.json`（可选，改完即生效）

```json
{
  "hot_temp_c": 80.0,       // 判热阈值 (°C, 取 CPU/GPU 较大者)
  "warm_temp_c": 70.0,      // 判温阈值
  "hot_power_w": 20.0,      // 温度不可读时的功率兜底 (W)
  "warm_power_w": 10.0,
  "metrics_path": "~/.cache/heat-sampler/metrics.json",
  "stale_after_s": 300,     // 采样数据视为过期的秒数
  "warn_warm": true         // 温热时是否注入提醒
}
```

## License

MIT
