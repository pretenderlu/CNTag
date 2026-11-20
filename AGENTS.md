# CNTag 项目说明

CNTag 是 DiscTag 的姊妹应用，用于把现有中文音乐库中被音译（拼音）或英文填写的标签与文件名原位还原为中文。

## 测试
- `python -m unittest discover -s tests -v`
- `ruff check .`（规则见 `ruff.toml`，只检查真实错误）。
- 每个测试文件开头 `import _isolate`：把 `CNTAG_CONFIG_DIR` 指向临时目录，避免测试写入真实的设置、撤销记录和缓存。测试不得访问网络。
- `scripts/make_icon.py` 用 Pillow 生成 `assets/icon.png/.ico/.icns`。

## 代码结构
- 无界面逻辑：`textutil`（CJK / 拼音 / 简繁 / `name_match_score` / `artists_match`）、`tags`（读写标签与重命名，WAV 用 ID3 帧）、`library`（遍历与按专辑分组，含多碟合并）、`resolve`（名称解析与候选）、`matching`（文件对应曲目、生成行）、`scanner`（`scan_album` / `rows_for_candidate` / `scan_library`，含弱匹配降级为待确认）、`history`（应用与可重试撤销，每个文件写入后原子更新日志）、`models`。
- 曲库客户端：`catalog_itunes`、`catalog_netease`、`encyclopedia`（MusicBrainz / Wikidata）+ `cache`（sqlite），共享 `http.http_session()`。
- `cntag/app.py` 的 `CNTagApp` 只负责启动、线程调度（`_run_async` / `_post`，后台线程不得直接调用 Tk）、设置与退出；界面按职责拆成 `cntag/ui/` 下的 mixin：`layout`、`theme`、`options`、`library`、`candidates`、`compare`、`apply`、`keyboard`、`updates`，共享常量与辅助函数在 `ui/common.py`。
- 非界面模块：`settings`（settings.json 路径与读取）、`updates`（GitHub Release 检查与安装包下载）、`i18n`、`windowing`（Windows 原生窗口样式）、`rounded_panel` / `rounded_style`（圆角控件样式）。
- 界面文字一律以中文原文写成 `tr("中文 {0}", 值)`，英文译文在 `cntag/locales/en.py`。新增或修改文案时同步更新译文；`tests/test_i18n.py` 会检查缺失、多余和占位符不一致。不要在模块级（导入时）调用 `tr()`，需要本地化的常量写成函数。语言在 `main.py` 导入界面模块之前确定，切换后需重启。
- 测试中 mock 界面模块时，patch 目标要指向实际使用该名称的模块。

## 版本号
- 唯一来源：`cntag/__init__.py` 的 `__version__`。`CNTag.spec`、`installer/CNTag.iss` 和各处 User-Agent 都从这里读取。
- README 中的版本文字（"当前版本"和安装包文件名）需要手动同步；`tests/test_release.py` 会在不一致时失败。

## 发布流程
1. 修改 `__version__` 和 README，提交到 main，等待 `Tests` 工作流通过。
2. 推送附注 tag `v<版本>`（tag 信息为 `CNTag v<版本>`）。`Release` 工作流会：
   - 校验 tag 与 `__version__` 一致；
   - 在 Windows 上运行测试、构建，生成 `CNTag-Windows-x64.zip`（顶层为 `CNTag/`）和 `CNTagSetup-v<版本>.exe`；
   - 在 macOS（Apple Silicon / Intel）上构建并 ad-hoc 签名，生成两个 DMG；
   - 创建包含以上 4 个资产的**草稿** Release。
3. 在 GitHub 上核对草稿资产，按以往格式填写发布说明，然后发布。草稿和预发布不会触发应用内更新。
4. 自动更新要求 Release 资产带有 GitHub 的 `sha256` digest（上传后自动生成），发布后用 `check_for_updates("<旧版本>")` 验证。

本地构建（仅用于调试）：`python -m pip install -r requirements-dev.txt`，`python build_app.py` 输出到 `dist/CNTag`；安装包用 `"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\CNTag.iss`。

## 许可
- 项目本身为 GPL-3.0-or-later（`LICENSE`）。
- Mutagen 为 GPL-2.0-or-later，打包后的应用整体须以 GPL 兼容方式分发。第三方声明见 `THIRD_PARTY_NOTICES.md`，许可文本在 `licenses/`，由 `CNTag.spec` 打包进应用。
