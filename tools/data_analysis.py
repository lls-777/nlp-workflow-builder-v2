from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import pandas as pd

from config import MAX_TABLE_ROWS
from core.workflow_schema import ExecutionContext


SUPPORTED_TABLE_EXTENSIONS = frozenset({".csv", ".xlsx"})
TABLE_PREVIEW_ROWS = 5


class DataAnalysisError(ValueError):
    """Raised when a declarative table operation cannot be completed."""


def read_table_file(
    file_path: Union[str, Path],
    *,
    sheet_name: Optional[str] = None,
) -> Dict[str, Any]:
    path = Path(file_path).resolve()
    if not path.is_file():
        raise DataAnalysisError(f"Table file does not exist: {path}")
    extension = path.suffix.lower()
    if extension not in SUPPORTED_TABLE_EXTENSIONS:
        raise DataAnalysisError(
            f"Unsupported table format: {extension or '<none>'}. "
            "Supported formats are CSV and XLSX."
        )

    try:
        if extension == ".csv":
            frame = pd.read_csv(path)
        else:
            frame = pd.read_excel(path, sheet_name=sheet_name or 0, engine="openpyxl")
    except Exception as exc:
        raise DataAnalysisError(
            f"Unable to read table file. Check that the file is a valid {extension[1:].upper()} document: "
            f"{path.name}"
        ) from exc
    return _frame_to_table(frame, name=path.name, path=str(path))


def profile_table_data(table: Mapping[str, Any]) -> Dict[str, Any]:
    frame = _table_to_frame(table)
    columns = [str(column) for column in frame.columns]
    numeric_columns = [
        str(column)
        for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column])
    ]
    categorical_columns = [
        column for column in columns if column not in numeric_columns
    ]
    return {
        "row_count": len(frame),
        "columns": columns,
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "missing_values": {
            str(column): int(frame[column].isna().sum()) for column in frame.columns
        },
        "preview": _records(frame.head(TABLE_PREVIEW_ROWS)),
    }


