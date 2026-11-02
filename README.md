# 插件商店助手（astrbot_plugin_plugin_shop）

让 AstrBot 的机器人自己逛插件市场：搜索、安装、启用、停用、卸载插件。全部能力以 LLM 工具的形式暴露，用户直接说需求即可，安装和变更操作默认需要用户确认。

## 功能

- **市场搜索**：按功能描述、插件名或作者搜索官方插件市场，返回 ID、版本、简介、仓库地址，并标注是否已安装。
- **安装预览 + 确认安装**：先返回插件来源、版本、作者和风险说明；用户明确同意后才真正下载安装，安装后自动加载。
- **已安装列表**：列出本地插件的启用状态，可按关键词过滤。
- **启停与卸载**：启用、停用、卸载插件；卸载默认关闭，需要在配置里显式开启。

## 安装

在 AstrBot 的插件目录下克隆：

```bash
cd /path/to/AstrBot/data/plugins
git clone https://github.com/mo1463/astrbot_plugin_plugin_shop.git
```

重启 AstrBot，或在 WebUI 插件页启用。

## 使用

直接用自然语言提需求，例如：

- 「帮我找一个天气插件」
- 「把刚才那个插件装上」
- 「列出我装了哪些插件」
- 「停用 astrbot_plugin_xxx」

管理员也可以发送 `/插件市场` 查看说明。

## 配置

插件配置项（WebUI 插件配置页）：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable` | bool | `true` | 关闭后不注册任何工具 |
| `admin_only` | bool | `true` | 仅管理员和被允许的用户可用 |
| `extra_allowed_users` | list | `[]` | 额外允许的用户 ID，仅在 `admin_only` 开启时生效 |
| `allow_uninstall` | bool | `false` | 是否允许卸载（删除插件文件） |

## LLM 工具

| 工具名 | 作用 |
| --- | --- |
| `plugin_market_search` | 搜索插件市场 |
| `plugin_market_install` | 查看安装信息 / 确认后安装 |
| `plugin_shop_list` | 列出已安装插件 |
| `plugin_shop_manage` | 启用 / 停用 / 卸载插件 |

## 安全说明

- 安装和变更操作采用两段式：首次调用返回预览且不执行，`confirm=true` 才真正执行。
- 默认仅管理员可用。
- 安装会下载并立即加载第三方代码，属于高风险操作，请只安装可信来源的插件。
- 卸载默认关闭，避免误删。

## 兼容性

- AstrBot `>= 4.0.0`
- 支持平台：`aiocqhttp`、`telegram`、`qq_official`

## License

[MIT](./LICENSE)
