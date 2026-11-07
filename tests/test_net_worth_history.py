from datetime import date
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber
from django.contrib.messages import get_messages
from django.test import Client

from dashboard.models import FileUploadHistory
from dashboard.services.net_worth_history import read_history, save_net_worth, seed_demo_history


@pytest.fixture
def s3_history(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    settings.NET_WORTH_HISTORY_BUCKET = "test-history-bucket"
    client = boto3.client("s3", region_name="ap-south-1", aws_access_key_id="testing", aws_secret_access_key="testing")
    with Stubber(client) as stubber, patch("dashboard.services.net_worth_history._s3_client", return_value=client):
        yield stubber
        stubber.assert_no_pending_responses()


def test_s3_history_reads_all_pages_and_sorts_dates(s3_history, tmp_path):
    prefix = "net-worth/history/"
    bucket = "test-history-bucket"
    s3_history.add_response("list_objects_v2", {
        "Contents": [{"Key": prefix + "2026-10-31.json"}], "IsTruncated": True, "NextContinuationToken": "next-page",
    }, {"Bucket": bucket, "Prefix": prefix})
    data = b'{"date":"2026-10-31","total_net_worth":90.25}'
    s3_history.add_response("get_object", {"Body": StreamingBody(BytesIO(data), len(data))}, {"Bucket": bucket, "Key": prefix + "2026-10-31.json"})
    s3_history.add_response("list_objects_v2", {
        "Contents": [{"Key": prefix + "2026-10-30.json"}], "IsTruncated": False,
    }, {"Bucket": bucket, "Prefix": prefix, "ContinuationToken": "next-page"})
    data = b'{"date":"2026-10-30","total_net_worth":100}'
    s3_history.add_response("get_object", {"Body": StreamingBody(BytesIO(data), len(data))}, {"Bucket": bucket, "Key": prefix + "2026-10-30.json"})
    assert read_history() == [{"date": "2026-10-30", "total_net_worth": 100}, {"date": "2026-10-31", "total_net_worth": 90.25}]
    assert not (tmp_path / "cache").exists()


def test_s3_writes_only_the_current_date_and_allows_decreases(s3_history, tmp_path):
    for amount in (100.0, 90.25):
        s3_history.add_response("put_object", {}, {
            "Bucket": "test-history-bucket", "Key": "net-worth/history/2026-10-31.json",
            "Body": json.dumps({"date": "2026-10-31", "total_net_worth": amount}).encode("utf-8"),
            "ContentType": "application/json", "ServerSideEncryption": "AES256",
        })
        save_net_worth(amount, date(2026, 10, 31))
    assert not (tmp_path / "cache").exists()


def test_empty_s3_history(s3_history):
    s3_history.add_response("list_objects_v2", {"IsTruncated": False}, {"Bucket": "test-history-bucket", "Prefix": "net-worth/history/"})
    assert read_history() == []


def test_s3_access_failure_does_not_fall_back_to_local_csv(s3_history, tmp_path):
    s3_history.add_client_error("list_objects_v2", service_error_code="AccessDenied", http_status_code=403)
    with pytest.raises(ClientError):
        read_history()
    s3_history.add_client_error("put_object", service_error_code="AccessDenied", http_status_code=403)
    with pytest.raises(ClientError):
        save_net_worth(100)
    assert not (tmp_path / "cache").exists()


def test_demo_is_never_written_or_read_in_s3(s3_history, tmp_path):
    with pytest.raises(ValueError, match="local only"):
        seed_demo_history(100)
    with pytest.raises(ValueError, match="local only"):
        read_history(demo=True)
    assert not (tmp_path / "cache").exists()


@pytest.mark.django_db
def test_lambda_google_sheet_update_and_demo_block(settings, tmp_path, client, s3_history, monkeypatch):
    settings.DEBUG = False
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "portfolio-production")
    FileUploadHistory.objects.create(file_path=str(tmp_path / "gsheet_sample.xlsx"))
    s3_history.add_response("put_object", {}, {
        "Bucket": "test-history-bucket", "Key": "net-worth/history/2026-10-31.json",
        "Body": json.dumps({"date": "2026-10-31", "total_net_worth": 2500000.25}).encode("utf-8"),
        "ContentType": "application/json", "ServerSideEncryption": "AES256",
    })
    with patch("dashboard.views.build_dashboard_context", return_value={"portfolio": SimpleNamespace(net_worth=2500000.25)}), patch("dashboard.services.net_worth_history.timezone.localdate", return_value=date(2026, 10, 31)):
        assert client.post("/net-worth/").status_code == 302
    with patch("dashboard.views.build_dashboard_context") as build:
        assert client.post("/net-worth/", {"action": "demo"}).status_code == 302
        build.assert_not_called()
    assert not (tmp_path / "cache").exists()


