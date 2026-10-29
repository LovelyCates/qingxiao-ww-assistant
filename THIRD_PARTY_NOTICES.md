# 来源、修改与第三方许可

本项目为修改版本，修改日期：2026-10-30。仓库发布源码按根目录AGPL-3.0许可提供；原作者版权及许可保留。

- **OK-WW**：https://github.com/ok-oldking/ok-wuthering-waves 。基础v3.7.8，选取后续修复及v3.7.13活动功能。原AGPL-3.0文本保留在`ok-wuthering-waves-3.7.8/LICENSE.txt`和`LICENSES/AGPL-3.0.txt`。
- **ok-script 2.0.13**：https://github.com/ok-oldking/ok-script ，网站 https://ok-script.com/ 。完整许可保留于`LICENSES/ok-script-2.0.13.txt`，含Apache-2.0、Commons Clause和额外条款。其依赖包由包管理器单独获取，没有被重新许可，也未随本仓库捆绑。
- PySide6/Qt、PySide6-Fluent-Widgets及其他依赖遵循其发行包原许可。版本锁定在`requirements.lock.txt`。
- 上游识别图片、翻译资源、图标与模型未直接包含在公开Git树中。`upstream-resources.json`只记录来源路径、版本、长度和SHA-256。获取脚本从上游v3.7.8读取，保留校验结果。
- 默认界面保留清宵人物主题：图标和壁纸为参考角色形象生成的同人视觉。角色及相关商标权益归库洛游戏和相关权利人，详见`manual_launcher/assets/CHARACTER-ART.md`。代码AGPL不包含对第三方角色IP的再授权。
- 原创几何SVG及渲染图仍保留为缺少人物素材时的回退资源，按根项目许可提供。

整个运行栈并非统一的无限制商用许可。完整组合二进制安装包的兼容性、组件和素材分发范围尚待核实；本次只公开源码预览。
