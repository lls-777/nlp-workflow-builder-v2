from __future__ import annotations

from pathlib import Path

import pytest

from config import EXAMPLES_DIR
from core.planner import Planner, Scenario


@pytest.fixture
def planner() -> Planner:
    return Planner()


@pytest.mark.parametrize(
    ("user_request", "files", "expected_scenario"),
    [
        ("请帮我整理这份文档", ["sample.txt"], Scenario.SUMMARY),
        ("What do users value?", ["sample.txt"], Scenario.DOCUMENT_QA),
        ("FAQ: can a member request a refund?", ["sample_faq.md"], Scenario.FAQ_CUSTOMER_SERVICE),
        ("请分析销售数据", ["sample_sales.csv"], Scenario.DATA_ANALYSIS),
        ("请每周一生成报告", ["sample.txt"], Scenario.ONE_TIME_REPORT),
    ],
)
def test_planner_recognizes_five_acceptance_scenarios(
    planner: Planner,
    user_request: str,
    files: list,
    expected_scenario: Scenario,
) -> None:
    clarification = planner.clarify(
        user_request,
        [EXAMPLES_DIR / file_name for file_name in files],
    )

    assert clarification.scenario == expected_scenario


def test_planner_weekly_report_request_is_downgraded_without_schedule_fields(
    planner: Planner,
) -> None:
    request = "请每周一自动生成销售报告"
    clarification = planner.clarify(request, [EXAMPLES_DIR / "sample.txt"])

    assert clarification.unsupported is True
    assert "立即生成一次报告" in clarification.questions[0]

    plan = planner.create_workflow(
        request,
        [EXAMPLES_DIR / "sample.txt"],
        scenario=Scenario.ONE_TIME_REPORT,
    )
    serialized_workflow = plan.workflow.model_dump_json().lower()
    for forbidden_term in ("schedule", "cron", "timer", "recurrence", "定时"):
        assert forbidden_term not in serialized_workflow
    assert [step.step_type for step in plan.workflow.steps] == [
        "read_document",
        "generate_text",
    ]


def test_planner_feedback_creates_next_version(planner: Planner) -> None:
    plan = planner.create_workflow(
        "请总结这份文件",
        [EXAMPLES_DIR / "sample.txt"],
        scenario=Scenario.SUMMARY,
    )

    revised = planner.revise_workflow(plan.workflow, "缩短到 80 字，保留 3 个要点")

    assert revised.workflow.id == plan.workflow.id
    assert revised.workflow.version == 2
    generate_step = revised.workflow.steps[-1]
    assert generate_step.params["max_length"] == 80
    assert generate_step.params["bullet_count"] == 3