@pytest.mark.django_db
def test_cloud_dashboard_reads_s3_and_ignores_demo_query(settings, tmp_path, client, s3_history):
    settings.DEBUG = False
    workbook = tmp_path / "gsheet_sample.xlsx"
    workbook.touch()
    FileUploadHistory.objects.create(file_path=str(workbook))
    s3_history.add_response("list_objects_v2", {"Contents": [{"Key": "net-worth/history/2026-10-31.json"}], "IsTruncated": False}, {"Bucket": "test-history-bucket", "Prefix": "net-worth/history/"})
    data = b'{"date":"2026-10-31","total_net_worth":100}'
    s3_history.add_response("get_object", {"Body": StreamingBody(BytesIO(data), len(data))}, {"Bucket": "test-history-bucket", "Key": "net-worth/history/2026-10-31.json"})
    payload = {"portfolio": {"net_worth": 100}, "snapshots": [{"month": "2020-01", "total_net_worth": 1}]}
    with patch("dashboard.views.build_dashboard_context", return_value=payload):
        response = client.get("/?history=demo")
    assert response.status_code == 200
    assert response.context["snapshots"] == [{"date": "2026-10-31", "total_net_worth": 100}]
    assert response.context["net_worth_demo"] is False
    assert response.context["net_worth_history_enabled"] is True
    assert b"Update Net Worth" in response.content
    assert b"Load Demo Year" not in response.content
    assert payload["snapshots"][0]["month"] == "2020-01"


@pytest.mark.django_db
def test_cloud_storage_errors_are_visible_without_losing_portfolio(settings, tmp_path, client, s3_history):
    settings.DEBUG = False
    workbook = tmp_path / "gsheet_sample.xlsx"
    workbook.touch()
    FileUploadHistory.objects.create(file_path=str(workbook))
    s3_history.add_client_error("list_objects_v2", service_error_code="AccessDenied", http_status_code=403)
    payload = {"portfolio": {"net_worth": 100}, "errors": []}
    with patch("dashboard.views.build_dashboard_context", return_value=payload):
        response = client.get("/")
    assert response.status_code == 200
    assert response.context["portfolio"] == {"net_worth": 100}
    assert response.context["snapshots"] == []
    assert b"Net worth history could not be read" in response.content
    assert payload["errors"] == []
    s3_history.add_client_error("put_object", service_error_code="AccessDenied", http_status_code=403)
    with patch("dashboard.views.build_dashboard_context", return_value={"portfolio": SimpleNamespace(net_worth=100)}):
        response = client.post("/net-worth/")
    messages = [str(message) for message in get_messages(response.wsgi_request)]
    assert any("could not be saved" in message for message in messages)
    assert not any("saved for today" in message for message in messages)


