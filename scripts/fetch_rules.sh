#!/usr/bin/env bash
# CR原文をローカルに取得する（本文はコミットしない → data/raw/ はgitignore）。
# 版・URL・ハッシュの正本は data/MANIFEST.json。新版に更新するときは
# MANIFEST を書き換えてから本スクリプトを実行し、ハッシュを更新する。
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/raw

UA="aizorius-judge/0.1 (rules fetch; https://github.com/reonyanarticle/aizorius-judge)"

url_en=$(python3 -c 'import json; print(json.load(open("data/MANIFEST.json"))["sources"]["cr_en"]["url"])')
file_en=$(python3 -c 'import json; print(json.load(open("data/MANIFEST.json"))["sources"]["cr_en"]["local_file"])')
url_ja=$(python3 -c 'import json; print(json.load(open("data/MANIFEST.json"))["sources"]["cr_ja"]["url"])')
file_ja=$(python3 -c 'import json; print(json.load(open("data/MANIFEST.json"))["sources"]["cr_ja"]["local_file"])')

echo "fetch EN: $url_en"
curl -sL -A "$UA" -o "$file_en" "$url_en"
echo "fetch JA: $url_ja"
curl -sL -A "$UA" -o "$file_ja" "$url_ja"

echo "--- sha256（MANIFEST と一致するか確認する）---"
shasum -a 256 "$file_en" "$file_ja"
python3 - <<'PY'
import hashlib, json

manifest = json.load(open("data/MANIFEST.json"))
for key, src in manifest["sources"].items():
    actual = hashlib.sha256(open(src["local_file"], "rb").read()).hexdigest()
    status = "OK" if actual == src["sha256"] else "MISMATCH（新版の可能性。MANIFESTの更新が必要）"
    print(f"{key}: {status}")
PY
