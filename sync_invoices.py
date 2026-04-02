from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from config import (
    CORPORATE_CODE,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    INCOMING_SHEET_NAME,
    LOGIN_NAME,
    OUTGOING_SHEET_NAME,
    PASSWORD,
    SERVICE_URL,
    SOAP_TIMEOUT_SECONDS,
    SPREADSHEET_NAME,
    WSDL_URL,
)
from digitalplanet_client import DigitalPlanetClient
from google_sheets_writer import GoogleSheetsWriter

META_SHEET_NAME = "_meta"
LAST_SYNC_KEY = "last_sync"


def safe_get(obj: Any, *keys: str, default: Any = "") -> Any:
    if obj is None:
        return default

    if isinstance(obj, dict):
        lowered = {str(k).lower(): v for k, v in obj.items()}
        for key in keys:
            if key in obj:
                return obj[key]
            val = lowered.get(str(key).lower())
            if val is not None:
                return val

    for key in keys:
        if hasattr(obj, key):
            return getattr(obj, key)

    return default


def extract_invoices(pack: Any) -> list[dict]:
    if not pack:
        return []

    if isinstance(pack, dict):
        invoices = safe_get(pack, "Invoices", "invoices", default=[])
        if invoices is None:
            return []
        if isinstance(invoices, list):
            return invoices
        return [invoices]

    invoices = getattr(pack, "Invoices", None)
    if invoices is None:
        return []

    if isinstance(invoices, list):
        return invoices
    return [invoices]


