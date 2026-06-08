from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union
from uuid import uuid4

from config import PROJECT_ROOT
from core.workflow_schema import Workflow


WORKFLOW_TEMPLATE_DIR = PROJECT_ROOT / "examples" / "workflows"
PROMPT_DIR = PROJECT_ROOT / "prompts"
STEP_DESCRIPTIONS = {
    "read_document": "读取文件内容",
    "chunk_document": "整理文件片段",
    "retrieve_chunks": "查找相关内容",
    "answer_with_sources": "根据文件回答并附上依据",
    "read_table": "读取表格",
    "profile_table": "概览表格结构",
    "filter_table": "筛选符合条件的数据",
    "aggregate_table": "汇总关键指标",
    "sort_table": "整理结果顺序",
    "render_chart": "准备图表",
    "generate_text": "生成文字结果",
}


class Scenario(str, Enum):
    SUMMARY = "summary"
    DOCUMENT_QA = "document_qa"
    DATA_ANALYSIS = "data_analysis"
    FAQ_CUSTOMER_SERVICE = "faq_customer_service"
    ONE_TIME_REPORT = "one_time_report"


@dataclass(frozen=True)
class Clarification:
    scenario: Scenario
    needs_more_info: bool
    questions: Tuple[str, ...] = ()
    unsupported: bool = False
    message: Optional[str] = None


@dataclass(frozen=True)
class PlannedWorkflow:
    scenario: Scenario
    workflow: Workflow
    plan_text: str
    limitation_message: Optional[str] = None


