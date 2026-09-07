# Image Studio

ノベルゲーム制作のための、**画像生成専用の独立したWebサイト**です。
[game](https://github.com/jinziruixi07-design/game) リポジトリ(ノベルゲーム本体)とはコードを完全に分けています。
このサイト単体で起動・利用でき、ゲーム側には一切依存しません。

生成した画像は手元にダウンロードして、ゲーム側の `novel/assets/characters/` や
`novel/assets/backgrounds/` に自分でコピーして使う、という流れになります。

## これは何をするサイト?

ブラウザで開くとこんな画面になります。

1. 「種類」で作りたいものを選ぶ
2. 「欲しい画像の説明」に、欲しい絵の内容を書く(英語推奨。後述のAI変換機能を使えば日本語の雑な指示でもOK)
3. 「生成する」ボタンを押す
4. 少し待つと**4枚**の候補画像が並んで表示される
5. 気に入った画像を「ダウンロード」でPCに保存する

裏側では、画像を実際に描く役目の **ComfyUI** という別ソフトにお願いを送って、
できあがった絵を受け取って画面に表示している、という仕組みです。
このサイト自体は絵を描く機能を持たず、あくまで「ComfyUIへの注文書と受け取り窓口」です。

### 選べる「種類」(ワークフロー)

| 種類 | 説明 |
|---|---|
| キャラクター立ち絵 (SDXL) | 文章だけから新しいキャラクターを描く。高品質・低速 |
| キャラクター立ち絵 (FLUX.2 Klein) | 同上だが蒸留モデルで高速。ラフ確認向け |
| 背景 (SDXL) | 文章だけから背景を描く |
| 新規キャラクター (2枚の参照画像からブレンド) | 2枚の参考画像(顔・服装・雰囲気など)の要素を混ぜて新しいキャラを作る |
| 既存キャラクターの表情・ポーズ違い | 保存済みキャラクター(または1枚の参照画像)を元に、同じキャラのまま表情やポーズだけを変える |

後半2つは「画像から画像を作る」モードで、**IPAdapter**というComfyUIの追加機能を使います
(セットアップ手順は下記)。

### キャラクターライブラリ

生成した4枚の中から気に入ったものを「キャラクターとして保存」しておくと、画面下の
「保存したキャラクター」に並びます。保存したキャラクターは「既存キャラクターの表情・ポーズ違い」
を使うときに、参照画像アップロードの代わりにドロップダウンから選べます。

これにより、1回作って終わりではなく、**同じキャラクターの素材を後から何度でも追加できます**。
保存データは `characters/` フォルダに画像とJSONで置かれ、Gitには含めていません(手元にだけ残ります)。

## 必要なもの

- Python 3.10以降
- **ComfyUI** が別途どこかで起動していること(下記の手順1)
  - 画像生成にはGPU(NVIDIA製)がほぼ必須です。GPU搭載PC、またはGPU付きのクラウド環境が必要になります

## GPU搭載PCが無い場合: Google Colabで動かす

GPU搭載PCをお持ちでない場合は、`colab/ImageStudio_Colab.ipynb` を使うと、
Google ColabのGPUを借りてComfyUIとImage Studioの両方を起動できます。

1. https://colab.research.google.com を開き、「アップロード」タブからこのリポジトリの
   `colab/ImageStudio_Colab.ipynb` を開く(またはGitHubタブで
   `jinziruixi07-design/image-studio` を検索して開く)
2. 「ランタイム」→「ランタイムのタイプを変更」で **GPU** を選ぶ
3. ノートブックに書かれた説明に従って、上から順にセルを実行する
4. 最後のセルで表示される `https://xxxxx.trycloudflare.com` のようなURLをブラウザで開く

これだけで、下記の手順1・2で説明しているセットアップがすべて自動で行われます。
Colab無料版には利用時間の制限があるため、長時間の作業には向きませんが、
まず試してみるには十分です。

### 直接手元のPC/サーバーでComfyUIを動かす場合

Colabを使わず、ご自身のGPU環境で動かす場合は、以下の手順1・2を参照してください。

## 手順1: ComfyUIを起動する

このリポジトリの `comfyui-runtime/` フォルダに、ComfyUIをDockerで起動するための設定を入れてあります。

```bash
cd comfyui-runtime
docker compose up --build
```

初回はComfyUI本体のダウンロード・ビルドで時間がかかります。
起動できたら `http://localhost:8188` でComfyUIの画面(このサイトとは別の画面)が開けるか確認してください。

Dockerを使わずローカルに直接インストールする場合:

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt
python main.py --listen 127.0.0.1 --port 8188
```

### モデルファイルの準備

- **SDXLワークフロー用**: `sd_xl_base_1.0.safetensors` を ComfyUIの `models/checkpoints/` に配置
- **FLUX.2 Klein(高速版)用**: UNet本体・CLIPテキストエンコーダ2種・VAEを、それぞれ
  `models/unet/` `models/clip/` `models/vae/` に配置し、
  `workflows/character_portrait_flux_klein.json` 内のファイル名を実際に置いたファイル名に合わせて書き換えてください。
  配布元によりファイル名が異なるためです。
- **参照画像から作る2つのワークフロー用(IPAdapter)**:
  1. ComfyUI Managerから **ComfyUI_IPAdapter_plus** カスタムノードをインストールしてください
     ([https://github.com/cubiq/ComfyUI_IPAdapter_plus](https://github.com/cubiq/ComfyUI_IPAdapter_plus))
  2. IPAdapterのモデルファイルと、CLIP Visionのモデルファイルをダウンロードして配置してください
     (`models/ipadapter/` と `models/clip_vision/` など。カスタムノードのREADMEに従ってください)
  3. `workflows/character_new_from_references.json` と
     `workflows/character_consistent_variation.json` 内の `preset` の値(例: `"PLUS (high strength)"`)は
     お使いのIPAdapterのバージョンによって選択肢が変わることがあります。ComfyUIの画面上で一度
     ノードを組んで動作確認し、必要ならJSONの値を実際の設定に合わせて調整してください。

  IPAdapterはコミュニティ製の拡張機能で頻繁に更新されるため、このリポジトリのワークフローは
  「動作の目安」として用意したものです。うまく動かない場合は、ComfyUIの画面上でノードを
  組み直し、メニューの "Save (API Format)" で書き出したJSONに差し替えてください。

## 手順2: このサイト(Image Studio)を起動する

ComfyUIが起動した状態で、別のターミナルで:

```bash
pip install -r requirements.txt
python server.py
```

ブラウザで `http://127.0.0.1:5000` を開くと、画像生成の画面が表示されます。

ComfyUIを手順1と違うアドレスで動かしている場合は、環境変数で教えてあげてください。

```bash
COMFYUI_URL=http://192.168.1.10:8188 python server.py
```

## AIによる「雑な日本語→英語プロンプト」自動変換(任意機能)

プロンプト欄の隣に出る「AIで英語プロンプトに変換」ボタンは、Claude(Anthropic API)を使って
日本語の雑な指示を画像生成向けの英語プロンプトに変換します。**この機能は無くてもサイトの他の
機能は全部使えます。**

### 有効にする

1. [console.anthropic.com](https://console.anthropic.com/settings/keys) でAPIキーを発行する
2. このフォルダに `.env` という名前でファイルを作り、以下を書く

   ```
   ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
   ```

   (`.env.example` をコピーして書き換えると簡単です。`.env` はGitには含まれません)
3. `python server.py` を再起動すると、ボタンが表示されるようになります

### 料金について

この機能は使うたびにごくわずかな従量課金(Anthropic API利用料)が発生します。
軽量モデル(Haiku)を使っているため、1回あたり1円未満程度です。

### 後で完全に無効化・課金を止めたい場合

以下のどちらか(両方やっても構いません)で、いつでも完全に止められます。

- **このサイト側で止める**: `.env` ファイルを削除する、または中の `ANTHROPIC_API_KEY=` を
  空にする。次回起動時からボタンが表示されなくなり、このサイトからは一切APIを呼ばなくなります。
- **Anthropic側で止める**: [console.anthropic.com](https://console.anthropic.com/settings/keys)
  でそのAPIキー自体を削除(Revoke)する。キーが無効になるので、他のどこかで使い回していても
  一切使えなくなります。

## フォルダの中身

```
server.py                              このサイトの本体(Flaskという仕組みで動くWebサーバー)
comfy_client.py                        ComfyUIへ注文を送って絵を受け取る処理
prompt_expand.py                       Claude APIで日本語→英語プロンプト変換する処理(任意機能)
static/                                ブラウザに表示される画面(HTML/CSS/JS)
workflows/                             ComfyUIへの「注文書」のひな形
outputs/                               生成した画像がここに自動保存される(ダウンロードのバックアップ)
characters/                            保存したキャラクターの画像・情報(Gitには含めない)
comfyui-runtime/                       ComfyUI自体をDockerで起動するための設定
.env.example                           ANTHROPIC_API_KEYの設定例
```

## 新しい「種類」(ワークフロー)を追加したい場合

1. ComfyUIの画面でワークフローを組み、メニューの "Save (API Format)" でJSONを保存
2. `workflows/<好きな名前>.json` として置く
3. `workflows/<同じ名前>.meta.json` を作り、どのノードがプロンプト/シード/保存先かを書く
   (既存のファイルを見本にしてください)。参照画像を使うワークフローなら、`reference_nodes`
   (LoadImageノードのID一覧)と `reference_labels`(画面に出すラベル)も書いてください
4. サイトを再読み込みすると「種類」の選択肢に自動で追加されます
