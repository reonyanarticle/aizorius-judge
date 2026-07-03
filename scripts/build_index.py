"""検索インデックスを構築する（初回／CR更新時／モデル変更時）。

実行: uv run python scripts/build_index.py
前提: data/comprehensive_rules_{en,ja}.json（無ければ scripts/parse_rules.py を先に）。
"""

from __future__ import annotations

import logging
import sys

from aizorius_judge.data_loader import build_or_load_index
from aizorius_judge.settings import Settings


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    index = build_or_load_index(Settings())
    print(
        f"index ready: rules={len(index.corpus)} device={index.embedder.device} "
        f"model={index.embedder.model_name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