def filter_table_data(
    table: Mapping[str, Any],
    *,
    filters: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    frame = _table_to_frame(table)
    filtered_frame = frame
    for condition in filters:
        field = _require_column(filtered_frame, condition.get("field"))
        operator = condition.get("operator")
        value = condition.get("value")
        try:
            mask = _build_filter_mask(filtered_frame[field], operator, value)
        except DataAnalysisError:
            raise
        except (TypeError, ValueError) as exc:
            raise DataAnalysisError(
                f"Cannot apply filter '{operator}' to column '{field}'."
            ) from exc
        filtered_frame = filtered_frame.loc[mask].copy()
    return _frame_to_table(
        filtered_frame,
        name=str(table.get("name", "table")),
        path=str(table.get("path", "")),
    )


def aggregate_table_data(
    table: Mapping[str, Any],
    *,
    group_by: Sequence[str],
    aggregations: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    frame = _table_to_frame(table)
    normalized_group_by = [_require_column(frame, field) for field in group_by]
    result_frame = _group_frame(frame, normalized_group_by)

    for index, aggregation in enumerate(aggregations, start=1):
        operation = aggregation.get("operation")
        field_value = aggregation.get("field")
        field = _require_column(frame, field_value) if field_value else None
        alias = str(
            aggregation.get("alias")
            or _default_aggregation_alias(operation, field, index)
        )
        if alias in result_frame.columns:
            raise DataAnalysisError(f"Duplicate aggregation output column: {alias}")
        values = _aggregate_series(
            frame=frame,
            group_by=normalized_group_by,
            operation=operation,
            field=field,
        )
        result_frame = result_frame.merge(
            values.rename(alias).reset_index(),
            on=normalized_group_by,
            how="left",
        ) if normalized_group_by else _append_scalar_column(
            result_frame, alias=alias, value=values
        )

    return _frame_to_table(
        result_frame,
        name=str(table.get("name", "table")),
        path=str(table.get("path", "")),
    )


def sort_table_data(
    table: Mapping[str, Any],
    *,
    sort_by: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    frame = _table_to_frame(table)
    fields = [_require_column(frame, spec.get("field")) for spec in sort_by]
    ascending = [bool(spec.get("ascending", True)) for spec in sort_by]
    try:
        sorted_frame = frame.sort_values(
            by=fields,
            ascending=ascending,
            kind="mergesort",
            na_position="last",
        )
    except (TypeError, ValueError) as exc:
        raise DataAnalysisError("Unable to sort the table with the provided fields.") from exc
    return _frame_to_table(
        sorted_frame,
        name=str(table.get("name", "table")),
        path=str(table.get("path", "")),
    )


def render_chart_spec(
    table: Mapping[str, Any],
    *,
    chart_type: str,
    x: str,
    y: str,
    title: Optional[str],
) -> Dict[str, Any]:
    frame = _table_to_frame(table)
    x_field = _require_column(frame, x)
    y_field = _require_column(frame, y)
    if chart_type not in {"bar", "line"}:
        raise DataAnalysisError(f"Unsupported chart type: {chart_type}")
    return {
        "chart_type": chart_type,
        "title": title or f"{y_field} by {x_field}",
        "x": x_field,
        "y": y_field,
        "data": _records(frame[[x_field, y_field]]),
    }


def read_table(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    return {
        "table": read_table_file(
            inputs.get("file", ""),
            sheet_name=params.get("sheet_name"),
        )
    }


def profile_table(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    return {"table_profile": profile_table_data(_require_table_input(inputs))}


def filter_table(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    return {
        "table": filter_table_data(
            _require_table_input(inputs),
            filters=params["filters"],
        )
    }


def aggregate_table(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    return {
        "table": aggregate_table_data(
            _require_table_input(inputs),
            group_by=params["group_by"],
            aggregations=params["aggregations"],
        )
    }


def sort_table(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    return {
        "table": sort_table_data(
            _require_table_input(inputs),
            sort_by=params["sort_by"],
        )
    }


def render_chart(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    return {
        "chart": render_chart_spec(
            _require_table_input(inputs),
            chart_type=params["chart_type"],
            x=params["x"],
            y=params["y"],
            title=params.get("title"),
        )
    }


def _build_filter_mask(
    series: pd.Series,
    operator: Any,
    value: Any,
) -> pd.Series:
    if operator == "eq":
        return series == value
    if operator == "ne":
        return series != value
    if operator == "gt":
        return series > value
    if operator == "gte":
        return series >= value
    if operator == "lt":
        return series < value
    if operator == "lte":
        return series <= value
    if operator == "in":
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise DataAnalysisError("Filter operator 'in' requires a list of values.")
        return series.isin(value)
    if operator == "contains":
        if not isinstance(value, str):
            raise DataAnalysisError("Filter operator 'contains' requires text.")
        return series.astype("string").str.contains(value, regex=False, na=False)
    raise DataAnalysisError(f"Unsupported filter operator: {operator}")


def _aggregate_series(
    *,
    frame: pd.DataFrame,
    group_by: Sequence[str],
    operation: Any,
    field: Optional[str],
) -> Any:
    grouped = frame.groupby(list(group_by), dropna=False, sort=False) if group_by else None
    if operation == "count":
        return grouped.size() if grouped is not None else int(len(frame))
    if field is None:
        raise DataAnalysisError(f"Aggregation '{operation}' requires a field.")
    if operation in {"sum", "mean", "min", "max"}:
        if operation in {"sum", "mean"} and not pd.api.types.is_numeric_dtype(frame[field]):
            raise DataAnalysisError(
                f"Aggregation '{operation}' requires numeric column: {field}"
            )
        series = grouped[field] if grouped is not None else frame[field]
        if operation == "sum":
            return series.sum()
        if operation == "mean":
            return series.mean()
        if operation == "min":
            return series.min()
        return series.max()
    raise DataAnalysisError(f"Unsupported aggregation operation: {operation}")


def _group_frame(frame: pd.DataFrame, group_by: Sequence[str]) -> pd.DataFrame:
    if not group_by:
        return pd.DataFrame(index=[0])
    return frame[list(group_by)].drop_duplicates().reset_index(drop=True)


def _append_scalar_column(frame: pd.DataFrame, *, alias: str, value: Any) -> pd.DataFrame:
    result = frame.copy()
    result[alias] = value
    return result


def _default_aggregation_alias(
    operation: Any,
    field: Optional[str],
    index: int,
) -> str:
    if field:
        return f"{operation}_{field}"
    return f"{operation}_{index}"


def _require_table_input(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    table = inputs.get("table")
    if not isinstance(table, Mapping):
        raise DataAnalysisError("Table operation requires a table input.")
    return table


def _require_column(frame: pd.DataFrame, field: Any) -> str:
    if not isinstance(field, str) or not field:
        raise DataAnalysisError("Table column name is required.")
    if field not in frame.columns:
        raise DataAnalysisError(f"Table column does not exist: {field}")
    return field


def _table_to_frame(table: Mapping[str, Any]) -> pd.DataFrame:
    records = table.get("records")
    if not isinstance(records, list):
        raise DataAnalysisError("Table records must be a list.")
    columns = table.get("columns")
    if not isinstance(columns, list):
        raise DataAnalysisError("Table columns must be a list.")
    try:
        return pd.DataFrame(records, columns=columns)
    except Exception as exc:
        raise DataAnalysisError("Table data cannot be processed.") from exc


def _frame_to_table(frame: pd.DataFrame, *, name: str, path: str) -> Dict[str, Any]:
    normalized_frame = frame.reset_index(drop=True)
    if len(normalized_frame) > MAX_TABLE_ROWS:
        raise DataAnalysisError(
            f"Table contains {len(normalized_frame)} rows; limit is {MAX_TABLE_ROWS}."
        )
    columns = [str(column) for column in normalized_frame.columns]
    if len(set(columns)) != len(columns):
        raise DataAnalysisError("Table contains duplicate column names.")
    normalized_frame.columns = columns
    return {
        "name": name,
        "path": path,
        "columns": columns,
        "row_count": len(normalized_frame),
        "preview": _records(normalized_frame.head(TABLE_PREVIEW_ROWS)),
        "records": _records(normalized_frame),
    }


def _records(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    sanitized_frame = frame.astype(object).where(pd.notna(frame), None)
    return [
        {str(key): _to_json_value(value) for key, value in record.items()}
        for record in sanitized_frame.to_dict(orient="records")
    ]


def _to_json_value(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
