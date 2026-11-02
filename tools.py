import asyncio
from dataclasses import dataclass, field
from typing import Any

from astrbot.api import FunctionTool, logger
from astrbot.api.event import AstrMessageEvent

from .market import load_market, search


def _short(text: Any, limit: int = 160) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


@dataclass
class PluginShopTool(FunctionTool):
    shop: Any = None

    async def _deny(self, event: AstrMessageEvent) -> str | None:
        return await self.shop.check_permission(event)

    def _installed_names(self) -> dict[str, Any]:
        result = {}
        for star in self.shop.context.get_all_stars():
            name = str(getattr(star, "name", "") or "")
            if not name:
                continue
            result[name] = star
            module_path = str(getattr(star, "module_path", "") or "")
            if module_path:
                result.setdefault(module_path.rsplit(".", 1)[-1], star)
        return result


@dataclass
class MarketSearchTool(PluginShopTool):
    name: str = "plugin_market_search"
    description: str = (
        "在 AstrBot 插件市场按关键词搜索插件。返回插件 ID、名称、版本、简介和仓库地址。"
        "当用户想找某个功能的插件、或询问市场里有没有某类插件时使用。"
        "搜索后再用 plugin_market_install 安装；不要凭记忆编造插件名。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，可以是功能描述、插件名或作者名，多个词用空格分隔。",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回条数，默认 5，最大 15。",
                    "default": 5,
                },
            },
            "required": ["keyword"],
        }
    )

    async def run(self, event: AstrMessageEvent, keyword: str, limit: int = 5):
        denied = await self._deny(event)
        if denied:
            return denied
        try:
            entries = await load_market()
        except Exception as exc:
            return f"搜索失败：{exc}"
        results = search(entries, keyword, min(max(int(limit or 5), 1), 15))
        if not results:
            return f"插件市场里没有找到与「{keyword}」相关的插件。"
        installed = self._installed_names()
        lines = [f"找到 {len(results)} 个相关插件："]
        for market_id, entry in results:
            name = str(entry.get("name") or market_id)
            mark = "已安装" if name in installed else "未安装"
            lines.append(
                f"- {entry.get('display_name') or name}（ID: {market_id}，"
                f"版本 {entry.get('version') or '未知'}，{mark}）\n"
                f"  简介：{_short(entry.get('desc'), 120)}\n"
                f"  仓库：{entry.get('repo') or '无'}"
            )
        lines.append("需要安装时，先用 plugin_market_install 传入插件 ID 查看安装信息，并等待用户确认。")
        return "\n".join(lines)


@dataclass
class MarketInstallTool(PluginShopTool):
    name: str = "plugin_market_install"
    description: str = (
        "从 AstrBot 插件市场安装插件。必须先向用户说明插件用途、来源和风险，并获得用户明确同意后，"
        "才能把 confirm 设为 true。未确认时 confirm=false，只返回安装预览，不会安装任何东西。"
        "安装会下载并立即加载第三方代码，属于高风险操作。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "market_id": {
                    "type": "string",
                    "description": "插件市场 ID，来自 plugin_market_search 的结果，例如 author/astrbot_plugin_xxx。",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "是否为已获用户明确同意的实际安装。首次调用必须为 false。",
                    "default": False,
                },
            },
            "required": ["market_id"],
        }
    )

    async def run(self, event: AstrMessageEvent, market_id: str, confirm: bool = False):
        denied = await self._deny(event)
        if denied:
            return denied
        try:
            entries = await load_market()
        except Exception as exc:
            return f"读取插件市场失败：{exc}"
        key = str(market_id or "").strip()
        entry = entries.get(key)
        if entry is None:
            matches = search(entries, key, 1)
            if not matches:
                return f"插件市场中不存在「{key}」，请先用 plugin_market_search 搜索。"
            key, entry = matches[0]
        name = str(entry.get("name") or key)
        repo = str(entry.get("repo") or "").strip()
        if not repo:
            return f"插件「{name}」在市场中缺少仓库地址，无法安装。"
        preview = (
            f"插件：{entry.get('display_name') or name}（{name}）\n"
            f"版本：{entry.get('version') or '未知'}\n"
            f"作者：{entry.get('author') or '未知'}\n"
            f"来源：{repo}\n"
            f"简介：{_short(entry.get('desc'), 200)}"
        )
        if not confirm:
            return (
                preview
                + "\n\n尚未安装。请向用户说明以上信息并询问是否安装；用户明确同意后，"
                "再以 confirm=true 调用本工具。"
            )
        if name in self._installed_names():
            return f"插件「{name}」已安装。如需更新或启停，请使用 plugin_shop_manage。"
        star_manager = getattr(self.shop.context, "_star_manager", None)
        if star_manager is None:
            return "安装失败：无法访问插件管理器。"
        try:
            await asyncio.wait_for(
                star_manager.install_plugin(
                    repo,
                    download_url=str(entry.get("download_url") or ""),
                ),
                timeout=300,
            )
        except asyncio.TimeoutError:
            return f"安装「{name}」超时，请稍后在 WebUI 插件页确认状态。"
        except Exception as exc:
            return f"安装「{name}」失败：{exc}"
        star = self.shop.context.get_registered_star(name)
        turned_on = False
        if star is not None and not getattr(star, "activated", True):
            try:
                await star_manager.turn_on_plugin(name)
                turned_on = True
            except Exception as exc:
                logger.warning(f"[plugin_shop] 启用插件失败 {name}: {exc}")
        logger.info(f"[plugin_shop] 已安装市场插件 {name} ({key}) by {event.get_sender_id()}")
        return (
            preview
            + f"\n\n安装完成。{'已自动启用。' if turned_on else '已加载。'}"
            "如果插件需要额外配置或依赖，请在 WebUI 插件页检查。"
        )


