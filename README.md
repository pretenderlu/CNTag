# CNTag

CNTag 是一款 Windows 与 macOS 桌面工具，DiscTag 的姊妹项目，用于把现有中文音乐库中被音译（拼音）或英文填写的标签与文件名，原位还原为正确的中文。

当前版本：**v0.1.0**

> 状态：早期开发，尚未发布正式版本。

## 功能

- 扫描整个音乐库，每个文件夹视为一张专辑；`CD1` / `Disc 2` / `第2碟` 等子文件夹自动合并为同一张多碟专辑。
- 名称解析：MusicBrainz / Wikidata 别名 → iTunes 英文别名 → 歌手作品列表拼音匹配（`Dan Dan You Qing` → 淡淡幽情），再到 iTunes（可选网易云）获取中文曲目。
- 按曲号、拼音标题和别名把本地文件对应到曲目；解析到的歌手与预期不符或多数曲目对不上时，不会自动勾选，而是列出候选专辑等待确认。
- 候选专辑显示封面、曲目列表和曲目数对比，也可手动输入专辑名 / 歌手搜索。
- 标签对比表逐项显示原值 → 新值，可勾选、编辑，按置信度一键筛选。
- 写入标题、歌手、专辑、专辑歌手、流派、曲号和碟号，可同时把文件重命名为 `NN - 标题.ext`；支持 MP3、FLAC、M4A、OGG/Opus、WAV。
- 每次应用都会记录修改前的标签与文件名，可在“撤销…”中随时还原（支持部分撤销后重试）。
- 繁体自动转简体（可关闭），iTunes 地区可选台湾、中国大陆、香港、日本、美国。
- 支持中文和英文界面：默认跟随系统语言，可点击右下角的 “English / 中文” 切换，切换后自动重启。
- 启动时后台检查 GitHub 最新 Release，发现更新时显示圆点；Windows 可自动下载并安装更新，macOS 可跳转到发布页。

## 下载与运行

发布页提供 Windows 安装包与免安装压缩包，以及 Apple Silicon、Intel Mac 的 macOS 构建：

[下载 Releases](https://github.com/pretenderlu/CNTag/releases)

Windows 用户可运行 `CNTagSetup-v0.1.0.exe` 完成安装，默认安装到 `%LOCALAPPDATA%\Programs\CNTag`，不需要管理员权限。安装器会创建开始菜单快捷方式，也可选择桌面快捷方式。也提供免安装 ZIP，解压后运行 `CNTag.exe` 并保留 `_internal` 目录。

macOS 构建使用 ad-hoc 签名，未经过 Apple Developer ID 签名和公证，首次打开时 macOS 会提示无法验证开发者。放行方法（只需一次）：

1. 将 `CNTag.app` 拖入“应用程序”文件夹，双击打开，在提示框中点“完成”。
2. 打开“系统设置 → 隐私与安全性”，在页面下方找到 CNTag 的提示，点“仍要打开”，再输入密码确认。

也可以在终端执行 `xattr -dr com.apple.quarantine /Applications/CNTag.app` 后再打开。

## 从源码运行

需要 Python 3.12 或更高版本。

```bash
python -m pip install -r requirements.txt
python main.py
```

Windows 和 macOS 均可使用以下命令构建桌面应用。构建前安装构建依赖：

```bash
python -m pip install -r requirements-dev.txt
python build_app.py
```

Windows 构建输出到 `dist/CNTag/CNTag.exe`；安装包用 Inno Setup 编译 `installer/CNTag.iss` 生成。`dist` 和 `build` 不会提交到仓库。

## 测试

```bash
python -m pip install -r requirements.txt ruff
ruff check .
python -m unittest discover -s tests -v
```

## 许可

本项目以 GPL-3.0-or-later 发布（`LICENSE`）。第三方组件声明见 `THIRD_PARTY_NOTICES.md`，许可文本在 `licenses/`。
