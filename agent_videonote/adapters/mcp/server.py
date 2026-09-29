from __future__ import annotations

from typing import Any

from agent_videonote.adapters.mcp.facade import McpToolFacade
from agent_videonote.application.factory import build_runtime_from_environment


def create_server():
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is not installed. Install Agent-VideoNote with the 'mcp' extra."
        ) from exc

    container = build_runtime_from_environment()
    facade = McpToolFacade(container.application)
    mcp = MCPServer("Agent-VideoNote")

    @mcp.tool()
    def health() -> dict[str, Any]:
        """轻量运行体检：检查媒体工具和 Provider 配置，不加载模型。"""
        return facade.health()

    @mcp.tool()
    def asr_setup_plan(search_dirs: list[str] | None = None) -> dict[str, Any]:
        """只读探测本机 ASR 环境并给出安装计划；不安装包或下载模型。"""
        return facade.asr_setup_plan(search_dirs=search_dirs)

    @mcp.tool()
    def asr_models(
        role: str | None = None,
        priority: str = "balanced",
        integrated_only: bool = False,
        limit: int = 5,
        detail: str = "compact",
    ) -> dict[str, Any]:
        """按需查看 ASR 模型候选；默认紧凑返回，不会自动下载安装。"""
        return facade.asr_models(
            role=role,
            priority=priority,
            integrated_only=integrated_only,
            limit=limit,
            detail=detail,
        )

    @mcp.tool()
    def prepare(source: str) -> dict[str, Any]:
        """创建或恢复本地视频任务，并读取紧凑媒体信息。"""
        return facade.prepare(source)

    @mcp.tool()
    def set_course_context(
        course_id: str,
        title_terms: list[str] | None = None,
        glossary_terms: list[str] | None = None,
        free_text: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """保存课程级术语与识别上下文，后续任务只需引用 course_id。"""
        return facade.set_course_context(
            course_id,
            title_terms=title_terms,
            glossary_terms=glossary_terms,
            free_text=free_text,
            language=language,
        )

    @mcp.tool()
    def get_course_context(course_id: str) -> dict[str, Any]:
        """读取已保存的课程识别上下文。"""
        return facade.get_course_context(course_id)

    @mcp.tool()
    def ingest_srt(
        task_id: str,
        srt_path: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """将可靠 SRT 转为统一时间轴；只返回摘要，不返回全文。"""
        return facade.ingest_srt(task_id, srt_path, language)

    @mcp.tool()
    def transcribe(
        task_id: str,
        course_id: str | None = None,
        language: str | None = None,
        hotwords: list[str] | None = None,
        context_text: str | None = None,
    ) -> dict[str, Any]:
        """调用 primary ASR；只返回结果摘要。优先使用持久化 course_id。"""
        return facade.transcribe(
            task_id,
            course_id=course_id,
            language=language,
            hotwords=hotwords,
            context_text=context_text,
        )

    @mcp.tool()
    def get_transcript(
        task_id: str,
        start_segment: int = 1,
        end_segment: int = 80,
        include_words: bool = False,
    ) -> dict[str, Any]:
        """按连续段范围读取转写；单次最多 200 段，避免把全文塞入上下文。"""
        return facade.get_transcript(
            task_id,
            start_segment=start_segment,
            end_segment=end_segment,
            include_words=include_words,
        )

    @mcp.tool()
    def review(
        task_id: str,
        start: float,
        end: float,
        speed: float = 1.0,
        course_id: str | None = None,
        language: str | None = None,
        hotwords: list[str] | None = None,
        context_text: str | None = None,
    ) -> dict[str, Any]:
        """对指定时间窗做独立局部复核；相同窗口复用已有结果。"""
        return facade.review(
            task_id,
            start=start,
            end=end,
            speed=speed,
            course_id=course_id,
            language=language,
            hotwords=hotwords,
            context_text=context_text,
        )

    @mcp.tool()
    def task(task_id: str) -> dict[str, Any]:
        """读取任务当前阶段、已完成阶段、产物和未解决项数量。"""
        return facade.task(task_id)

    @mcp.tool()
    def complete_visual(
        task_id: str,
        evidence: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """在视觉工作由外部 Agent 完成并有证据后推进到交付阶段。"""
        return facade.complete_visual(task_id, evidence or {})

    @mcp.tool()
    def validate_delivery(
        task_id: str,
        deliverables_dir: str,
    ) -> dict[str, Any]:
        """检查最终正文、图片引用、孤图和多余文件；通过后标记 DONE。"""
        return facade.validate_delivery(task_id, deliverables_dir)

    return mcp, container


def main() -> None:
    mcp, container = create_server()
    try:
        mcp.run()
    finally:
        container.asr_registry.close_all()


if __name__ == "__main__":
    main()
