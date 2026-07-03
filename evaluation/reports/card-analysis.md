# 実カード分析（Scryfall連携・MCP層の前倒し検証）

実在カードで「カード特定→キーワード→CRルール」の動線を検証した結果。

## 稲妻（Lightning Bolt）
- fuzzy解決: `稲妻` → Lightning Bolt ✓ / 公式裁定 0件
- keywords→ルール対応: （キーワードなし）
- 質問「稲妻はプレインズウォーカーを対象にできますか」→ 検索: 702.6（Keyword Abilities）, 122.1（Counters）, 306.1（Planeswalkers）

## オークの弓使い（Orcish Bowmasters）
- fuzzy解決: `オークの弓使い` → Orcish Bowmasters ✓ / 公式裁定 8件
- keywords→ルール対応: Amass→701.47, Flash→702.8
- 質問「相手がドローしたときに誘発する能力はスタックに載りますか」→ 検索: 603.10（Handling Triggered Abilities）, 117.2（Timing and Priority）, 113.8（Abilities）

## 孤独（Solitude）
- fuzzy解決: `孤独` → Solitude ✓ / 公式裁定 2件
- keywords→ルール対応: Lifelink→702.15, Evoke→702.74, Flash→702.8
- 質問「想起でクリーチャーを唱えたときの生け贄はいつ発生しますか」→ 検索: 702.110（Keyword Abilities）, 702.82（Keyword Abilities）, 702.86（Keyword Abilities）

## 敏捷なこそ泥、ラガバン（Ragavan, Nimble Pilferer）
- fuzzy解決: `敏捷なこそ泥、ラガバン` → Ragavan, Nimble Pilferer ✓ / 公式裁定 6件
- keywords→ルール対応: Treasure→対応なし, Dash→702.109
- 質問「疾駆で唱えたクリーチャーはターン終了時にどうなりますか」→ 検索: 702.91（Keyword Abilities）, 506.7（Combat Phase）, 508.1（Declare Attackers Step）

## 波使い（Master of Waves）
- fuzzy解決: `波使い` → Master of Waves ✓ / 公式裁定 7件
- keywords→ルール対応: Protection→702.16
- 質問「エレメンタルのトークンは召喚酔いの影響を受けますか」→ 検索: 302.6（Creatures）, 614.16（Replacement Effects）, 111.10（Tokens）

