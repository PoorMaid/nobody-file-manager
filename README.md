# Nobody 网页文件管理器 · 使用说明

一个单文件 Python 服务 + 网页面板，在手机/电脑浏览器里浏览、上传、编辑、解压、执行命令。
**免 root 可用**，不需要装任何 pip 包。
**有 root 更好**：设备具备 `su` 时，`启动.sh` 会自动探测并以 root 启动后端，此时可直接浏览 `/` 根目录、读写系统路径；无 `su` 则自动回退普通权限，访问不到的路径按只读处理并在界面提示。
**全盘访问只认真实 root**：后端启动后会实际探测权限（能否读到多个不同应用 uid 的 `data/data` 子目录、`/system/bin/su` 是否返回 uid=0）。proot 里的 `uid=0` 是假 root，不会被当成 root。探测不到时 `/api/info` 返回 `isRoot:false` 并附 `rootHint`，前端首次打开会弹出「需要 root 才能全盘访问」提示，绝不静默降级。
**已移除 SAF（系统选择器）授权**：不再提供「唤起系统选择器」按钮与 `/api/saf_picker`、`/api/saf_grants` 接口。授权目录现在只靠「扫描可访问的储存空间」+ 手动填路径添加。
---

## 一、怎么启动

在终端里执行（任意目录都可以，不必先 cd）：

```
sh /storage/emulated/0/Download/shhtml/启动.sh
```

**脚本会自己定位所在目录**，所以上面这个绝对路径只是最保险的写法；已经 cd 到本文件夹时，`sh 启动.sh` 也一样。
万一目录找错了，报错信息会直接打印一条可复制的绝对路径命令，照着执行即可。

---

## 一之二、菜单式交互（推荐）

不带参数执行会进入交互菜单，装好 Python 后长这样：

```
==============================================
  Nobody 网页文件管理器
  时间 Time：2026-11-18 13:24
  目录 Dir ：/storage/emulated/0/Download/shhtml
  Python   ：/usr/bin/python3
==============================================
  状态 Status：· 未运行 Not running
  【1】启动 Start
  【2】停止 Stop
  【3】重新安装 Python Reinstall Python
  【4】查看状态 Status
  【5】查看日志 Log
  【0】退出 Exit
  请输入编号：
```

**如果没装 Python，菜单会自动退化成两项：**

```
  Python：✗ 未安装 Not installed
  状态 Status：✗ 没有 Python，无法启动
  【1】自动安装 Python Install Python
  【2】退出 Exit
```

选 1 就自动装，装完回到菜单再选 1 启动。全程不用手敲命令。

---

## 一之三、也可以直接带参数跑（适合脚本调用）

```
sh 启动.sh start      # 启动服务
sh 启动.sh stop       # 停止服务
sh 启动.sh status     # 查看状态
sh 启动.sh log        # 看最后 30 行日志
sh 启动.sh install    # 仅安装 Python
```

参数直达模式不会弹菜单。

（旧的 `停止.sh` 仍可用，等价于 `sh 启动.sh stop`。）

---

## 一之四、启动时会做什么

选 1 后脚本依次完成 5 步，并在屏幕上打出状态：

```
[1/5] 检查文件 Check files              OK
[2/5] 检查 Python Check Python          OK：路径 + 版本
[3/5] 清理旧进程 Clean old process      OK
[4/5] 选择端口并启动 Select port and start   Port + PID + 健康检查
[5/5] 获取访问网址 Get access URL       局域网 IP
```

启动成功后的结尾面板长这样：

```
✅ 启动成功 Startup successful
访问网址 URL   ：http://192.168.x.x:9178/     ← 同一 WiFi 的手机/电脑打开这个
本机网址 Local ：http://127.0.0.1:9178/
端口 Port      ：9178    PID：6485
```

- 网址同时写到 `logs/url.txt`，可直接复制。
- 网页右上角也有「复制地址」按钮，一键复制当前网址。

**若服务已在运行**，选 1 不会再启动一遍，而是给出：

```
  【1】重启服务 Restart
  【2】返回菜单 Back
```

---

## 二、运行环境要求（重要）

本服务是 **Python** 写的，所以运行它的环境里必须有 `python3`。
Android 系统自带 shell（`/system/bin/sh`）里**没有** python，这是系统限制，不是脚本问题。

脚本会在第 [2/5] 步自动探测下面这些位置：

```
$PREFIX/bin/python3    → Termux
/usr/bin/python3       → 常见 Linux / proot Ubuntu
/usr/local/bin/python3
python3 / python       → 走 PATH
```

**任意一个能命中就能跑。** 如果全都没有，**不用手动装**——菜单会自动变成「1 自动安装 Python / 2 退出」，选 1 即可。

自动安装会按环境依次尝试这些包管理器：

