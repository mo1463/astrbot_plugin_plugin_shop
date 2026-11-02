import json
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger

try:
    from astrbot.core.utils.astrbot_path import (
        get_astrbot_data_path,
        get_astrbot_plugin_data_path,
    )
except Exception:
    get_astrbot_data_path = None
    get_astrbot_plugin_data_path = None

PLUGIN_NAME = "astrbot_plugin_plugin_shop"

MARKET_URLS = (
    "https://api.soulter.top/astrbot/plugins",
    "https://github.com/AstrBotDevs/AstrBot_Plugins_Collection/raw/refs/heads/main/plugin_cache_original.json",
)
CACHE_TTL_SECONDS = 12 * 3600


class MarketDataError(Exception):
    pass


def _data_dir() -> Path:
    """返回 AstrBot 的 data 目录。"""
    if get_astrbot_data_path is not None:
        try:
            return Path(get_astrbot_data_path())
        except Exception:
            pass
    # 回退：插件位于 <data>/plugins/<plugin>/，向上两级即 <data>
    candidate = Path(__file__).resolve().parents[2]
    if candidate.name == "data":
        return candidate
    return Path.cwd() / "data"


def _plugin_data_dir() -> Path:
    """返回插件持久化数据目录 <data>/plugin_data/<plugin>/。"""
    base: Path | None = None
    if get_astrbot_plugin_data_path is not None:
        try:
            base = Path(get_astrbot_plugin_data_path())
        except Exception:
            base = None
    if base is None:
        base = _data_dir() / "plugin_data"
    path = base / PLUGIN_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.debug(f"[plugin_shop] 创建插件数据目录失败 {path}: {exc}")
    return path


def _own_cache_path() -> Path:
    return _plugin_data_dir() / "market_cache.json"



def _normalize_entries(raw: Any) -> dict[str, dict]:
    if isinstance(raw, dict):
        payload = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        if isinstance(payload, dict):
            return {
                str(key): value
                for key, value in payload.items()
                if isinstance(value, dict) and not str(key).startswith("$")
            }
    if isinstance(raw, list):
        result = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = f"{item.get('author', '')}/{item.get('name', '')}".strip("/")
            if key:
                result[key] = item
        return result
    return {}


def _load_local_cache() -> dict[str, dict]:
    candidates = [_own_cache_path(), _data_dir() / "plugins.json"]
    best: dict[str, dict] = {}
    best_time = 0.0
    for path in candidates:
        try:
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug(f"[plugin_shop] 读取市场缓存失败 {path}: {exc}")
            continue
        entries = _normalize_entries(raw)
        if not entries:
            continue
        try:
            stamp = float(raw.get("timestamp") or raw.get("fetched_at") or 0)
        except Exception:
            stamp = 0.0
        stamp = stamp or path.stat().st_mtime
        if stamp >= best_time:
            best, best_time = entries, stamp
    return best


async def _fetch_remote() -> dict[str, dict]:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        for url in MARKET_URLS:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        continue
                    data = await response.json(content_type=None)
            except Exception as exc:
                logger.debug(f"[plugin_shop] 拉取市场数据失败 {url}: {exc}")
                continue
            entries = _normalize_entries(data)
            if entries:
                try:
                    payload = {
                        "fetched_at": time.time(),
                        "data": entries,
                    }
                    _own_cache_path().write_text(
                        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                    )
                except Exception as exc:
                    logger.debug(f"[plugin_shop] 写入市场缓存失败: {exc}")
                return entries
    raise MarketDataError("插件市场数据获取失败，且没有可用缓存")


async def load_market(force_refresh: bool = False) -> dict[str, dict]:
    if not force_refresh:
        entries = _load_local_cache()
        if entries:
            cache_path = _own_cache_path()
            if cache_path.is_file():
                age = time.time() - cache_path.stat().st_mtime
                if age < CACHE_TTL_SECONDS:
                    return entries
            else:
                return entries
    try:
        return await _fetch_remote()
    except MarketDataError:
        entries = _load_local_cache()
        if entries:
            return entries
        raise


def _haystack(market_id: str, entry: dict) -> str:
    parts = [
        market_id,
        str(entry.get("name") or ""),
        str(entry.get("display_name") or ""),
        str(entry.get("author") or ""),
        str(entry.get("desc") or ""),
        str(entry.get("category") or ""),
    ]
    tags = entry.get("tags")
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)
    return " ".join(parts).lower()


def search(entries: dict[str, dict], keyword: str, limit: int = 5) -> list[tuple[str, dict]]:
    tokens = [token for token in str(keyword or "").lower().split() if token]
    scored: list[tuple[int, float, str, dict]] = []
    for market_id, entry in entries.items():
        haystack = _haystack(market_id, entry)
        if tokens and not all(token in haystack for token in tokens):
            continue
        score = 0
        name = str(entry.get("name") or "").lower()
        display = str(entry.get("display_name") or "").lower()
        for token in tokens:
            if token in name:
                score += 5
            if token in display:
                score += 4
            if token in haystack:
                score += 1
        try:
            updated = float(entry.get("updated_at") or 0)
        except Exception:
            updated = 0.0
        scored.append((score, updated, market_id, entry))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [(market_id, entry) for _, _, market_id, entry in scored[: max(1, limit)]]
