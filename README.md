# 全景校园 · 上课

项目用 Blender 还原石家庄一中东校区，再把校园模型导入 Godot，制作可步行探索的《上课》。校园平面与外观依据航拍和 45 个全景站点校对，建模范围包括校门、广场、教学楼及连廊、图书馆、体育区和公寓楼。

## 下载游玩

在 [GitHub Releases](https://github.com/lgx123123456/panorama-campus/releases/tag/v0.2.35) 下载 `Shangke-Setup-v0.2.35.exe`。安装包适用于 Windows 10/11 x64，安装后从开始菜单打开「上课」。主菜单可选择「自由探索」「丧尸模式」和「多人联机」。

## 从源码运行

准备 Git LFS 和 Godot 4.6.3。先取回校园模型和碰撞等大文件，再用 Godot 项目管理器导入 `游戏设计/openfire/project.godot`。资源导入完成后，按 `F5` 进入主菜单。

```sh
git lfs install
git clone https://github.com/lgx123123456/panorama-campus.git
cd panorama-campus
git lfs pull
godot --editor --path "游戏设计/openfire"
```

Windows 玩家版使用 Godot 的 `Windows Player` 导出预设，需要同版本的导出模板。把导出程序命名为 `上课.exe`，保留同目录的运行库，再用 Inno Setup 编译[安装脚本](游戏设计/openfire/tools/windows_installer.iss)。脚本接收 `ReleaseDir`、`ReleaseVersion` 和 `OutputPath` 三个参数。

## 项目结构

| 位置 | 内容 |
| --- | --- |
| [还原](还原/) | Blender Python 建模脚本、场景索引、实景校准与动线记录 |
| [游戏设计](游戏设计/) | 玩法、界面与联机设计文档 |
| [游戏设计/openfire](游戏设计/openfire/) | Godot 工程、运行资产、测试场景和 Windows 打包脚本 |

原始全景、航拍参考、Blender 母版和历轮建模产物由本地项目保存。重跑建模脚本前需备齐脚本引用的底图、照片及前一轮母版。Godot 工程随仓库提供当前运行所需的校园资源。

## 当前还原范围

- 校门至尚德广场、教学轴线、孔德广场与体育区已接入同一校园场景。
- 致远楼、思远楼接入教室和东西两端楼梯。绅远楼与蕙远楼接入贯通楼道、宿舍、卫生间及三处楼梯。
- 部分楼层、房间布局、入口位置和尺寸依据照片与楼壳估排，继续随实景资料修订。建模顺序和现场核对项见[分轮还原计划](还原/从大门开始的分轮还原计划.md)及[实景门位与游戏动线核对](还原/实景门位与游戏动线核对.md)。

游戏工程基于 OpenFire 和 Godot。第三方模型、声音及组件的来源与许可见[署名文档](游戏设计/openfire/CREDITS.md)及[OpenFire 许可证](游戏设计/openfire/LICENSE)。