def to_iso(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return str(value)


def to_decimal_str(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        dec = Decimal(str(value))
        return format(dec, "f")
    except (InvalidOperation, ValueError):
        return str(value)


def normalize_outgoing_record(inv: Any) -> list[str]:
    created = safe_get(inv, "Createdate", "CreateDate", "IssueDate", default="")
    party = safe_get(inv, "Partyname", "PartyName", default="")
    payable = safe_get(inv, "Payableamount", "PayableAmount", default="")
    invoice_id = safe_get(inv, "InvoiceId", "ID", default="")
    status = safe_get(inv, "StatusDescription", "Status", default="")
    uuid = safe_get(inv, "UUID", "Uuid", default="")

    return [
        to_iso(created),
        str(party),
        to_decimal_str(payable),
        str(invoice_id),
        str(status),
        str(uuid),
    ]


def normalize_incoming_record(inv: Any) -> list[str]:
    created = safe_get(inv, "Createdate", "CreateDate", "IssueDate", default="")
    party = safe_get(inv, "Partyname", "PartyName", default="")
    payable = safe_get(inv, "Payableamount", "PayableAmount", default="")
    invoice_id = safe_get(inv, "InvoiceId", "ID", default="")
    status = safe_get(inv, "StatusDescription", "Status", default="")
    uuid = safe_get(inv, "UUID", "Uuid", default="")

    return [
        to_iso(created),
        str(party),
        to_decimal_str(payable),
        str(invoice_id),
        str(status),
        str(uuid),
    ]


def read_last_sync(writer: GoogleSheetsWriter) -> datetime | None:
    rows = writer.read_sheet(META_SHEET_NAME)
    if not rows:
        return None

    for row in rows:
        if len(row) >= 2 and str(row[0]).strip() == LAST_SYNC_KEY:
            raw = str(row[1]).strip()
            if not raw:
                return None
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                return None
    return None


def write_last_sync(writer: GoogleSheetsWriter, ts: datetime) -> None:
    writer.clear_sheet(META_SHEET_NAME)
    writer.write_rows(
        META_SHEET_NAME,
        [["key", "value"], [LAST_SYNC_KEY, ts.isoformat(sep=" ", timespec="seconds")]],
    )


def build_existing_keys(rows: list[list[Any]]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()

    for row in rows[1:]:
        if len(row) < 4:
            continue

        created = str(row[0]).strip()
        payable = str(row[2]).strip()
        invoice_id = str(row[3]).strip()

        if invoice_id:
            keys.add((created, payable, invoice_id))

    return keys


def filter_new_rows(existing_rows: list[list[Any]], candidate_rows: list[list[str]]) -> list[list[str]]:
    existing_keys = build_existing_keys(existing_rows)
    new_rows: list[list[str]] = []

    for row in candidate_rows:
        if len(row) < 4:
            continue

        key = (str(row[0]).strip(), str(row[2]).strip(), str(row[3]).strip())
        if key not in existing_keys:
            new_rows.append(row)
            existing_keys.add(key)

    return new_rows


def main() -> None:
    now = datetime.now()

    writer = GoogleSheetsWriter(
        service_account_file=GOOGLE_SERVICE_ACCOUNT_FILE,
        spreadsheet_name=SPREADSHEET_NAME,
    )

    last_sync = read_last_sync(writer)

    if last_sync is None:
        start_date = now - timedelta(days=3)
        print(f"İlk senkronizasyon. Başlangıç tarihi: {start_date}")
    else:
        # Güvenlik overlap'i
        start_date = last_sync - timedelta(minutes=600)
        print(f"Son senkronizasyon bulundu: {last_sync}")
        print(f"Overlap'li başlangıç tarihi: {start_date}")

    end_date = now
    print(f"Bitiş tarihi: {end_date}")

    dp = DigitalPlanetClient(
        wsdl_url=WSDL_URL,
        corporate_code=CORPORATE_CODE,
        login_name=LOGIN_NAME,
        password=PASSWORD,
        timeout=SOAP_TIMEOUT_SECONDS,
    )

    print("Giden e-Faturalar çekiliyor...")
    outgoing_pack = dp.get_available_sent_invoices_by_date(start_date, end_date)
    outgoing_invoices = extract_invoices(outgoing_pack)
    print(f"Giden e-Fatura kayıt sayısı: {len(outgoing_invoices)}")

    print("Giden e-Arşiv faturalar çekiliyor...")
    earchive_pack = dp.get_earchive_invoices_by_date(start_date, end_date)
    earchive_invoices = extract_invoices(earchive_pack)
    print(f"Giden e-Arşiv kayıt sayısı: {len(earchive_invoices)}")

    print("Gelen faturalar çekiliyor...")
    incoming_pack = dp.get_available_invoices_by_date(start_date, end_date)
    all_available_invoices = extract_invoices(incoming_pack)

    incoming_invoices: list[dict] = []
    for inv in all_available_invoices:
        direction = str(safe_get(inv, "Direction", default="")).strip().lower()
        if "incoming" in direction:
            incoming_invoices.append(inv)

    print(f"Gelen kayıt sayısı: {len(incoming_invoices)}")

    outgoing_rows = [normalize_outgoing_record(inv) for inv in outgoing_invoices]
    earchive_rows = [normalize_outgoing_record(inv) for inv in earchive_invoices]
    all_outgoing_rows = outgoing_rows + earchive_rows

    incoming_rows = [normalize_incoming_record(inv) for inv in incoming_invoices]

    outgoing_existing = writer.read_sheet(OUTGOING_SHEET_NAME)
    incoming_existing = writer.read_sheet(INCOMING_SHEET_NAME)

    if not outgoing_existing:
        outgoing_existing = [["Oluşturulma Tarihi", "Firma Ünvanı", "Fatura Tutarı", "Fatura No", "Durum", "UUID"]]
    if not incoming_existing:
        incoming_existing = [["Oluşturulma Tarihi", "Firma Ünvanı", "Fatura Tutarı", "Fatura No", "Durum", "UUID"]]

    new_outgoing_rows = filter_new_rows(outgoing_existing, all_outgoing_rows)
    new_incoming_rows = filter_new_rows(incoming_existing, incoming_rows)

    print(f"Yeni giden kayıt sayısı: {len(new_outgoing_rows)}")
    print(f"Yeni gelen kayıt sayısı: {len(new_incoming_rows)}")

    if len(outgoing_existing) <= 1:
        writer.clear_sheet(OUTGOING_SHEET_NAME)
        writer.write_rows(OUTGOING_SHEET_NAME, outgoing_existing[:1])

    if len(incoming_existing) <= 1:
        writer.clear_sheet(INCOMING_SHEET_NAME)
        writer.write_rows(INCOMING_SHEET_NAME, incoming_existing[:1])

    if new_outgoing_rows:
        writer.append_rows(OUTGOING_SHEET_NAME, new_outgoing_rows)

    if new_incoming_rows:
        writer.append_rows(INCOMING_SHEET_NAME, new_incoming_rows)

    write_last_sync(writer, now)
    print("Senkronizasyon tamamlandı.")


if __name__ == "__main__":
    main()
