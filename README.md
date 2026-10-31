# 日本語の指示を解釈し、走行を変更するロボット

既存のUbuntu 22.04 / ROS 2 Humble / Gazebo Fortress環境に追加した。
ローカルモデルQwen2.5 1.5BをOllamaで実際に推論し、
日本語から行動列を生成する。

## 課題要件との対応

|課題要件|実装・提出方法|
|---|---|
|AIの使用 必須 推論のみ可|ローカルLLMによる日本語の指示解釈と行動列生成|
|自由なロボットタスク|前後移動・旋回・停止を組み合わせた走行|
|サンプルからの発展|手動WASD操作を自然言語による計画と実行前確認へ拡張|
|1〜3分の動画 MP4|日本語入力・実際のAI出力・ロボット動作を画面録画|
|使用コード一式|既存src、新規2ファイル、依存と起動方法、出典をpublic GitHubへ|

## 修正箇所

既存ファイルの編集は **0個**、新規ファイルは以下の **2個** 。

1. `~/fortress_ws/src/nav_dev/scripts/ai_commander.py` を追加。
   AI問い合わせ、JSON検証、実行前確認、Twist送信、停止、ログを担当。
2. `~/fortress_ws/src/nav_dev/launch/nav_ai.launch.py` を追加。
   既存 `nav_teleop.launch.py` と同様にGazebo・ブリッジを起動し、
   手動 `teleop_node` を起動するNodeブロックを含めない構成。

`teleop_node.cpp`、`world.sdf`、`nav_teleop.yaml`、`CMakeLists.txt`、
`package.xml`は変更なし。
Pythonを直接起動するため、CMakeへの実行ファイル追加やpip導入は不要。
既存CMakeの `install(DIRECTORY launch config models ...)` が新launchを配置。


## 1 AIの環境準備 Windows PowerShellの場合

ローカルの環境で、コンテナ名が異なる場合は `pai_ros2` を実際の名前に置換すること。

初回のみ、順番に実行すること。

```powershell
docker start pai_ros2
docker network create pai_ai_net
docker network connect pai_ai_net pai_ros2
docker run -d --name pai_ai --network pai_ai_net -v pai_ollama:/root/.ollama ollama/ollama:latest
docker exec pai_ai ollama pull qwen2.5:1.5b
docker exec pai_ai ollama list
```

`pai_ai_net` が既にあればcreateを省略。既に接続済みならconnectも省略。
`pai_ai` が既にある場合は再度runせず `docker start pai_ai` を実行。
起動直後にサーバー未準備と出たら `docker logs pai_ai` を確認し、pullを再実行。
モデルは約986MB。GPU・APIキー・有料契約は不要。
RAMはPC全体16GB程度を出発点の目安とし、CPU推論速度とGazeboの負荷を実測。

ROSとAIはDockerの同じネットワークで通信するため、11434のホストポート公開は不要。
ブラウザは従来どおり `http://localhost:6080/` を使用。

```powershell
docker image inspect ollama/ollama:latest --format '{{index .RepoDigests 0}}'
docker exec pai_ai ollama --version
docker exec pai_ai ollama list
```

## 2 ファイル配置

配布ZIPをWindowsのダウンロードフォルダーで展開し、
`PAI_AI_Demo`フォルダーが存在することを確認します。
解凍先が異なる場合はPowerShellのコピー元だけ変更。

```powershell
docker cp "$env:USERPROFILE\Downloads\PAI_AI_Demo" pai_ros2:/home/ubuntu/
```

ブラウザのUbuntuデスクトップでTerminalを開き、以後はUbuntu端末で実行。

```bash
cd ~/PAI_AI_Demo
bash install_demo.sh
source /opt/ros/humble/setup.bash
python3 -c 'import rclpy; from geometry_msgs.msg import Twist; print("ROS Python OK")'
cd ~/fortress_ws
colcon build --symlink-install --packages-up-to nav_dev --cmake-args -DBUILD_TESTING=OFF
source ~/fortress_ws/install/setup.bash
```

`rclpy`が見つからなければ、まずsourceが同じ端末で済んでいるか確認。
それでも不足していれば `sudo apt-get update` と
`sudo apt-get install ros-humble-rclpy` を実行。
conda/pixi等の別Python環境を起動せず、Ubuntuのpython3を使用。

## 3 AI推論だけを先に確認する

Ubuntu端末で実行。
ロボットは動きませんが、LLMへの推論要求は実際に行う。

```bash
source /opt/ros/humble/setup.bash
python3 ~/fortress_ws/src/nav_dev/scripts/ai_commander.py --plan-only "少し前へ進んで、そのあと左を向いて止まってください"
```

`AI PLAN`にforward、left、wait等が指示の順序で出るか確認。
計画が不正な場合は止まり、固定の代替走行には切り替えない。
指示が曖昧なら単純に言い換え、再度推論ください。

JSON構造、最大6動作、各0.5〜4秒、合計20秒以内をコードが検証。
速度は人が定義した0.15m/s、旋回は0.5rad/sに固定。
AIは動作の順序・種類・時間を決め、ROSノードが20Hzで実行。

