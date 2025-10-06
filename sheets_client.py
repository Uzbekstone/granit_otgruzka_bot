import json
import datetime as dt
from typing import Any, List
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

class Sheets:
    def __init__(self, spreadsheet_id: str, credentials_json: str):
        creds = Credentials.from_service_account_info(json.loads(credentials_json), scopes=SCOPES)
        gc = gspread.authorize(creds)
        self.sh = gc.open_by_key(spreadsheet_id)
        self.ws_data = self._get_or_create_ws("Otgruzka")

    def _get_or_create_ws(self, title: str):
        try:
            return self.sh.worksheet(title)
        except Exception:
            return self.sh.add_worksheet(title=title, rows=1000, cols=20)

    def append_otgruzka(self, row: List[Any]):
        header = [
            "Timestamp", "Sana", "Turi_razmer", "Miqdor_m2_uzunlik", "Paddon_soni",
            "Manzil", "Telefon", "Rasmlar_file_ids", "Yetkazish_summa", "Yuklagan_kim", "Operator"
        ]
        ws = self.ws_data
        values = ws.get_all_values()
        if not values or not values[0] or values[0][0] != "Timestamp":
            ws.clear()
            ws.append_row(header)
        ws.append_row(row)

    def read_between(self, start: dt.datetime, end: dt.datetime):
        ws = self.ws_data
        values = ws.get_all_values()
        if not values or values[0][0] != "Timestamp":
            return []
        rows = []
        for r in values[1:]:
            try:
                ts = dt.datetime.fromisoformat(r[0])
            except Exception:
                continue
            if start <= ts < end:
                rows.append(r)
        return rows