class Planner:
    """Rule-based MVP planner that composes registered workflow templates."""

    def clarify(
        self,
        user_request: str,
        uploaded_files: Sequence[Union[str, Path]] = (),
    ) -> Clarification:
        scenario = self._recognize_scenario(user_request, uploaded_files)
        if scenario == Scenario.ONE_TIME_REPORT:
            return Clarification(
                scenario=scenario,
                needs_more_info=True,
                questions=(
                    "当前版本暂不支持后台定时运行。是否改为立即生成一次报告？",
                ),
                unsupported=True,
                message=(
                    "当前版本可以立即生成一次报告，但暂不支持在后台按周自动运行。"
                ),
            )

        questions: List[str] = []
        if not uploaded_files:
            questions.append("请先上传需要处理的文件。")
        if scenario in {Scenario.DOCUMENT_QA, Scenario.FAQ_CUSTOMER_SERVICE}:
            if not self._looks_like_question(user_request):
                questions.append("请补充你希望基于文件回答的具体问题。")
        return Clarification(
            scenario=scenario,
            needs_more_info=bool(questions),
            questions=tuple(questions[:3]),
            message=self._render_clarification(questions) if questions else None,
        )

    def create_workflow(
        self,
        user_request: str,
        uploaded_files: Sequence[Union[str, Path]] = (),
        *,
        scenario: Optional[Scenario] = None,
        workflow_id: Optional[str] = None,
        version: int = 1,
    ) -> PlannedWorkflow:
        resolved_scenario = scenario or self._recognize_scenario(
            user_request, uploaded_files
        )
        workflow = self._load_template(resolved_scenario)
        workflow_payload = workflow.model_dump(mode="json")
        workflow_payload["id"] = workflow_id or f"workflow_{uuid4().hex}"
        workflow_payload["version"] = version
        planned_workflow = Workflow.model_validate(workflow_payload)
        limitation_message = (
            "当前版本可以立即生成一次报告，但暂不支持在后台按周自动运行。"
            if resolved_scenario == Scenario.ONE_TIME_REPORT
            else None
        )
        return PlannedWorkflow(
            scenario=resolved_scenario,
            workflow=planned_workflow,
            plan_text=self._render_plan(planned_workflow, resolved_scenario),
            limitation_message=limitation_message,
        )

    def revise_workflow(
        self,
        workflow: Workflow,
        feedback: str,
    ) -> PlannedWorkflow:
        payload = workflow.model_dump(mode="json")
        payload["version"] = workflow.version + 1
        self._apply_text_generation_feedback(payload, feedback)
        revised_workflow = Workflow.model_validate(payload)
        scenario = self._scenario_from_workflow(workflow)
        steps = self._describe_steps(revised_workflow)
        prompt = self._load_prompt("revise.md")
        plan_text = prompt.format(
            version=revised_workflow.version,
            feedback=feedback,
            steps=steps,
        ).strip()
        return PlannedWorkflow(
            scenario=scenario,
            workflow=revised_workflow,
            plan_text=plan_text,
        )

    def _recognize_scenario(
        self,
        user_request: str,
        uploaded_files: Sequence[Union[str, Path]],
    ) -> Scenario:
        normalized_request = user_request.lower()
        file_names = " ".join(Path(file_path).name.lower() for file_path in uploaded_files)
        suffixes = {Path(file_path).suffix.lower() for file_path in uploaded_files}
        if any(
            marker in normalized_request
            for marker in (
                "每周",
                "定时",
                "定期",
                "weekly",
                "every monday",
                "schedule",
                "cron",
                "timer",
                "recurrence",
            )
        ):
            return Scenario.ONE_TIME_REPORT
        if suffixes.intersection({".csv", ".xlsx"}) or any(
            marker in normalized_request
            for marker in ("分析", "统计", "销售", "analyze", "analysis", "sales")
        ):
            return Scenario.DATA_ANALYSIS
        if "faq" in file_names or any(
            marker in normalized_request
            for marker in ("faq", "客服", "customer service")
        ):
            return Scenario.FAQ_CUSTOMER_SERVICE
        if self._looks_like_question(user_request):
            return Scenario.DOCUMENT_QA
        return Scenario.SUMMARY

    def _looks_like_question(self, user_request: str) -> bool:
        normalized_request = user_request.lower()
        return "?" in user_request or "？" in user_request or any(
            marker in normalized_request
            for marker in (
                "什么",
                "如何",
                "是否",
                "吗",
                "退款",
                "what",
                "how",
                "can ",
                "does ",
                "is ",
            )
        )

    def _load_template(self, scenario: Scenario) -> Workflow:
        template_path = WORKFLOW_TEMPLATE_DIR / f"{scenario.value}.json"
        try:
            return Workflow.model_validate_json(template_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"Workflow template cannot be read: {scenario.value}") from exc

    def _render_plan(self, workflow: Workflow, scenario: Scenario) -> str:
        prompt = self._load_prompt("plan.md")
        steps = self._describe_steps(workflow)
        return prompt.format(
            scenario=scenario.value,
            steps=steps,
            source_policy=workflow.source_policy.value,
        ).strip()

    def _describe_steps(self, workflow: Workflow) -> str:
        return " -> ".join(
            STEP_DESCRIPTIONS.get(step.step_type, step.title or step.step_type)
            for step in workflow.steps
        )

    def _render_clarification(self, questions: Sequence[str]) -> str:
        prompt = self._load_prompt("clarify.md")
        return prompt.format(
            questions="\n".join(f"- {question}" for question in questions)
        ).strip()

    def _load_prompt(self, file_name: str) -> str:
        try:
            return (PROMPT_DIR / file_name).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Prompt template cannot be read: {file_name}") from exc

    def _scenario_from_workflow(self, workflow: Workflow) -> Scenario:
        step_types = [step.step_type for step in workflow.steps]
        if step_types == [
            "read_document",
            "chunk_document",
            "retrieve_chunks",
            "answer_with_sources",
        ]:
            return Scenario.DOCUMENT_QA
        if "read_table" in step_types:
            return Scenario.DATA_ANALYSIS
        if any(
            step.params.get("task") == "report"
            for step in workflow.steps
            if step.step_type == "generate_text"
        ):
            return Scenario.ONE_TIME_REPORT
        return Scenario.SUMMARY

    def _apply_text_generation_feedback(
        self,
        payload: dict,
        feedback: str,
    ) -> None:
        max_length_match = re.search(
            r"(\d+)\s*(?:字|characters?)",
            feedback,
            flags=re.IGNORECASE,
        )
        bullet_count_match = re.search(
            r"(\d+)\s*(?:个\s*)?(?:要点|key\s*points?)",
            feedback,
            flags=re.IGNORECASE,
        )
        for step in payload["steps"]:
            if step["step_type"] != "generate_text":
                continue
            if max_length_match:
                step["params"]["max_length"] = int(max_length_match.group(1))
            if bullet_count_match:
                step["params"]["bullet_count"] = int(bullet_count_match.group(1))