## 4 走行の事前リハーサル

以前の手動launchを起動端末でCtrl+Cして終了。
GazeboのKey Publisherも追加しない。

**Ubuntu端末A シミュレーター**

```bash
source /opt/ros/humble/setup.bash
source ~/fortress_ws/install/setup.bash
ros2 launch nav_dev nav_ai.launch.py
```

以前と同様に黒い画面になる場合だけ、終了して以下で起動。

```bash
LIBGL_ALWAYS_SOFTWARE=1 QT_X11_NO_MITSHM=1 ros2 launch nav_dev nav_ai.launch.py
```

**Ubuntu端末B 推論と実行**

```bash
source /opt/ros/humble/setup.bash
source ~/fortress_ws/install/setup.bash
ros2 node list
ros2 topic info /cmd_vel --verbose
python3 ~/fortress_ws/src/nav_dev/scripts/ai_commander.py "少し前へ進んで、そのあと左を向いて止まってください"
```

`teleop_node`、`key_hit_event_node`が存在していたら、手動launchを終了。
AI実行前はブリッジのsubscriberがあり、他の速度publisherがいない状態を確認。
`AI PLAN`を読み、意味が正しければEnter、不適切ならqとEnterで中止。
初回の確認入力はプログラム内の操作で、端末のシェルではない。
`EXEC`の表示とロボットの動きが対応するか確認。
`DONE`は指令送信完了の意味です。位置・経路の成功を自動判定していない。

中断は端末BでCtrl+C。異常時の停止は同じPythonスクリプトの専用モードで送れる。
別publisherでの緊急停止を使うときは、先にAIをCtrl+Cで止める。

```bash
python3 ~/fortress_ws/src/nav_dev/scripts/ai_commander.py --stop
```

プログラムのfinallyで停止指令を繰り返しますが、プロセス強制終了や通信断は保証範囲外。

## 5 録画中に実行したコマンド例

端末Bの環境読み込みを済ませ、次を順番に実行。
事前に用意した日本語のプロンプト指示を4回実行し、録画。

**指示A Ubuntu端末B**

```bash
python3 ~/fortress_ws/src/nav_dev/scripts/ai_commander.py "少し前へ進んで、そのあと左を向いて止まってください"
```

`AI PLAN`を画面上で説明し、正しければ **Enter**。走行終了まで待ちます。

**指示B 同じ端末B**

```bash
python3 ~/fortress_ws/src/nav_dev/scripts/ai_commander.py "少しバックしてから右へ旋回して、最後に停止してください"
```

再度AIが出した計画を確認して **Enter**。指示Bは現在の姿勢を基準に実行。

`AI PLAN`は説明用の一例であり、実際の結果を記録します。
最終画面で「AIは日本語から計画を生成。検証後ROS 2で実行。


## 6 推論の証拠と評価

`~/fortress_ws/demo_logs/*.json` に指示、モデル、推論時間、
AIのレスポンス、実行した計画、指令送信の状態を保存。
推論失敗時の固定fallbackはなく、その場合はエラー表示で終了。
`planned`は推論だけ、`cancelled`は実行中止、
`commands_completed`は指令送信完了。

今回は４種類の指示を試した。

|入力|実際のAI出力|意味の一致|目視での動作|推論時間|
|---|---|---|---|---|
|前進→左→停止|実測を記入|○/×|実測を記入|実測を記入|
|バック→右→停止|実測を記入|○/×|実測を記入|実測を記入|
|上記の言い換え指示|実測を記入|○/×|実測を記入|実測を記入|
|上記の言い換え指示|実測を記入|○/×|実測を記入|実測を記入|


## 7 提出用コードをWindowsへコピー実施

既存モデルやキー入力用パッケージも含め、動かしたコード一式を提出。
この追加キットだけでは既存環境を再現できないので、次で既存srcも集めた。

**Windows PowerShell**

```powershell
$out = Join-Path $env:USERPROFILE "PAI_final_submission"
New-Item -ItemType Directory -Force -Path $out | Out-Null
docker cp pai_ros2:/home/ubuntu/fortress_ws/src $out
docker cp pai_ros2:/home/ubuntu/fortress_ws/demo_logs $out
docker cp pai_ros2:/home/ubuntu/PAI_AI_Demo $out
docker cp pai_ros2:/home/ubuntu/fortress_sources/2DRoboPrac_ws/LICENSE "$out\UPSTREAM_LICENSE"
```

## 参考URL

- ベース記事: https://qiita.com/N622/items/9d89f77d85d9da0af29e
- 元コード: https://github.com/OsawaKousei/2DRoboPrac_ws
  コミット `123fd2e4ddfccf420499a02a3852c17a369f93bb`
- Ollama CPU Docker: https://docs.ollama.com/docker
- APIと構造化出力: https://docs.ollama.com/api/generate
- モデルとライセンス: https://ollama.com/library/qwen2.5:1.5b
- 録画: https://support.microsoft.com/en-us/windows/apps/use-snipping-tool-to-capture-screenshots

確認日 2026年10月26日
