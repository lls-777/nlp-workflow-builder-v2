from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from pydantic import ValidationError

from config import (
    ALLOWED_FILE_ROOTS,
    MAX_SINGLE_FILE_BYTES,
    MAX_TOTAL_FILE_BYTES,
    MAX_UPLOAD_FILES,
    MAX_WORKFLOW_STEPS,
    SUPPORTED_UPLOAD_EXTENSIONS,
)
from core.logging_utils import log_step_status, log_workflow_status
from core.step_registry import STEP_REGISTRY, StepDefinition, StepRegistry
from core.workflow_schema import (
    BindingSource,
    DisplayType,
    ExecutionContext,
    SourcePolicy,
    Step,
    StepOutput,
    StepRunResult,
    StepStatus,
    ValueType,
    Workflow,
    WorkflowResult,
    WorkflowStatus,
)


Handler = Callable[[Dict[str, Any], Dict[str, Any], ExecutionContext], Dict[str, Any]]

DISPLAY_VALUE_TYPES = {
    DisplayType.TEXT: ValueType.TEXT,
    DisplayType.TABLE: ValueType.TABLE,
    DisplayType.CHART: ValueType.CHART,
    DisplayType.CITATIONS: ValueType.CITATIONS,
    DisplayType.ARTIFACT: ValueType.ARTIFACT,
}


