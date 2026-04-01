from __future__ import annotations

from datetime import datetime, timedelta, timezone
TR_TZ = timezone(timedelta(hours=3))
from decimal import Decimal, InvalidOperation
from typing import Any

import config
from digitalplanet_client import DigitalPlanetClient
from google_sheets_writer import GoogleSheetsWriter


OUTGOING_HEADERS = ["Oluşturulma Tarihi", "Alıcı", "Tutar", "Fatura No", "Tür"]
INCOMING_HEADERS = ["Oluşturulma Tarihi", "Alıcı", "Tutar", "Fatura No", "Tür"]

META_SHEET_NAME = "_meta"
LAST_SYNC_KEY = "last_sync"


def safe_get(record: dict, *keys, default="") -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return default


def parse_date(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    text = str(value)
    return text.replace("T", " ")[:16] if "T" in text else text


def parse_date_for_sort(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%d.%m.%Y %H:%M")
    except Exception:
        return datetime.min


def parse_amount(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).replace(",", ".").strip()
    try:
        amount = Decimal(text)
        return f"{amount:.2f}".replace(".", ",")
    except (InvalidOperation, ValueError):
        return str(value)


def detect_type(record: dict, forced_type: str | None = None) -> str:
    if forced_type:
        return forced_type

    direction = str(safe_get(record, "Direction", default="")).strip().lower()
    profile_id = str(safe_get(record, "Profileid", "ProfileID", default="")).strip().upper()

    if direction == "earchive":
        return "e-Arşiv"

    if "ARSIV" in profile_id:
        return "e-Arşiv"

    return "e-Fatura"


def normalize_outgoing_record(record: dict, forced_type: str | None = None) -> list[str]:
    return [
        parse_date(safe_get(record, "Createdate", "CreateDate", "IssueDate", "Issuedate")),
        str(safe_get(record, "Partyname", "PartyName")).strip(),
        parse_amount(safe_get(record, "Payableamount", "PayableAmount")),
        str(safe_get(record, "InvoiceId", "InvoiceID")).strip(),
        detect_type(record, forced_type=forced_type),
    ]


def normalize_incoming_record(record: dict, forced_type: str | None = None) -> list[str]:
    return [
        parse_date(safe_get(record, "Createdate", "CreateDate", "IssueDate", "Issuedate")),
        str(safe_get(record, "Partyname", "PartyName")).strip(),
        parse_amount(safe_get(record, "Payableamount", "PayableAmount")),
        str(safe_get(record, "InvoiceId", "InvoiceID")).strip(),
        detect_type(record, forced_type=forced_type),
    ]


def extract_invoices(pack_result: dict) -> list[dict]:
    invoices = pack_result.get("Invoices")

    if not invoices:
        return []

    if isinstance(invoices, dict):
        inner = invoices.get("InvoiceInfoResult")

        if isinstance(inner, list):
            return inner

        if isinstance(inner, dict):
            return [inner]

    if isinstance(invoices, list):
        return invoices

    return []


def dedupe_rows_by_invoice_no(rows: list[list[str]]) -> list[list[str]]:
    seen_invoice_nos = set()
    output = []

    for row in rows:
        invoice_no = (row[3] or "").strip()

        if not invoice_no:
            continue

        if invoice_no not in seen_invoice_nos:
            seen_invoice_nos.add(invoice_no)
            output.append(row)

    return output


def get_last_sync_time(writer: GoogleSheetsWriter) -> datetime:
    ws = writer.get_or_create_sheet(META_SHEET_NAME, rows=100, cols=2)
    values = ws.get_all_values()

    for row in values:
        if len(row) >= 2 and row[0].strip() == LAST_SYNC_KEY:
            try:
                return datetime.fromisoformat(row[1].strip())
            except Exception:
                pass

    # ilk çalıştırma fallback
    return datetime.now(TR_TZ) - timedelta(days=config.LOOKBACK_DAYS)


def update_last_sync_time(writer: GoogleSheetsWriter, sync_time: datetime) -> None:
    ws = writer.get_or_create_sheet(META_SHEET_NAME, rows=100, cols=2)
    ws.clear()
    ws.update("A1", [["key", "value"], [LAST_SYNC_KEY, sync_time.isoformat()]])


def main() -> None:
    print("Google Sheets'e bağlanılıyor...")
    writer = GoogleSheetsWriter(
        service_account_file=str(config.GOOGLE_SERVICE_ACCOUNT_FILE),
        spreadsheet_name=config.SPREADSHEET_NAME,
    )

    now = datetime.now(TR_TZ)
    last_sync = get_last_sync_time(writer)

    # güvenlik overlap'i: son 10 dakikayı tekrar tara
    start_date = last_sync - timedelta(minutes=10)
    end_date = now

    print(f"Sync aralığı: {start_date} -> {end_date}")

    print(f"SOAP bağlanıyor: {config.WSDL_URL}")
    dp = DigitalPlanetClient(
        wsdl_url=config.WSDL_URL,
        corporate_code=config.CORPORATE_CODE,
        login_name=config.LOGIN_NAME,
        password=config.PASSWORD,
        timeout=config.SOAP_TIMEOUT_SECONDS,
    )

    print("Ticket alınıyor...")
    dp.authenticate()
    print("Ticket alındı.")

    print("Giden e-Faturalar çekiliyor...")
    outgoing_pack = dp.get_available_sent_invoices_by_date(start_date, end_date)
    outgoing_invoices = extract_invoices(outgoing_pack)
    print(f"Giden e-Fatura kayıt sayısı: {len(outgoing_invoices)}")

    print("Giden e-Arşiv faturalar çekiliyor...")
    earchive_pack = dp.get_earchive_invoices_by_date(start_date, end_date)
    earchive_invoices = extract_invoices(earchive_pack)
    print(f"Giden e-Arşiv kayıt sayısı: {len(earchive_invoices)}")

    print("Gelen faturalar çekiliyor...")
    incoming_pack = dp.get_incoming_invoices_by_issue_date(start_date, end_date)
    incoming_invoices = extract_invoices(incoming_pack)
    print(f"Gelen kayıt sayısı: {len(incoming_invoices)}")

    outgoing_rows = [normalize_outgoing_record(inv, forced_type="e-Fatura") for inv in outgoing_invoices]
    earchive_rows = [normalize_outgoing_record(inv, forced_type="e-Arşiv") for inv in earchive_invoices]
    incoming_rows = [normalize_incoming_record(inv, forced_type="e-Fatura") for inv in incoming_invoices]

    outgoing_rows = outgoing_rows + earchive_rows

    outgoing_rows = [r for r in outgoing_rows if any(str(cell).strip() for cell in r)]
    incoming_rows = [r for r in incoming_rows if any(str(cell).strip() for cell in r)]

    outgoing_rows = dedupe_rows_by_invoice_no(outgoing_rows)
    incoming_rows = dedupe_rows_by_invoice_no(incoming_rows)

    # en eski üstte
    outgoing_rows.sort(key=lambda r: parse_date_for_sort(r[0]))
    incoming_rows.sort(key=lambda r: parse_date_for_sort(r[0]))

    print("Google Sheets'e yazılıyor...")

    writer.ensure_headers(config.OUTGOING_SHEET_NAME, OUTGOING_HEADERS)
    writer.ensure_headers(config.INCOMING_SHEET_NAME, INCOMING_HEADERS)

    existing_outgoing = writer.get_existing_invoice_numbers(config.OUTGOING_SHEET_NAME)
    existing_incoming = writer.get_existing_invoice_numbers(config.INCOMING_SHEET_NAME)

    new_outgoing = [r for r in outgoing_rows if r[3] not in existing_outgoing]
    new_incoming = [r for r in incoming_rows if r[3] not in existing_incoming]

    new_outgoing.sort(key=lambda r: parse_date_for_sort(r[0]))
    new_incoming.sort(key=lambda r: parse_date_for_sort(r[0]))

    print(f"Yeni giden fatura sayısı: {len(new_outgoing)}")
    print(f"Yeni gelen fatura sayısı: {len(new_incoming)}")

    writer.append_rows(config.OUTGOING_SHEET_NAME, new_outgoing)
    writer.append_rows(config.INCOMING_SHEET_NAME, new_incoming)

    update_last_sync_time(writer, now)

    print("Tamamlandı.")


if __name__ == "__main__":
    main()
