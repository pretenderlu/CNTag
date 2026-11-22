import sys

from cntag import i18n
from cntag.settings import load_settings

if "--self-test" in sys.argv[1:]:
    from cntag.selftest import main as self_test

    sys.exit(self_test(sys.argv[1:]))

# 在导入界面模块之前确定语言。模块导入时不再生成界面文字，此顺序只是保持简单、稳妥。
i18n.set_language(i18n.resolve(load_settings().get("language", "auto")))

from cntag.app import CNTagApp  # noqa: E402


if __name__ == "__main__":
    CNTagApp().run()