class WorkflowValidationError(ValueError):
    """Raised when a workflow cannot be safely executed."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _find_duplicates(values: Iterable[str]) -> List[str]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _is_within_allowed_root(path: Path, allowed_roots: Sequence[Path]) -> bool:
    resolved_path = path.resolve()
    for root in allowed_roots:
        resolved_root = root.resolve()
        try:
            resolved_path.relative_to(resolved_root)
            return True
        except ValueError:
            continue
    return False


def _validate_file_path(path_value: Any, allowed_roots: Sequence[Path]) -> Path:
    if not isinstance(path_value, (str, Path)):
        raise WorkflowValidationError("Uploaded file path must be a string or Path")

    resolved_path = Path(path_value).resolve()
    if not _is_within_allowed_root(resolved_path, allowed_roots):
        raise WorkflowValidationError(
            f"File path is outside allowed upload roots: {resolved_path}"
        )
    if not resolved_path.is_file():
        raise WorkflowValidationError(f"Uploaded file does not exist: {resolved_path}")
    if resolved_path.suffix.lower() not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise WorkflowValidationError(
            f"Unsupported uploaded file format: {resolved_path.suffix or '<none>'}"
        )
    if resolved_path.stat().st_size > MAX_SINGLE_FILE_BYTES:
        raise WorkflowValidationError(
            f"Uploaded file exceeds {MAX_SINGLE_FILE_BYTES} byte limit: {resolved_path}"
        )
    return resolved_path


def _validate_runtime_inputs(
    workflow: Workflow,
    context: ExecutionContext,
    allowed_roots: Sequence[Path],
) -> None:
    declared_inputs = {item.name: item for item in workflow.workflow_inputs}
    unexpected_inputs = sorted(set(context.workflow_inputs) - set(declared_inputs))
    if unexpected_inputs:
        raise WorkflowValidationError(
            f"Execution context contains undeclared inputs: {unexpected_inputs}"
        )

    total_file_bytes = 0
    total_file_count = 0
    for name, definition in declared_inputs.items():
        if definition.required and name not in context.workflow_inputs:
            raise WorkflowValidationError(f"Required workflow input is missing: {name}")
        if name not in context.workflow_inputs:
            continue

        value = context.workflow_inputs[name]
        if definition.value_type == ValueType.TEXT:
            if not isinstance(value, str):
                raise WorkflowValidationError(
                    f"Workflow input '{name}' must contain text"
                )
            continue

        if definition.value_type == ValueType.FILE:
            paths = [_validate_file_path(value, allowed_roots)]
        elif definition.value_type == ValueType.FILES:
            if isinstance(value, (str, bytes, Path)) or not isinstance(value, Sequence):
                raise WorkflowValidationError(
                    f"Workflow input '{name}' must contain a list of files"
                )
            paths = [_validate_file_path(item, allowed_roots) for item in value]
        else:
            continue

        total_file_count += len(paths)
        total_file_bytes += sum(path.stat().st_size for path in paths)

    if total_file_count > MAX_UPLOAD_FILES:
        raise WorkflowValidationError(
            f"Workflow contains {total_file_count} files; limit is {MAX_UPLOAD_FILES}"
        )
    if total_file_bytes > MAX_TOTAL_FILE_BYTES:
        raise WorkflowValidationError(
            "Workflow uploaded files exceed "
            f"{MAX_TOTAL_FILE_BYTES} total byte limit"
        )


def _definition_for_step(step: Step, registry: StepRegistry) -> StepDefinition:
    definition = registry.get(step.step_type)
    if definition is None:
        raise WorkflowValidationError(f"Unregistered step_type: {step.step_type}")
    if not definition.enabled:
        raise WorkflowValidationError(f"Disabled step_type: {step.step_type}")
    return definition


def validate_workflow(
    workflow: Workflow,
    context: Optional[ExecutionContext] = None,
    *,
    registry: StepRegistry = STEP_REGISTRY,
    allowed_file_roots: Sequence[Path] = ALLOWED_FILE_ROOTS,
) -> WorkflowStatus:
    if len(workflow.steps) > MAX_WORKFLOW_STEPS:
        raise WorkflowValidationError(
            f"Workflow contains {len(workflow.steps)} steps; "
            f"limit is {MAX_WORKFLOW_STEPS}"
        )

    duplicate_input_names = _find_duplicates(
        workflow_input.name for workflow_input in workflow.workflow_inputs
    )
    if duplicate_input_names:
        raise WorkflowValidationError(
            f"Duplicate workflow input names: {duplicate_input_names}"
        )

    duplicate_step_ids = _find_duplicates(step.id for step in workflow.steps)
    if duplicate_step_ids:
        raise WorkflowValidationError(f"Duplicate step ids: {duplicate_step_ids}")

    workflow_inputs = {
        workflow_input.name: workflow_input for workflow_input in workflow.workflow_inputs
    }
    step_positions = {step.id: index for index, step in enumerate(workflow.steps)}
    definitions: Dict[str, StepDefinition] = {}

    for index, step in enumerate(workflow.steps):
        definition = _definition_for_step(step, registry)
        definitions[step.id] = definition
        if (
            definition.requires_network
            and workflow.source_policy
            in {
                SourcePolicy.UPLOADED_FILES_ONLY,
                SourcePolicy.USER_PROVIDED_ONLY,
            }
        ):
            raise WorkflowValidationError(
                f"Offline source policy forbids network step: {step.step_type}"
            )

        try:
            definition.params_model.model_validate(step.params)
        except ValidationError as exc:
            raise WorkflowValidationError(
                f"Invalid params for step '{step.id}': {exc}"
            ) from exc

        duplicate_port_names = _find_duplicates(item.name for item in step.inputs)
        if duplicate_port_names:
            raise WorkflowValidationError(
                f"Step '{step.id}' has duplicate input ports: {duplicate_port_names}"
            )

        provided_ports = {item.name: item for item in step.inputs}
        undeclared_ports = sorted(set(provided_ports) - set(definition.input_ports))
        if undeclared_ports:
            raise WorkflowValidationError(
                f"Step '{step.id}' uses undeclared input ports: {undeclared_ports}"
            )

        missing_ports = sorted(
            name
            for name, port in definition.input_ports.items()
            if port.required and name not in provided_ports
        )
        if missing_ports:
            raise WorkflowValidationError(
                f"Step '{step.id}' is missing required input ports: {missing_ports}"
            )

        for port_name, step_input in provided_ports.items():
            port = definition.input_ports[port_name]
            if not port.allow_multiple_bindings and len(step_input.bindings) > 1:
                raise WorkflowValidationError(
                    f"Step '{step.id}' input '{port_name}' accepts only one binding"
                )

            for binding in step_input.bindings:
                if binding.source == BindingSource.WORKFLOW_INPUT:
                    assert binding.input_name is not None
                    if binding.input_name not in workflow_inputs:
                        raise WorkflowValidationError(
                            f"Step '{step.id}' references unknown workflow input: "
                            f"{binding.input_name}"
                        )
                    bound_type = workflow_inputs[binding.input_name].value_type
                else:
                    assert binding.step_id is not None
                    assert binding.output_name is not None
                    if binding.step_id not in step_positions:
                        raise WorkflowValidationError(
                            f"Step '{step.id}' references unknown step: {binding.step_id}"
                        )
                    if step_positions[binding.step_id] >= index:
                        raise WorkflowValidationError(
                            f"Step '{step.id}' must reference a previous step, "
                            f"not '{binding.step_id}'"
                        )
                    previous_definition = definitions[binding.step_id]
                    if binding.output_name not in previous_definition.output_ports:
                        raise WorkflowValidationError(
                            f"Step '{step.id}' references unknown output "
                            f"'{binding.output_name}' from step '{binding.step_id}'"
                        )
                    bound_type = previous_definition.output_ports[binding.output_name]

                if bound_type not in port.allowed_value_types:
                    allowed = sorted(item.value for item in port.allowed_value_types)
                    raise WorkflowValidationError(
                        f"Step '{step.id}' input '{port_name}' expects {allowed}, "
                        f"got '{bound_type.value}'"
                    )

    for result_binding in workflow.result_bindings:
        if result_binding.step_id not in definitions:
            raise WorkflowValidationError(
                "Result binding references unknown step: "
                f"{result_binding.step_id}"
            )
        output_ports = definitions[result_binding.step_id].output_ports
        if result_binding.output_name not in output_ports:
            raise WorkflowValidationError(
                "Result binding references unknown output "
                f"'{result_binding.output_name}' from step "
                f"'{result_binding.step_id}'"
            )
        actual_type = output_ports[result_binding.output_name]
        expected_type = DISPLAY_VALUE_TYPES[result_binding.display_type]
        if actual_type != expected_type:
            raise WorkflowValidationError(
                f"Result binding display_type '{result_binding.display_type.value}' "
                f"does not match output type '{actual_type.value}'"
            )

    if context is not None:
        _validate_runtime_inputs(workflow, context, allowed_file_roots)

    return WorkflowStatus.VALIDATED


def _resolve_inputs(step: Step, context: ExecutionContext) -> Dict[str, Any]:
    resolved_inputs: Dict[str, Any] = {}
    for step_input in step.inputs:
        values: List[Any] = []
        for binding in step_input.bindings:
            if binding.source == BindingSource.WORKFLOW_INPUT:
                assert binding.input_name is not None
                values.append(context.workflow_inputs[binding.input_name])
            else:
                assert binding.step_id is not None
                assert binding.output_name is not None
                values.append(context.step_outputs[binding.step_id][binding.output_name])
        resolved_inputs[step_input.name] = values[0] if len(values) == 1 else values
    return resolved_inputs


def _preview(value: Any, limit: int = 240) -> str:
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _build_step_outputs(
    definition: StepDefinition, raw_outputs: Mapping[str, Any]
) -> List[StepOutput]:
    expected_names = set(definition.output_ports)
    actual_names = set(raw_outputs)
    if expected_names != actual_names:
        raise RuntimeError(
            f"Handler '{definition.handler_name}' returned outputs "
            f"{sorted(actual_names)}; expected {sorted(expected_names)}"
        )
    return [
        StepOutput(
            output_name=name,
            value_type=value_type,
            preview=_preview(raw_outputs[name]),
        )
        for name, value_type in definition.output_ports.items()
    ]


def execute_workflow(
    workflow: Workflow,
    context: ExecutionContext,
    *,
    handler_map: Optional[Mapping[str, Handler]] = None,
    registry: StepRegistry = STEP_REGISTRY,
    allowed_file_roots: Sequence[Path] = ALLOWED_FILE_ROOTS,
) -> WorkflowResult:
    handlers = dict(handler_map or {})
    try:
        validate_workflow(
            workflow,
            context,
            registry=registry,
            allowed_file_roots=allowed_file_roots,
        )
    except WorkflowValidationError as exc:
        log_workflow_status(
            workflow_id=workflow.id,
            run_id=context.run_id,
            status=WorkflowStatus.FAILED,
            error_summary=exc,
        )
        return WorkflowResult(
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            run_id=context.run_id,
            status=WorkflowStatus.FAILED,
            error_message=str(exc),
        )

    log_workflow_status(
        workflow_id=workflow.id,
        run_id=context.run_id,
        status=WorkflowStatus.VALIDATED,
    )
    log_workflow_status(
        workflow_id=workflow.id,
        run_id=context.run_id,
        status=WorkflowStatus.RUNNING,
    )
    step_runs: List[StepRunResult] = []
    failed_message: Optional[str] = None
    for index, step in enumerate(workflow.steps):
        definition = registry.get(step.step_type)
        assert definition is not None
        started_at = _utc_now()
        log_step_status(
            workflow_id=workflow.id,
            run_id=context.run_id,
            step_id=step.id,
            step_type=step.step_type,
            status=StepStatus.RUNNING,
        )
        try:
            handler = handlers.get(definition.handler_name)
            if handler is None:
                raise RuntimeError(
                    f"No handler is configured for step_type: {step.step_type}"
                )
            params = definition.params_model.model_validate(step.params).model_dump()
            raw_outputs = handler(_resolve_inputs(step, context), params, context)
            outputs = _build_step_outputs(definition, raw_outputs)
            context.step_outputs[step.id] = dict(raw_outputs)
            log_step_status(
                workflow_id=workflow.id,
                run_id=context.run_id,
                step_id=step.id,
                step_type=step.step_type,
                status=StepStatus.COMPLETED,
            )
            step_runs.append(
                StepRunResult(
                    step_id=step.id,
                    step_type=step.step_type,
                    status=StepStatus.COMPLETED,
                    outputs=outputs,
                    preview="; ".join(
                        output.preview or "" for output in outputs if output.preview
                    ),
                    started_at=started_at,
                    finished_at=_utc_now(),
                )
            )
        except Exception as exc:  # Handler errors become user-visible run failures.
            failed_message = str(exc)
            log_step_status(
                workflow_id=workflow.id,
                run_id=context.run_id,
                step_id=step.id,
                step_type=step.step_type,
                status=StepStatus.FAILED,
                error_summary=exc,
            )
            step_runs.append(
                StepRunResult(
                    step_id=step.id,
                    step_type=step.step_type,
                    status=StepStatus.FAILED,
                    error_message=failed_message,
                    started_at=started_at,
                    finished_at=_utc_now(),
                )
            )
            for remaining in workflow.steps[index + 1 :]:
                log_step_status(
                    workflow_id=workflow.id,
                    run_id=context.run_id,
                    step_id=remaining.id,
                    step_type=remaining.step_type,
                    status=StepStatus.SKIPPED,
                )
            step_runs.extend(
                StepRunResult(
                    step_id=remaining.id,
                    step_type=remaining.step_type,
                    status=StepStatus.SKIPPED,
                    error_message="Skipped because an earlier step failed",
                )
                for remaining in workflow.steps[index + 1 :]
            )
            break

    if failed_message is not None:
        log_workflow_status(
            workflow_id=workflow.id,
            run_id=context.run_id,
            status=WorkflowStatus.FAILED,
            error_summary=failed_message,
        )
        return WorkflowResult(
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            run_id=context.run_id,
            status=WorkflowStatus.FAILED,
            step_runs=step_runs,
            error_message=failed_message,
        )

    final_outputs = []
    for binding in workflow.result_bindings:
        definition = registry.get(
            next(step.step_type for step in workflow.steps if step.id == binding.step_id)
        )
        assert definition is not None
        value_type = definition.output_ports[binding.output_name]
        final_outputs.append(
            StepOutput(
                output_name=binding.output_name,
                value_type=value_type,
                label=binding.label,
                display_type=binding.display_type,
                value=context.step_outputs[binding.step_id][binding.output_name],
                preview=_preview(
                    context.step_outputs[binding.step_id][binding.output_name]
                ),
            )
        )

    log_workflow_status(
        workflow_id=workflow.id,
        run_id=context.run_id,
        status=WorkflowStatus.COMPLETED,
    )
    return WorkflowResult(
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        run_id=context.run_id,
        status=WorkflowStatus.COMPLETED,
        step_runs=step_runs,
        final_outputs=final_outputs,
    )