@dataclass
class InstalledListTool(PluginShopTool):
    name: str = "plugin_shop_list"
    description: str = "列出当前已安装的 AstrBot 插件及其启用状态，可按关键词过滤。"
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "可选过滤关键词，匹配插件名或简介。",
                    "default": "",
                }
            },
        }
    )

    async def run(self, event: AstrMessageEvent, keyword: str = ""):
        denied = await self._deny(event)
        if denied:
            return denied
        token = str(keyword or "").strip().lower()
        lines = []
        for star in self.shop.context.get_all_stars():
            name = str(getattr(star, "name", "") or "")
            desc = str(getattr(star, "desc", "") or "")
            if token and token not in name.lower() and token not in desc.lower():
                continue
            state = "启用" if getattr(star, "activated", False) else "停用"
            lines.append(f"- {name}（{state}，v{getattr(star, 'version', '未知')}）：{_short(desc, 60)}")
        if not lines:
            return "没有匹配的已安装插件。"
        return f"已安装插件 {len(lines)} 个：\n" + "\n".join(sorted(lines))


@dataclass
class ManageTool(PluginShopTool):
    name: str = "plugin_shop_manage"
    description: str = (
        "启用、停用或卸载已安装的 AstrBot 插件。停用会立即中断该插件功能，卸载会删除插件文件。"
        "执行前必须获得用户明确同意；卸载时 confirm 必须为 true。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "插件名，例如 astrbot_plugin_xxx。",
                },
                "action": {
                    "type": "string",
                    "enum": ["enable", "disable", "uninstall"],
                    "description": "enable=启用，disable=停用，uninstall=卸载并删除文件。",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "是否为已获用户明确同意的实际执行，默认 false 只返回预览。",
                    "default": False,
                },
            },
            "required": ["plugin_name", "action"],
        }
    )

    async def run(
        self,
        event: AstrMessageEvent,
        plugin_name: str,
        action: str,
        confirm: bool = False,
    ):
        denied = await self._deny(event)
        if denied:
            return denied
        name = str(plugin_name or "").strip()
        act = str(action or "").strip().lower()
        if act not in {"enable", "disable", "uninstall"}:
            return "action 只能是 enable、disable 或 uninstall。"
        star = self.shop.context.get_registered_star(name)
        if star is None:
            return f"未找到插件「{name}」。"
        if name == "astrbot_plugin_plugin_shop" and act != "enable":
            return "不能停用或卸载当前正在使用的插件商店插件。"
        if act == "uninstall" and not self.shop._option("allow_uninstall", False):
            return "当前配置不允许卸载插件，只能启用、停用或安装。"
        if not confirm:
            return (
                f"待执行：{act} 插件「{name}」（v{getattr(star, 'version', '未知')}）。\n"
                "尚未执行。请向用户确认后，再用 confirm=true 调用。"
            )
        star_manager = getattr(self.shop.context, "_star_manager", None)
        if star_manager is None:
            return "操作失败：无法访问插件管理器。"
        try:
            if act == "enable":
                await star_manager.turn_on_plugin(name)
            elif act == "disable":
                await star_manager.turn_off_plugin(name)
            else:
                await star_manager.uninstall_plugin(name)
        except Exception as exc:
            return f"{act} 插件「{name}」失败：{exc}"
        logger.info(f"[plugin_shop] {act} 插件 {name} by {event.get_sender_id()}")
        return f"已对插件「{name}」执行 {act}。"
