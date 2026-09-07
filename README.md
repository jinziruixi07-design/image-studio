# Image Studio

ノベルゲーム制作のための、**画像生成専用の独立したWebサイト**です。
[game](https://github.com/jinziruixi07-design/game) リポジトリ(ノベルゲーム本体)とはコードを完全に分けています。
このサイト単体で起動・利用でき、ゲーム側には一切依存しません。

生成した画像は手元にダウンロードして、ゲーム側の `novel/assets/characters/` や
`novel/assets/backgrounds/` に自分でコピーして使う、という流れになります。

## これは何をするサイト?

ブラウザで開くとこんな画面になります。

1. 「種類」で作りたいものを選ぶ(キャラクター立ち絵 / 背景 / 高速ラフ確認用)
2. 「欲しい画像の説明」に、英語の単語や文章で欲しい絵の内容を書く
3. 「生成する」ボタンを押す
4. 少し待つと画像が表示される
5. 「この画像をダウンロード」でPCに保存する

裏側では、画像を実際に描く役目の **ComfyUI** という別ソフトにお願いを送って、
できあがった絵を受け取って画面に表示している、という仕組みです。
このサイト自体は絵を描く機能を持たず、あくまで「ComfyUIへの注文書と受け取り窓口」です。

## 必要なもの

- Python 3.10以降
- **ComfyUI** が別途どこかで起動していること(下記の手順1)
  - 画像生成にはGPU(NVIDIA製)がほぼ必須です。GPU搭載PC、またはGPU付きのクラウド環境が必要になります

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

- SDXLワークフロー用: `sd_xl_base_1.0.safetensors` を ComfyUIの `models/checkpoints/` に配置
- FLUX.2 Klein(高速版)用: UNet本体・CLIPテキストエンコーダ2種・VAEを、それぞれ
  `models/unet/` `models/clip/` `models/vae/` に配置し、
  `workflows/character_portrait_flux_klein.json` 内のファイル名を実際に置いたファイル名に合わせて書き換えてください。
  配布元によりファイル名が異なるためです。

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

## フォルダの中身

```
server.py               このサイトの本体(Flaskという仕組みで動くWebサーバー)
comfy_client.py          ComfyUIへ注文を送って絵を受け取る処理
static/                  ブラウザに表示される画面(HTML/CSS/JS)
workflows/               ComfyUIへの「注文書」のひな形(SDXL/FLUX.2 Klein)
outputs/                 生成した画像がここに自動保存される(ダウンロードのバックアップ)
comfyui-runtime/         ComfyUI自体をDockerで起動するための設定
```

## 新しい「種類」(ワークフロー)を追加したい場合

1. ComfyUIの画面でワークフローを組み、メニューの "Save (API Format)" でJSONを保存
2. `workflows/<好きな名前>.json` として置く
3. `workflows/<同じ名前>.meta.json` を作り、どのノードがプロンプト/シード/保存先かを書く
   (既存のファイルを見本にしてください)
4. サイトを再読み込みすると「種類」の選択肢に自動で追加されます
