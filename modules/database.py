import os
import json
import sqlite3
import csv
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "hd_control.db")
CONFIG_PATH = os.path.join(DB_DIR, "storage_config.json")


class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.config = self._load_config()
        self._init_db()
        self._cleanup_legacy_seed_data()
        self.resequence_drives()
        self.resequence_lab_inventory()

    def _load_config(self) -> dict:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "hds_file_path": None,
            "computers_file_path": None,
        }

    def save_config(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_hds_file_path(self) -> str:
        return self.config.get("hds_file_path")

    def set_hds_file_path(self, path: str):
        self.config["hds_file_path"] = path
        self.save_config()
        self.sync_hds_file()

    def get_computers_file_path(self) -> str:
        return self.config.get("computers_file_path")

    def set_computers_file_path(self, path: str):
        self.config["computers_file_path"] = path
        self.save_config()
        self.sync_computers_file()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Tabela de HDs / SSDs verificados (inicia sempre limpa em cada PC)
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

            # Tabela de Levantamento de Computadores / Periféricos (inicia sempre limpa em cada PC)
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

    def _cleanup_legacy_seed_data(self):
        """
        Remove registros estáticos antigos de exemplo caso estivessem presentes no banco local,
        garantindo que cada computador tenha apenas os dados que realmente cadastrar.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM drives WHERE serial IN ('HD-HIST-001', 'HD-HIST-002') AND notes LIKE '%Importado automaticamente de HDs.txt%'"
            )
            cursor.execute(
                "DELETE FROM lab_inventory WHERE notes IN ("
                "'Levantamento inicial importado do arquivo ''computadores''', "
                "'Nenhum funcionando inicialmente. Importado de ''computadores''', "
                "'Precisa: AMD Ryzen 7 2700 ou Ryzen 5 2400G | RAM DDR4 8GB 2400 | GPU RX 6400', "
                "'1 funcionando c/ problema (Tecla F9 travada). 3 sem funcionar (Sem pilha AAA+ e dongle).'"
                ")"
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

    def resequence_drives(self):
        """
        Reorganiza os IDs da tabela drives para que fiquem estritamente contínuos (1, 2, 3... N).
        Quando um HD intermediário é excluído, os HDs posteriores recuam imediatamente
        para ocupar o espaço vago e herdar a nova numeração sequencial sem pular números.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TEMP TABLE _drives_reseq AS SELECT * FROM drives ORDER BY id ASC;")
            cursor.execute("DELETE FROM drives;")
            cursor.execute("""
                INSERT INTO drives (
                    id, serial, model, vendor, capacity, drive_type, connection_bus,
                    device_node, smart_status, bad_sectors, power_on_hours, temperature,
                    status, assigned_machine, notes, last_tested, created_at
                )
                SELECT 
                    ROW_NUMBER() OVER (ORDER BY id ASC) as id,
                    serial, model, vendor, capacity, drive_type, connection_bus,
                    device_node, smart_status, bad_sectors, power_on_hours, temperature,
                    status, assigned_machine, notes, last_tested, created_at
                FROM _drives_reseq;
            """)
            cursor.execute("DROP TABLE _drives_reseq;")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'drives';")
            cursor.execute("INSERT INTO sqlite_sequence (name, seq) SELECT 'drives', COALESCE(MAX(id), 0) FROM drives;")
            conn.commit()

    def delete_drive(self, drive_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM drives WHERE id = ?", (drive_id,))
            conn.commit()
        # Resequencia os registros para preencher a vaga do HD excluído imediatamente
        self.resequence_drives()
        self.sync_legacy_files()

    def get_all_drives(self, filter_status=None, search_query=None, order_asc=True):
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
            order_clause = "ASC" if order_asc else "DESC"
            query += f" ORDER BY id {order_clause}"
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

    def resequence_lab_inventory(self):
        """
        Reorganiza os IDs da tabela lab_inventory para que fiquem estritamente contínuos (1, 2, 3... N).
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TEMP TABLE _lab_reseq AS SELECT * FROM lab_inventory ORDER BY id ASC;")
            cursor.execute("DELETE FROM lab_inventory;")
            cursor.execute("""
                INSERT INTO lab_inventory (
                    id, category, brand_model, total, working, not_working,
                    with_ram, without_ram, with_hdd, with_ssd, without_storage, notes, updated_at
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY id ASC) as id,
                    category, brand_model, total, working, not_working,
                    with_ram, without_ram, with_hdd, with_ssd, without_storage, notes, updated_at
                FROM _lab_reseq;
            """)
            cursor.execute("DROP TABLE _lab_reseq;")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'lab_inventory';")
            cursor.execute("INSERT INTO sqlite_sequence (name, seq) SELECT 'lab_inventory', COALESCE(MAX(id), 0) FROM lab_inventory;")
            conn.commit()

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
        self.resequence_lab_inventory()
        self.sync_legacy_files()

    def delete_lab_item(self, item_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM lab_inventory WHERE id = ?", (item_id,))
            conn.commit()
        self.resequence_lab_inventory()
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

    # --- EXPORT & DYNAMIC FILE SYNC ---
    def sync_legacy_files(self):
        """Sincroniza os arquivos dinâmicos de HDs e Computadores nos caminhos escolhidos pelo usuário."""
        self.sync_hds_file()
        self.sync_computers_file()

    def sync_hds_file(self, custom_path: str = None):
        """
        Gera/atualiza o arquivo de HDs limpo e dinâmico com base apenas nos HDs cadastrados neste PC.
        Suporta formato .csv ou .txt conforme o caminho escolhido pelo usuário.
        """
        target_path = custom_path or self.get_hds_file_path()
        if not target_path:
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
            if target_path.lower().endswith(".csv"):
                self.export_to_csv(target_path)
            else:
                stats = self.get_drive_stats()
                drives = self.get_all_drives(order_asc=True)
                lines = [
                    "=== CONTROLE DINÂMICO DE HDs / SSDs ===",
                    f"Atualizado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"HDs funcionando até o momento = {stats['working']}",
                    f"HDs com defeito = {stats['defective']}",
                    f"HDs em teste = {stats['testing']}",
                    f"Total de HDs registrados = {stats['total']}",
                    "",
                    "=== LISTA DE HDs / SSDs ===",
                ]
                if not drives:
                    lines.append("(Arquivo limpo — nenhum HD registrado até o momento)")
                else:
                    for idx, d in enumerate(drives, start=1):
                        lines.append(
                            f"#{idx} [{d['status']}] {d['model']} ({d['capacity']}) | S/N: {d['serial']} | SMART: {d['smart_status']} | BadSectors: {d['bad_sectors']} | Destino: {d['assigned_machine'] or 'Estoque'} | Obs: {d['notes']}"
                        )
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            return True
        except Exception:
            return False

    def sync_computers_file(self, custom_path: str = None):
        """
        Gera/atualiza o arquivo de Computadores limpo e dinâmico com base apenas nos lotes cadastrados neste PC.
        Suporta formato .csv ou .txt conforme o caminho escolhido pelo usuário.
        """
        target_path = custom_path or self.get_computers_file_path()
        if not target_path:
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
            if target_path.lower().endswith(".csv"):
                self.export_computers_to_csv(target_path)
            else:
                items = self.get_lab_inventory()
                total_pcs = sum(i["total"] for i in items if i["category"] == "Computador")
                working_pcs = sum(i["working"] for i in items if i["category"] == "Computador")
                no_storage_pcs = sum(i["without_storage"] for i in items if i["category"] == "Computador")
                lines = [
                    "=== LEVANTAMENTO DINÂMICO DE COMPUTADORES E PERIFÉRICOS ===",
                    f"Atualizado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"Total de Computadores = {total_pcs} | Funcionando = {working_pcs} | Sem HD/SSD = {no_storage_pcs}",
                    "",
                    "=== LOTES / BANCADA ===",
                ]
                if not items:
                    lines.append("(Arquivo limpo — nenhum computador ou periférico registrado até o momento)")
                else:
                    for idx, it in enumerate(items, start=1):
                        lines.append(
                            f"#{idx} [{it['category']}] {it['brand_model']} | Total: {it['total']} | Func: {it['working']} | Sem Func: {it['not_working']} | "
                            f"Com RAM: {it['with_ram']} | Sem RAM: {it['without_ram']} | Com HDD: {it['with_hdd']} | Com SSD: {it['with_ssd']} | Sem HD/SSD: {it['without_storage']} | Obs: {it['notes']}"
                        )
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            return True
        except Exception:
            return False

    def export_to_csv(self, filepath: str, filter_status=None, search_query=None):
        """
        Exporta a lista de HDs para CSV garantindo ordenação sequencial contínua (1, 2, 3... N).
        Qualquer HD excluído não é contabilizado e o próximo assume dinamicamente o número e o lugar.
        Usa utf-8-sig para compatibilidade direta com Excel e LibreOffice Calc.
        """
        drives = self.get_all_drives(filter_status=filter_status, search_query=search_query, order_asc=True)
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(
                [
                    "Nº",
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
            for idx, d in enumerate(drives, start=1):
                writer.writerow(
                    [
                        idx,
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
        return len(drives)

    def export_computers_to_csv(self, filepath: str):
        """
        Exporta a lista de Computadores e Periféricos para CSV garantindo numeração sequencial (1..N)
        e codificação UTF-8-BOM (utf-8-sig) compatível com Excel e LibreOffice Calc no Windows e Linux.
        """
        items = self.get_lab_inventory()
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(
                [
                    "Nº",
                    "ID",
                    "Categoria",
                    "Marca / Modelo",
                    "Total",
                    "Funcionando",
                    "Sem Funcionar",
                    "Com RAM",
                    "Sem RAM",
                    "Com HDD",
                    "Com SSD",
                    "Sem HD/SSD",
                    "Observações",
                    "Última Atualização",
                ]
            )
            for idx, it in enumerate(items, start=1):
                writer.writerow(
                    [
                        idx,
                        it["id"],
                        it["category"],
                        it["brand_model"],
                        it["total"],
                        it["working"],
                        it["not_working"],
                        it["with_ram"],
                        it["without_ram"],
                        it["with_hdd"],
                        it["with_ssd"],
                        it["without_storage"],
                        it["notes"],
                        it["updated_at"],
                    ]
                )
        return len(items)
