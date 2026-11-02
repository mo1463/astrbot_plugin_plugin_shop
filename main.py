from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .tools import InstalledListTool, ManageTool, MarketInstallTool, MarketSearchTool


@register(
    "astrbot_plugin_plugin_shop",
    "mo1463",
    "让机器人搜索插件市场、安装和启停插件（管理员限定，默认需要用户确认）",
    "1.0.0",
)
class PluginShop(Star):
    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context, config)
        self.config = config or {}
        self.tools: list = []
        self._register_tools()

    def _option(self, key: str, default: Any) -> Any:
        value = self.config.get(key, default)
        return default if value is None else value

    def _allowed_users(self) -> set[str]:
        raw = self._option("extra_allowed_users", [])
        if isinstance(raw, str):
            raw = [item.strip() for item in raw.replace("，", ",").split(",")]
        if not isinstance(raw, list):
            return set()
        return {str(item).strip() for item in raw if str(item).strip()}

    async def check_permission(self, event: AstrMessageEvent) -> str | None:
        if not self._option("enable", True):
            return "插件商店未启用。"
        if not self._option("admin_only", True):
            return None
        try:
            if event.is_admin():
                return None
        except Exception:
            pass
        if str(event.get_sender_id()) in self._allowed_users():
            return None
        return "插件管理仅限机器人管理员操作。"

    def _register_tools(self) -> None:
        try:
            self.tools = [
                MarketSearchTool(shop=self),
                MarketInstallTool(shop=self),
                InstalledListTool(shop=self),
                ManageTool(shop=self),
            ]
            self.context.add_llm_tools(*self.tools)
            logger.info(
                "[plugin_shop] 已注册工具：%s",
                "、".join(tool.name for tool in self.tools),
            )
        except Exception as exc:
            logger.error(f"[plugin_shop] 注册 LLM 工具失败: {exc}", exc_info=True)

    @filter.command("插件市场")
    async def market_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "插件市场已接入。直接告诉我要找什么功能的插件，我会先搜索并把信息给你，"
            "得到你确认后才会安装；也可以让我列出、启用、停用或卸载已装插件。"
        )
