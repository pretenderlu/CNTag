# CNTag

CNTag 是一款 Windows 与 macOS 桌面工具，DiscTag 的姊妹项目，用于把现有中文音乐库中被音译（拼音）或英文填写的标签与文件名，原位还原为正确的中文。

当前版本：**v0.1.0**

> 状态：早期开发。当前版本只包含应用骨架（界面、国际化、设置与自动更新），还原逻辑将在后续版本加入。

## 功能（规划中）

- 扫描现有音乐库，识别拼音 / 英文标签对应的正确中文专辑与曲目资料。
- 原位回写中文标签（标题、歌手、专辑、专辑歌手等）并按规范重命名文件。
- 写入前展示当前标签与中文标签的逐项对比，确认后再执行。
- 支持中文和英文界面：默认跟随系统语言，可点击右下角的 “English / 中文” 切换，切换后自动重启。
- 启动时后台检查 GitHub 最新 Release，发现更新时显示圆点；Windows 可自动下载并安装更新，macOS 可跳转到发布页。

## 下载与运行

发布页提供 Windows 安装包与压缩包，以及 Apple Silicon、Intel Mac 的 macOS 构建：

[下载 Releases](https://github.com/pretenderlu/CNTag/releases)

Windows 用户可运行 `CNTagSetup-v0.1.0.exe` 完成安装，默认安装到 `%LOCALAPPDATA%\Programs\CNTag`，不需要管理员权限。安装器会创建开始菜单快捷方式，也可选择桌面快捷方式。也提供免安装 ZIP，解压后运行 `CNTag.exe` 并保留 `_internal` 目录。

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
