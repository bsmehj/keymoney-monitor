# KeyMoney Monitor · API 余额桌面悬浮球

一个 Windows 桌面悬浮球小工具：随时瞥一眼你的 AI 平台账户还剩多少额度/钱。
鼠标悬停显示明细，右键菜单可刷新、改配置、跳转平台控制台查实际金额。

当前监控两个平台：

| 平台 | 悬浮球显示 | 数据来源 |
|---|---|---|
| 阿里云百炼（Token Plan 订阅） | 本月剩余额度百分比（如 `30%`） | 本机 `bl` CLI：`bl usage token-plan` |
| 硅基流动 SiliconFlow | 账户总余额（如 `¥14.0`） | 官方接口 `GET /v1/user/info` |

> 口径说明：百炼 Token Plan 是订阅套餐，没有"现金余额"概念，悬浮球显示的是**本月剩余套餐额度%**；
> 阿里云账户的**现金余额**请通过右键菜单"百炼·阿里云费用中心"跳转查询。
> 配置了硅基流动 Key 后，球面优先显示硅基流动的 ¥ 金额。

## 功能一览

- 桌面悬浮球：置顶、可拖拽（位置自动记忆）、不遮挡操作
- 悬停弹层：两平台余额明细、额度重置日期、最近更新时间
- 状态外圈环：正常无环 / 余额偏低橙环 / 查询异常红环 / 加载中灰环
- 自动刷新：默认每 5 分钟后台查询（可配置），不卡界面
- 双击球：立即刷新
- 右键菜单：立即刷新 / 设置（打开配置文件）/ 百炼·阿里云费用中心（查现金余额）/ 硅基流动·控制台（查余额/充值）/ 退出
- 单实例保护：重复启动不会叠加多个球
- 外观与任何桌面壁纸无关：自带不透明底盘（白底 + 深色 Octocat 图标 + 白色文字）

## 快速开始（exe，无需 Python）

1. 双击 `dist/KeyMoneyMonitor.exe`，桌面右下角出现悬浮球
2. 配置硅基流动 Key：右键球 →"设置"，在打开的 `config.json` 中填写
   `siliconflow_api_key`（`sk-` 开头），保存后双击球刷新
3. 百炼无需填 Key：复用本机 `bl` CLI 的登录态（见下）

### 百炼登录态维护

悬浮球通过 `bl` CLI 查询百炼额度。若球变红且提示 console 过期，在终端执行：

```bash
bl auth login --console --config token-plan
```

浏览器扫码登录后即恢复（登录态有效期有限，过期需重复此步骤）。
未安装 `bl` CLI 时：`npm install -g bailian-cli && bl skill init`。

## 配置文件

exe 同目录的 `config.json`（源码运行时为项目根目录的 `config.json`），首次运行自动生成，不入库：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `siliconflow_api_key` | `""` | 硅基流动 API Key；留空则跳过该平台 |
| `siliconflow_base_url` | `https://api.siliconflow.cn` | 国际站改为 `https://api.siliconflow.com` |
| `bailian_enabled` | `true` | 是否查询百炼 |
| `refresh_interval_seconds` | `300` | 自动刷新间隔（最小 30） |
| `siliconflow_low_balance` | `10.0` | 低于此 ¥ 值显示橙环 |
| `bailian_low_percent` | `20.0` | 剩余 % 低于此值显示橙环 |
| `ball_x` / `ball_y` | `null` | 悬浮球位置；删掉这两项可恢复默认右下角 |

隐私：所有凭证仅保存在本机该配置文件中，程序不上传任何数据到第三方。

## 源码运行与打包

环境：Windows + Python 3.10+（自带 tkinter）。运行时仅用标准库；
生成图标和打包额外需要 Pillow、PyInstaller。

```bash
python keymoney_monitor.py          # 源码运行
python make_icon.py                 # 重新生成 assets/ 图标（换图/改色后执行）
python -m PyInstaller --onefile --noconsole --name KeyMoneyMonitor ^
  --icon "<绝对路径>\assets\icon.ico" ^
  --add-data "<绝对路径>\assets;assets" ^
  --distpath dist --workpath build --specpath build keymoney_monitor.py
```

注意：`--icon` / `--add-data` 必须用**绝对路径**（相对路径会被解析到 spec 目录）。
换悬浮球图标：替换 `assets/icon_source.jpg` 后运行 `make_icon.py` 再打包；
底盘色/猫形颜色/状态环在 `make_icon.py` 顶部常量中修改。

## 常见问题

- **球变红**：悬停看原因。百炼多为 console 登录过期（按上文重新登录）；硅基流动多为 Key 无效或网络问题。
- **球不见了**：可能被拖到屏幕边缘外——删除配置中 `ball_x`/`ball_y` 后重启；或进程已退出，重新双击 exe。
- **打开设置/控制台没反应**：程序通过 `explorer.exe` 唤起关联程序/默认浏览器，检查是否被安全软件拦截。
- **出现两个球**：单实例保护失效时才会发生（端口 57321 被占用以外的异常），任务管理器结束多余 `KeyMoneyMonitor.exe` 进程。
- **额度数字与控制台不一致**：悬浮球每 5 分钟刷新一次，双击球可立即同步。

## 目录结构

```
keymoney_monitor.py   主程序（单文件，纯标准库）
make_icon.py          图标生成脚本（Pillow）
assets/               悬浮球状态贴图 ball_*.png、exe 图标 icon.ico、原图 icon_source.jpg
dist/                 KeyMoneyMonitor.exe（其 config.json 首次运行自动生成）
config.json           首次运行自动生成，不入库（.gitignore 排除）
```