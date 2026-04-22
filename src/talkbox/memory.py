import hashlib
import logging
from datetime import datetime
from pathlib import Path

from mempalace.config import MempalaceConfig
from mempalace.palace import get_collection
from mempalace.searcher import search_memories

logger = logging.getLogger("talkbox.memory")


class Memory:
    def __init__(self, palace_path: str | None = None, wing: str = "talkbox"):
        cfg = MempalaceConfig()
        self.palace_path = palace_path or cfg.palace_path
        self.wing = wing
        Path(self.palace_path).mkdir(parents=True, exist_ok=True)

    def search(self, query: str, n_results: int = 3) -> list[dict]:
        try:
            result = search_memories(
                query=query,
                palace_path=self.palace_path,
                wing=self.wing,
                n_results=n_results,
            )
            if "error" in result:
                logger.debug("记忆搜索无结果: %s", result["error"])
                return []
            hits = result.get("results", [])
            return [h for h in hits if h.get("distance", 2) < 1.5]
        except Exception as e:
            logger.debug("记忆搜索失败: %s", e)
            return []

    def store(self, user_msg: str, assistant_msg: str) -> None:
        content = f"> {user_msg}\n{assistant_msg}"
        if len(content.strip()) < 30:
            return
        try:
            col = get_collection(self.palace_path)
            drawer_id = f"drawer_{self.wing}_chat_{hashlib.sha256(content.encode()).hexdigest()[:24]}"
            col.upsert(
                documents=[content],
                ids=[drawer_id],
                metadatas=[{
                    "wing": self.wing,
                    "room": "chat",
                    "source_file": "talkbox_live",
                    "chunk_index": 0,
                    "added_by": "talkbox",
                    "filed_at": datetime.now().isoformat(),
                    "ingest_mode": "live",
                }],
            )
            logger.debug("记忆已存储: %s...", user_msg[:50])
        except Exception as e:
            logger.warning("记忆存储失败: %s", e)

    def format_context(self, hits: list[dict]) -> str:
        if not hits:
            return ""
        parts = [h.get("text", "").strip() for h in hits]
        joined = "\n---\n".join(parts)
        return f"# 相关记忆\n\n以下是与当前话题相关的历史对话记忆：\n\n{joined}"