def test_daily_history_preserves_dates_and_replaces_same_day(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    save_net_worth(100000, date(2026, 10, 30))
    save_net_worth(105000, date(2026, 10, 31))
    save_net_worth(99000.25, date(2026, 10, 31))
    assert read_history() == [
        {"date": "2026-10-30", "total_net_worth": 100000},
        {"date": "2026-10-31", "total_net_worth": 99000.25},
    ]
    assert (tmp_path / "cache/net_worth.csv").read_text().splitlines() == [
        "date,total_net_worth", "2026-10-30,100000.00", "2026-10-31,99000.25",
    ]


def test_demo_is_one_year_with_gains_and_losses_and_separate_from_real(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    save_net_worth(2500000, date(2026, 10, 31))
    seed_demo_history(2500000, date(2026, 10, 31))
    records = read_history(demo=True)
    assert records[0]["date"] == "2025-10-31"
    assert records[-1] == {"date": "2026-10-31", "total_net_worth": 2500000}
    assert len(records) == 54
    changes = [current["total_net_worth"] - previous["total_net_worth"] for previous, current in zip(records, records[1:])]
    assert min(changes) < 0 < max(changes)
    assert len(read_history()) == 1


def test_corrupt_history_is_not_overwritten(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    directory = tmp_path / "cache"
    directory.mkdir()
    path = directory / "net_worth.csv"
    path.write_text("invalid,data\n")
    with pytest.raises(ValueError):
        save_net_worth(100)
    assert path.read_text() == "invalid,data\n"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_values_are_rejected(settings, tmp_path, value):
    settings.BASE_DIR = tmp_path
    with pytest.raises(ValueError):
        save_net_worth(value)
    assert not (tmp_path / "cache/net_worth.csv").exists()


@pytest.mark.django_db
def test_local_update_uses_server_value_and_demo_stays_separate(settings, tmp_path, client):
    settings.DEBUG = True
    settings.BASE_DIR = tmp_path
    FileUploadHistory.objects.create(file_path=str(tmp_path / "portfolio.xlsx"))
    with patch("dashboard.views.build_dashboard_context", return_value={"portfolio": SimpleNamespace(net_worth=2100000)}):
        response = client.post("/net-worth/", {"total_net_worth": "999"}, HTTP_HOST="localhost")
        assert response.status_code == 302
        assert read_history() == [{"date": date.today().isoformat(), "total_net_worth": 2100000}]
        response = client.post("/net-worth/", {"action": "demo"}, HTTP_HOST="localhost")
        assert response.url == "/?history=demo"
        assert len(read_history(demo=True)) == 54
        assert len(read_history()) == 1
    with patch("dashboard.views.build_dashboard_context", return_value={"portfolio": SimpleNamespace(net_worth=2000000)}):
        client.post("/net-worth/", HTTP_HOST="localhost")
    assert len(read_history()) == 1
    assert read_history()[0]["total_net_worth"] == 2000000


@pytest.mark.django_db
@pytest.mark.parametrize("debug,host,filename,lambda_name", [
    (False, "localhost", "portfolio.xlsx", ""),
    (True, "testserver", "portfolio.xlsx", ""),
    (True, "localhost", "gsheet_sample.xlsx", ""),
    (True, "localhost", "portfolio.xlsx", "deployed-function"),
])
def test_nonlocal_and_google_sources_cannot_write(settings, tmp_path, client, monkeypatch, debug, host, filename, lambda_name):
    settings.DEBUG = debug
    settings.BASE_DIR = tmp_path
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", lambda_name)
    FileUploadHistory.objects.create(file_path=str(tmp_path / filename))
    with patch("dashboard.views.build_dashboard_context") as build:
        client.post("/net-worth/", HTTP_HOST=host)
        client.post("/net-worth/", {"action": "demo"}, HTTP_HOST=host)
    build.assert_not_called()
    assert not (tmp_path / "cache").exists()


@pytest.mark.django_db
def test_update_requires_post_csrf_and_valid_portfolio(settings, tmp_path, client):
    settings.DEBUG = True
    settings.BASE_DIR = tmp_path
    assert client.get("/net-worth/", HTTP_HOST="localhost").status_code == 405
    assert Client(enforce_csrf_checks=True).post("/net-worth/", HTTP_HOST="localhost").status_code == 403
    client.post("/net-worth/", HTTP_HOST="localhost")
    FileUploadHistory.objects.create(file_path=str(tmp_path / "portfolio.xlsx"))
    with patch("dashboard.views.build_dashboard_context", return_value={"portfolio": None, "errors": ["Invalid workbook"]}):
        client.post("/net-worth/", HTTP_HOST="localhost")
    assert not (tmp_path / "cache").exists()


@pytest.mark.django_db
def test_dashboard_reads_csv_even_with_cached_portfolio(settings, tmp_path, client):
    settings.DEBUG = True
    settings.BASE_DIR = tmp_path
    workbook = tmp_path / "portfolio.xlsx"
    workbook.touch()
    FileUploadHistory.objects.create(file_path=str(workbook))
    payload = {"portfolio": None, "snapshots": [{"month": "2020-01", "total_net_worth": 1}]}
    with patch("dashboard.views.build_dashboard_context", return_value=payload):
        save_net_worth(100, date(2026, 10, 30))
        response = client.get("/", HTTP_HOST="localhost")
        assert response.context["snapshots"] == read_history()
        save_net_worth(90, date(2026, 10, 31))
        response = client.get("/", HTTP_HOST="localhost")
        assert len(response.context["snapshots"]) == 2
        assert payload["snapshots"][0]["month"] == "2020-01"
        seed_demo_history(90)
        response = client.get("/?history=demo", HTTP_HOST="localhost")
        assert response.context["net_worth_demo"] is True
        assert len(response.context["snapshots"]) == 54