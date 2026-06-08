from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tools import data_analysis
from tools.data_analysis import (
    DataAnalysisError,
    aggregate_table_data,
    filter_table_data,
    profile_table_data,
    read_table_file,
    render_chart_spec,
    sort_table_data,
)


@pytest.fixture
def sales_table(tmp_path: Path) -> dict:
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(
        "region,status,sales_amount,product\n"
        "North,completed,1200,Starter\n"
        "South,completed,900,Premium\n"
        "North,pending,300,Starter\n"
        "East,completed,1500,Premium\n",
        encoding="utf-8",
    )
    return read_table_file(csv_path)


def test_read_csv_table_returns_serializable_structure(sales_table: dict) -> None:
    assert sales_table["columns"] == [
        "region",
        "status",
        "sales_amount",
        "product",
    ]
    assert sales_table["row_count"] == 4
    assert sales_table["records"][0] == {
        "region": "North",
        "status": "completed",
        "sales_amount": 1200,
        "product": "Starter",
    }


def test_read_xlsx_table_returns_serializable_structure(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "sales.xlsx"
    pd.DataFrame(
        [
            {"region": "North", "sales_amount": 1200},
            {"region": "South", "sales_amount": 900},
        ]
    ).to_excel(xlsx_path, index=False, engine="openpyxl")

    table = read_table_file(xlsx_path)

    assert table["row_count"] == 2
    assert table["records"][1] == {"region": "South", "sales_amount": 900}


def test_read_table_rejects_invalid_csv_with_clear_message(tmp_path: Path) -> None:
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(DataAnalysisError, match="Unable to read table file"):
        read_table_file(csv_path)


def test_read_table_rejects_rows_above_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    csv_path = tmp_path / "too_many.csv"
    csv_path.write_text("value\n1\n2\n3\n", encoding="utf-8")
    monkeypatch.setattr(data_analysis, "MAX_TABLE_ROWS", 2)

    with pytest.raises(DataAnalysisError, match="limit is 2"):
        read_table_file(csv_path)


def test_profile_table_lists_numeric_categorical_and_missing_values() -> None:
    table = data_analysis._frame_to_table(
        pd.DataFrame(
            [
                {"region": "North", "sales_amount": 1200.0},
                {"region": None, "sales_amount": None},
            ]
        ),
        name="sales.csv",
        path="/internal/sales.csv",
    )

    profile = profile_table_data(table)

    assert profile["row_count"] == 2
    assert profile["numeric_columns"] == ["sales_amount"]
    assert profile["categorical_columns"] == ["region"]
    assert profile["missing_values"] == {"region": 1, "sales_amount": 1}


@pytest.mark.parametrize(
    ("operator", "value", "expected_regions"),
    [
        ("eq", "completed", ["North", "South", "East"]),
        ("ne", "completed", ["North"]),
        ("gt", 900, ["North", "East"]),
        ("gte", 900, ["North", "South", "East"]),
        ("lt", 900, ["North"]),
        ("lte", 900, ["South", "North"]),
        ("in", ["North", "East"], ["North", "North", "East"]),
        ("contains", "rem", ["Premium", "Premium"]),
    ],
)
def test_filter_table_supports_whitelisted_operators(
    sales_table: dict,
    operator: str,
    value: object,
    expected_regions: list,
) -> None:
    field = {
        "eq": "status",
        "ne": "status",
        "gt": "sales_amount",
        "gte": "sales_amount",
        "lt": "sales_amount",
        "lte": "sales_amount",
        "in": "region",
        "contains": "product",
    }[operator]

    filtered = filter_table_data(
        sales_table,
        filters=[{"field": field, "operator": operator, "value": value}],
    )

    result_field = "product" if operator == "contains" else "region"
    assert [record[result_field] for record in filtered["records"]] == expected_regions


def test_filter_table_rejects_unknown_operator(sales_table: dict) -> None:
    with pytest.raises(DataAnalysisError, match="Unsupported filter operator"):
        filter_table_data(
            sales_table,
            filters=[{"field": "region", "operator": "starts_with", "value": "N"}],
        )


@pytest.mark.parametrize(
    ("operation", "expected_value"),
    [
        ("count", 2),
        ("sum", 1500),
        ("mean", 750.0),
        ("min", 300),
        ("max", 1200),
    ],
)
def test_aggregate_table_supports_whitelisted_operations(
    sales_table: dict,
    operation: str,
    expected_value: object,
) -> None:
    aggregation = {
        "operation": operation,
        "alias": "metric",
    }
    if operation != "count":
        aggregation["field"] = "sales_amount"

    aggregated = aggregate_table_data(
        sales_table,
        group_by=["region"],
        aggregations=[aggregation],
    )

    north_row = next(
        record for record in aggregated["records"] if record["region"] == "North"
    )
    assert north_row["metric"] == expected_value


def test_aggregate_table_rejects_unknown_operation(sales_table: dict) -> None:
    with pytest.raises(DataAnalysisError, match="Unsupported aggregation"):
        aggregate_table_data(
            sales_table,
            group_by=["region"],
            aggregations=[{"field": "sales_amount", "operation": "median"}],
        )


def test_sort_table_orders_rows_stably(sales_table: dict) -> None:
    sorted_table = sort_table_data(
        sales_table,
        sort_by=[{"field": "sales_amount", "ascending": False}],
    )

    assert [
        record["sales_amount"] for record in sorted_table["records"]
    ] == [1500, 1200, 900, 300]


def test_render_chart_returns_spec_without_file_generation(sales_table: dict) -> None:
    chart = render_chart_spec(
        sales_table,
        chart_type="bar",
        x="region",
        y="sales_amount",
        title="Sales by region",
    )

    assert chart == {
        "chart_type": "bar",
        "title": "Sales by region",
        "x": "region",
        "y": "sales_amount",
        "data": [
            {"region": "North", "sales_amount": 1200},
            {"region": "South", "sales_amount": 900},
            {"region": "North", "sales_amount": 300},
            {"region": "East", "sales_amount": 1500},
        ],
    }
