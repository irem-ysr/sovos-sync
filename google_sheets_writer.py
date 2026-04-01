import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsWriter:
    def __init__(self, service_account_file: str, spreadsheet_name: str):
        creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
        self.gc = gspread.authorize(creds)
        self.spreadsheet = self.gc.open(spreadsheet_name)

    def _get_or_create_worksheet(self, title: str, rows: int = 5000, cols: int = 10):
        try:
            return self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return self.spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

    def get_or_create_sheet(self, title: str, rows: int = 5000, cols: int = 10):
        return self._get_or_create_worksheet(title, rows=rows, cols=cols)

    def ensure_headers(self, title: str, headers: list[str]) -> None:
        ws = self._get_or_create_worksheet(title)
        current = ws.row_values(1)

        if current != headers:
            if not current:
                ws.update("A1", [headers])
            else:
                ws.delete_rows(1)
                ws.insert_row(headers, 1)

    def get_existing_invoice_numbers(self, sheet_name: str) -> set[str]:
        ws = self._get_or_create_worksheet(sheet_name)
        values = ws.get_all_values()

        invoice_nos = set()

        for row in values[1:]:
            if len(row) >= 4:
                invoice_no = row[3].strip()
                if invoice_no:
                    invoice_nos.add(invoice_no)

        return invoice_nos

    def append_rows(self, sheet_name: str, rows: list[list[str]]) -> None:
        if not rows:
            return

        ws = self._get_or_create_worksheet(sheet_name)
        ws.append_rows(rows, value_input_option="USER_ENTERED")

    def replace_sheet_data(self, title: str, headers: list[str], rows: list[list[str]]) -> None:
        ws = self._get_or_create_worksheet(title)
        all_values = [headers] + rows
        ws.clear()
        ws.update("A1", all_values)
