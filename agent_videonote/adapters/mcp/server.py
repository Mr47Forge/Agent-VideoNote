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
        """PROCESS 首个调用：轻量体检，并返回跨 Agent 的 runtime_protocol；不加载模型。"""
        return facade.health()

    @mcp.tool()
    def discover_visuals(task_id: str, budget_seconds: float = 600.0,
                         config: dict[str, Any] | None = None) -> dict[str, Any]:
        """增量扫描真实视频画面；测试阶段默认一次推进 600 秒源视频并复用断点。"""
        return facade.discover_visuals(task_id, budget_seconds, config)

    @mcp.tool()
    def get_visual_candidates(task_id: str, start: int = 0,
                              limit: int = 20) -> dict[str, Any]:
        """分页读取视觉候选与原视频时间戳，单次最多 50 条。"""
        return facade.get_visual_candidates(task_id, start, limit)

    @mcp.tool()
    def clean_visual_candidates(
        task_id: str,
        start: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        """批量处理一页视觉候选，优先真实源帧；返回紧凑统计而不是逐张大结果。"""
        return facade.clean_visual_candidates(task_id, start=start, limit=limit)

    @mcp.tool()
    def clean_visual_candidate(task_id: str, candidate_id: str) -> dict[str, Any]:
        """单张调试入口：寻找同状态的干净真实源帧；日常测试优先用批量工具。"""
        return facade.clean_visual_candidate(task_id, candidate_id)

    @mcp.tool()
    def repair_visual_candidate(
        task_id: str,
        candidate_id: str,
        provider: str,
        mask_path: str,
        window_seconds: float = 3.0,
        interval: float = 1.0,
    ) -> dict[str, Any]:
        """使用明确 mask 调指定修复 Provider；不会自动删除任何文字。"""
        return facade.repair_visual_candidate(
            task_id,
            candidate_id,
            provider,
            mask_path,
            window_seconds,
            interval,
        )

    @mcp.tool()
    def release_asr_role(role: str) -> dict[str, Any]:
        """结束一个 ASR 角色的驻留批次；不会删除模型文件或 Provider 配置。"""
        return facade.release_asr_role(role)

    @mcp.tool()
    def asr_setup_plan(search_dirs: list[str] | None = None) -> dict[str, Any]:
        """只读探测本机 ASR 环境并给出安装计划；不安装包或下载模型。"""
        return facade.asr_setup_plan(search_dirs=search_dirs)

    @mcp.tool()
    def visual_setup(apply: bool = False) -> dict[str, Any]:
        """安装或检查视觉清理运行体；只使用当前 Agent-VideoNote Python 环境，不创建第二个 venv。"""
        return facade.visual_setup(apply=apply)

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
        """创建/恢复任务；返回当前 context_key。新会话或 key 变化后调用 task_context。"""
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
        """读取紧凑任务状态；返回 context_tool/context_key，按其提示加载当前规则。"""
        return facade.task(task_id)

    @mcp.tool()
    def task_context(task_id: str) -> dict[str, Any]:
        """进入/恢复任务时读取一次：返回紧凑任务状态、全局规则和当前唯一阶段胶囊；不依赖宿主读取仓库文件。"""
        return facade.task_context(task_id)

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