| 包管理器 | 命中环境 | 实际命令 |
| --- | --- | --- |
| `pkg` | Termux | `pkg update -y && pkg install -y python` |
| `apt` / `apt-get` | Ubuntu / Debian / proot | `apt update -y && apt install -y python3`（非 root 自动 `sudo`） |
| `dnf` / `yum` | Fedora / CentOS | `dnf install -y python3` |
| `pacman` | Arch | `pacman -Sy --noconfirm python` |
| `apk` | Alpine | `apk add python3` |

装完脚本会立刻复查，成功会显示路径和版本，然后回菜单选 1 启动。

> 若一个包管理器都没找到（例如在 Android 原生 `/system/bin/sh` 里直接跑），脚本会提示换到 Termux 或 proot Ubuntu。Android 原生 shell 装不了 Python，是系统限制。

手动装也可以（备用）：

| 方式 | 操作 |
| --- | --- |
| Termux（推荐） | 装 Termux → `pkg install python` → 在 Termux 里执行 `sh /storage/emulated/0/Download/shhtml/启动.sh` |
| proot Ubuntu | MT 管理器/其它 proot 环境里装好 `python3`，然后在 Ubuntu 终端里执行 |
| Operit 内置 Ubuntu 终端 | 直接执行 `sh /storage/emulated/0/Download/shhtml/启动.sh` |

> 注意：**脚本自带目录定位**，所以在哪个环境里跑都不必先 cd，给绝对路径最稳。
> Termux 若提示 `Permission denied` 而文件确实存在，先执行一次 `termux-setup-storage` 授权存储访问。

---

## 三、目录结构

```
shhtml/
├── 启动.sh          核心启动脚本（唯一入口，自带目录定位）
├── 停止.sh          停止服务（等价 sh 启动.sh stop）
├── README.md        本说明
├── app/
│   └── server.py    Web 服务端（只用 Python 标准库，零依赖）
├── web/
│   └── index.html   网页面板前端（单文件，无外部 CDN）
└── logs/            运行时自动生成
    ├── server.log   服务输出日志
    ├── server.pid   当前进程号
    ├── port.txt     实际使用的端口
    └── url.txt      访问网址
```

`logs/` 里除 `server.log` 外，其余文件由脚本自动维护，删掉也没关系。

---

## 四、依赖说明

- **Python 3.6+**，只用标准库：`http.server`、`json`、`os`、`shutil`、`subprocess`、`zipfile`、`signal` 等。
- **不需要** pip install 任何东西，不需要 Flask/Django。
- 可选工具（有就用，没有不影响启动）：
  - `curl` —— 用于启动时的健康检查；没有则跳过，等 1 秒直接判定
  - `pgrep` —— 清理残留进程更彻底；没有就只靠 pid 文件
  - `ss` / `netstat` / `fuser` —— 端口占用检测；都没有则直接尝试
  - `termux-clipboard-set` —— 自动复制网址到剪贴板

---

## 五、端口

脚本按下面顺序自动挑第一个空闲端口：

```
9178 → 9179 → 9180 → 9181 → 9190 → 8888 → 9000
```

也可以用环境变量强制指定：

```
SHHTML_PORT=9001 sh /storage/emulated/0/Download/shhtml/启动.sh start
```

**文件根目录**默认是 `/sdcard`（即手机内部存储），想改成别的：

```
SHHTML_ROOT=/sdcard/Download sh /storage/emulated/0/Download/shhtml/启动.sh start
```

---

## 六、网页面板功能

- 浏览目录、进入/返回上级
- 查看文本文件、预览图片
- 上传（支持多选）、下载
- 新建文件夹 / 新建文件 / 重命名 / 复制 / 移动 / 删除
- 打包成 zip
- **终端卡片**：在设备本机执行 shell 命令，跟随当前浏览目录，支持 ↑/↓ 命令历史、Ctrl+L 清屏

---

## 七、常见问题

**Q：提示"未找到 python3"？**
直接执行 `sh 启动.sh`，菜单会变成「1 自动安装 / 2 退出」，选 1 自动装即可。装不上再看第二节手动方案。

**Q：Termux 里提示 `Permission denied`，但文件明明在？**
文件本身权限没问题，是 Termux 没拿到共享存储访问权。执行一次 `termux-setup-storage` 并允许授权，然后重试。仍不行就把整个 shhtml 文件夹复制到 `~/storage/downloads/` 下再跑，脚本会在新位置自己定位。**不要用 `chmod` 修**，手机存储（sdcardfs）上改了也不生效。

**Q：启动失败 / 日志有报错？**
脚本会直接把 `logs/server.log` 内容打出来。也可以手动 `cat logs/server.log` 看。

**Q：端口被占用？**
脚本会自动往后挑端口，结尾面板里的端口就是实际用的。也可用 `SHHTML_PORT` 手动指定。

**Q：手机电脑打不开？**
确认在同一 WiFi、IP 取对了（看结尾面板）、系统防火墙/其它 VPN 没拦截。

**Q：会不会影响手机其它 App？**
不会。它只是一个用户态 Python 进程，监听一个本地端口，`sh 停止.sh` 就结束。
