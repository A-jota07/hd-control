import os
import json
import sqlite3
import csv
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "hd_control.db")


class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()
        self._seed_initial_data_if_empty()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Tabela de HDs / SSDs verificados
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS drives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serial TEXT UNIQUE,
                    model TEXT,
                    vendor TEXT,
                    capacity TEXT,
                    drive_type TEXT, -- HDD, SSD, NVMe, USB
                    connection_bus TEXT, -- usb, sata, nvme
                    device_node TEXT,
                    smart_status TEXT, -- PASSED, FAILED, UNKNOWN
                    bad_sectors INTEGER DEFAULT 0,
                    power_on_hours INTEGER DEFAULT 0,
                    temperature REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'Em Teste', -- Funcionando, Com Defeito, Em Teste, Formatado, SO Instalado
                    assigned_machine TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    last_tested TEXT,
                    created_at TEXT
                )
            """)

            # Tabela de Levantamento de Computadores / Periféricos (importado de 'computadores' e 'HDs.txt')
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lab_inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT, -- Computador, Periférico, Meta
                    brand_model TEXT UNIQUE,
                    total INTEGER DEFAULT 0,
                    working INTEGER DEFAULT 0,
                    not_working INTEGER DEFAULT 0,
                    with_ram INTEGER DEFAULT 0,
                    without_ram INTEGER DEFAULT 0,
                    with_hdd INTEGER DEFAULT 0,
                    with_ssd INTEGER DEFAULT 0,
                    without_storage INTEGER DEFAULT 0,
                    notes TEXT DEFAULT '',
                    updated_at TEXT
                )
            """)

            # Histórico de Operações (Formatações, Testes, Gravações de SO, Cópias)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    device TEXT,
                    serial TEXT,
                    operation_type TEXT, -- SMART_TEST, FORMAT, ISO_FLASH, FILE_COPY, CLONE
                    status TEXT, -- SUCCESS, ERROR, INFO
                    details TEXT
                )
            """)
            conn.commit()

    def _seed_initial_data_if_empty(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM lab_inventory")
            if cursor.fetchone()["cnt"] == 0:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                initial_lab = [
                    (
                        "Computador",
                        "Dell (Bancada LEIA)",
                        35,
                        10,
                        25,
                        10,
                        24,
                        8,
                        12,
                        15,
                        "Levantamento inicial importado do arquivo 'computadores'",
                        now,
                    ),
                    (
                        "Computador",
                        "Bematech (Mini PC)",
                        6,
                        0,
                        6,
                        4,
                        2,
                        2,
                        1,
                        3,
                        "Nenhum funcionando inicialmente. Importado de 'computadores'",
                        now,
                    ),
                    (
                        "Computador",
                        "HP (Bancada)",
                        1,
                        0,
                        1,
                        0,
                        1,
                        0,
                        0,
                        1,
                        "Precisa: AMD Ryzen 7 2700 ou Ryzen 5 2400G | RAM DDR4 8GB 2400 | GPU RX 6400",
                        now,
                    ),
                    (
                        "Periférico",
                        "Teclados",
                        13,
                        10,
                        3,
                        0,
                        0,
                        0,
                        0,
                        0,
                        "1 funcionando c/ problema (Tecla F9 travada). 3 sem funcionar (Sem pilha AAA+ e dongle).",
                        now,
                    ),
                ]
                cursor.executemany(
                    """
                    INSERT INTO lab_inventory (
                        category, brand_model, total, working, not_working,
                        with_ram, without_ram, with_hdd, with_ssd, without_storage, notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    initial_lab,
                )

            # Verificar também se há HDs registrados. No arquivo HDs.txt constava "HDs funcionando até o momento = 2"
            cursor.execute("SELECT COUNT(*) as cnt FROM drives")
            if cursor.fetchone()["cnt"] == 0:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                initial_drives = [
                    (
                        "HD-HIST-001",
                        "HD Verificado #1 (Histórico HDs.txt)",
                        "Genérico",
                        "—",
                        "HDD",
                        "usb",
                        "",
                        "PASSED",
                        0,
                        0,
                        0.0,
                        "Funcionando",
                        "Estoque LEIA",
                        "Importado automaticamente de HDs.txt (HDs funcionando = 2)",
                        now,
                        now,
                    ),
                    (
                        "HD-HIST-002",
                        "HD Verificado #2 (Histórico HDs.txt)",
                        "Genérico",
                        "—",
                        "HDD",
                        "usb",
                        "",
                        "PASSED",
                        0,
                        0,
                        0.0,
                        "Funcionando",
                        "Estoque LEIA",
                        "Importado automaticamente de HDs.txt (HDs funcionando = 2)",
                        now,
                        now,
                    ),
                ]
                cursor.executemany(
                    """
                    INSERT INTO drives (
                        serial, model, vendor, capacity, drive_type, connection_bus,
                        device_node, smart_status, bad_sectors, power_on_hours, temperature,
                        status, assigned_machine, notes, last_tested, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    initial_drives,
                )
            conn.commit()

    # --- DRIVES CRUD ---
    def upsert_drive(self, drive_data: dict):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        serial = (drive_data.get("serial") or "").strip()
        if not serial:
            serial = f"NOSERIAL-{drive_data.get('model', 'DISK')}-{drive_data.get('device_node', 'dev')}"

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM drives WHERE serial = ?", (serial,))
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    """
                    UPDATE drives SET
                        model = COALESCE(?, model),
                        vendor = COALESCE(?, vendor),
                        capacity = COALESCE(?, capacity),
                        drive_type = COALESCE(?, drive_type),
                        connection_bus = COALESCE(?, connection_bus),
                        device_node = COALESCE(?, device_node),
                        smart_status = COALESCE(?, smart_status),
                        bad_sectors = COALESCE(?, bad_sectors),
                        power_on_hours = COALESCE(?, power_on_hours),
                        temperature = COALESCE(?, temperature),
                        status = COALESCE(?, status),
                        assigned_machine = COALESCE(?, assigned_machine),
                        notes = COALESCE(?, notes),
                        last_tested = ?
                    WHERE serial = ?
                """,
                    (
                        drive_data.get("model"),
                        drive_data.get("vendor"),
                        drive_data.get("capacity"),
                        drive_data.get("drive_type"),
                        drive_data.get("connection_bus"),
                        drive_data.get("device_node"),
                        drive_data.get("smart_status"),
                        drive_data.get("bad_sectors"),
                        drive_data.get("power_on_hours"),
                        drive_data.get("temperature"),
                        drive_data.get("status"),
                        drive_data.get("assigned_machine"),
                        drive_data.get("notes"),
                        now,
                        serial,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO drives (
                        serial, model, vendor, capacity, drive_type, connection_bus,
                        device_node, smart_status, bad_sectors, power_on_hours, temperature,
                        status, assigned_machine, notes, last_tested, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        serial,
                        drive_data.get("model", "Desconhecido"),
                        drive_data.get("vendor", ""),
                        drive_data.get("capacity", "—"),
                        drive_data.get("drive_type", "HDD"),
                        drive_data.get("connection_bus", "usb"),
                        drive_data.get("device_node", ""),
                        drive_data.get("smart_status", "UNKNOWN"),
                        drive_data.get("bad_sectors", 0),
                        drive_data.get("power_on_hours", 0),
                        drive_data.get("temperature", 0.0),
                        drive_data.get("status", "Em Teste"),
                        drive_data.get("assigned_machine", ""),
                        drive_data.get("notes", ""),
                        now,
                        now,
                    ),
                )
            conn.commit()
        self.sync_legacy_files()
        return serial

    def update_drive_by_id(self, drive_id: int, status: str, assigned_machine: str, notes: str, model: str = None, serial: str = None, capacity: str = None, drive_type: str = None):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE drives SET
                    status = ?,
                    assigned_machine = ?,
                    notes = ?,
                    model = COALESCE(?, model),
                    serial = COALESCE(?, serial),
                    capacity = COALESCE(?, capacity),
                    drive_type = COALESCE(?, drive_type),
                    last_tested = ?
                WHERE id = ?
            """,
                (status, assigned_machine, notes, model, serial, capacity, drive_type, now, drive_id),
            )
            conn.commit()
        self.sync_legacy_files()

    def delete_drive(self, drive_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM drives WHERE id = ?", (drive_id,))
            conn.commit()
        self.sync_legacy_files()

    def get_all_drives(self, filter_status=None, search_query=None):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM drives WHERE 1=1"
            params = []
            if filter_status and filter_status != "Todos":
                query += " AND status = ?"
                params.append(filter_status)
            if search_query:
                q = f"%{search_query}%"
                query += " AND (serial LIKE ? OR model LIKE ? OR assigned_machine LIKE ? OR notes LIKE ?)"
                params.extend([q, q, q, q])
            query += " ORDER BY id DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_drive_by_serial(self, serial: str):
        if not serial:
            return None
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM drives WHERE serial = ?", (serial,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_drive_stats(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM drives")
            total = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) as cnt FROM drives WHERE status IN ('Funcionando', 'Formatado', 'SO Instalado')")
            working = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM drives WHERE status = 'Com Defeito'")
            defective = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM drives WHERE status = 'Em Teste'")
            testing = cursor.fetchone()["cnt"]

            cursor.execute("SELECT SUM(without_storage) as needed FROM lab_inventory WHERE category = 'Computador'")
            row = cursor.fetchone()
            needed = row["needed"] if row and row["needed"] else 0

            return {
                "total": total,
                "working": working,
                "defective": defective,
                "testing": testing,
                "needed_for_pcs": needed,
            }

    # --- LAB INVENTORY CRUD ---
    def get_lab_inventory(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM lab_inventory ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def update_lab_item(self, item_id: int, data: dict):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE lab_inventory SET
                    brand_model = ?,
                    total = ?,
                    working = ?,
                    not_working = ?,
                    with_ram = ?,
                    without_ram = ?,
                    with_hdd = ?,
                    with_ssd = ?,
                    without_storage = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ?
            """,
                (
                    data["brand_model"],
                    int(data.get("total", 0)),
                    int(data.get("working", 0)),
                    int(data.get("not_working", 0)),
                    int(data.get("with_ram", 0)),
                    int(data.get("without_ram", 0)),
                    int(data.get("with_hdd", 0)),
                    int(data.get("with_ssd", 0)),
                    int(data.get("without_storage", 0)),
                    data.get("notes", ""),
                    now,
                    item_id,
                ),
            )
            conn.commit()
        self.sync_legacy_files()

    def add_lab_item(self, data: dict):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO lab_inventory (
                    category, brand_model, total, working, not_working,
                    with_ram, without_ram, with_hdd, with_ssd, without_storage, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    data.get("category", "Computador"),
                    data["brand_model"],
                    int(data.get("total", 0)),
                    int(data.get("working", 0)),
                    int(data.get("not_working", 0)),
                    int(data.get("with_ram", 0)),
                    int(data.get("without_ram", 0)),
                    int(data.get("with_hdd", 0)),
                    int(data.get("with_ssd", 0)),
                    int(data.get("without_storage", 0)),
                    data.get("notes", ""),
                    now,
                ),
            )
            conn.commit()
        self.sync_legacy_files()

    # --- LOGS ---
    def add_log(self, device: str, serial: str, operation_type: str, status: str, details: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO operation_logs (timestamp, device, serial, operation_type, status, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (now, device, serial, operation_type, status, details),
            )
            conn.commit()

    def get_logs(self, limit=100):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM operation_logs ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # --- EXPORT & LEGACY SYNC ---
    def sync_legacy_files(self):
        """Atualiza /home/junior/workspace/HDs.txt com o resumo atualizado para manter compatibilidade."""
        try:
            stats = self.get_drive_stats()
            drives = self.get_all_drives()
            hds_txt_path = "/home/junior/workspace/HDs.txt"
            lines = [
                f"HDs funcionando até o momento = {stats['working']}",
                f"HDs com defeito = {stats['defective']}",
                f"HDs em teste = {stats['testing']}",
                f"Total de HDs registrados = {stats['total']}",
                "",
                "=== LISTA DE HDs / SSDs ===",
            ]
            for d in drives:
                lines.append(
                    f"- [{d['status']}] {d['model']} ({d['capacity']}) | S/N: {d['serial']} | SMART: {d['smart_status']} | BadSectors: {d['bad_sectors']} | Destino: {d['assigned_machine'] or 'Estoque'} | Obs: {d['notes']}"
                )
            with open(hds_txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass

    def export_to_csv(self, filepath: str):
        drives = self.get_all_drives()
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "ID",
                    "Status",
                    "Modelo",
                    "Serial",
                    "Capacidade",
                    "Tipo",
                    "Barramento",
                    "Saúde SMART",
                    "Bad Sectors",
                    "Horas de Uso",
                    "Máquina/Destino",
                    "Observações",
                    "Último Teste",
                ]
            )
            for d in drives:
                writer.writerow(
                    [
                        d["id"],
                        d["status"],
                        d["model"],
                        d["serial"],
                        d["capacity"],
                        d["drive_type"],
                        d["connection_bus"],
                        d["smart_status"],
                        d["bad_sectors"],
                        d["power_on_hours"],
                        d["assigned_machine"],
                        d["notes"],
                        d["last_tested"],
                    ]
                )
