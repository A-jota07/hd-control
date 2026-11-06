"""
HD Control Studio - Módulo de Gerenciamento de Discos para Windows
Suporte nativo para detecção, diagnóstico SMART, formatação e testes em ambiente Windows.
"""

import os
import sys
import json
import shutil
import subprocess
from typing import List, Dict, Optional, Callable


class WindowsDiskManager:
    """Gerenciador de discos físicos e partições para plataforma Windows."""

    @staticmethod
    def _format_bytes(size: int) -> str:
        if size <= 0:
            return "0 B"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    @staticmethod
    def _run_ps(cmd: str, timeout: int = 15) -> str:
        """Executa um comando PowerShell e retorna a saída."""
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return res.stdout.strip()
        except Exception:
            return ""

    @staticmethod
    def _find_smartctl_exe() -> Optional[str]:
        """Procura o executável smartctl.exe no sistema Windows."""
        exe = shutil.which("smartctl")
        if exe:
            return exe
        candidates = [
            r"C:\Program Files\smartmontools\bin\smartctl.exe",
            r"C:\Program Files (x86)\smartmontools\bin\smartctl.exe",
            r"C:\Program Files\GSmartControl\smartctl.exe",
            r"C:\Program Files (x86)\GSmartControl\smartctl.exe",
            r"C:\ProgramData\chocolatey\bin\smartctl.exe",
            os.path.expanduser(r"~\scoop\apps\smartmontools\current\bin\smartctl.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    @classmethod
    def list_disks(cls, include_system_disks: bool = True) -> List[Dict]:
        """
        Lista todos os discos físicos no Windows usando PowerShell (Get-Disk e Get-Partition).
        Identifica discos USB, SATA, NVMe e partições montadas (C:, D:, etc.).
        """
        disks = []
        ps_cmd = (
            "Get-Disk | Select-Object Number, FriendlyName, SerialNumber, BusType, Size, "
            "HealthStatus, OperationalStatus, PartitionStyle, IsBoot, IsSystem | ConvertTo-Json -Depth 3"
        )
        output = cls._run_ps(ps_cmd, timeout=12)
        if not output:
            return disks

        try:
            raw = json.loads(output)
            disk_list = [raw] if isinstance(raw, dict) else raw
        except Exception:
            return disks

        # Mapeamento de partições e letras de unidade
        parts_cmd = "Get-Partition | Select-Object DiskNumber, PartitionNumber, DriveLetter, Size, Type | ConvertTo-Json -Depth 3"
        parts_out = cls._run_ps(parts_cmd, timeout=10)
        part_map = {}
        try:
            if parts_out:
                praw = json.loads(parts_out)
                plist = [praw] if isinstance(praw, dict) else praw
                for p in plist:
                    d_num = p.get("DiskNumber")
                    if d_num not in part_map:
                        part_map[d_num] = []
                    letter = p.get("DriveLetter") or ""
                    part_map[d_num].append({
                        "name": f"Partição {p.get('PartitionNumber')}" + (f" ({letter}:)" if letter else ""),
                        "path": f"{letter}:" if letter else f"Disk{d_num}Part{p.get('PartitionNumber')}",
                        "size": cls._format_bytes(int(p.get("Size") or 0)),
                        "fstype": p.get("Type") or "NTFS",
                        "label": f"Unidade {letter}:" if letter else "",
                        "mountpoints": [f"{letter}:\\"] if letter else [],
                    })
        except Exception:
            pass

        for d in disk_list:
            number = d.get("Number", 0)
            model = (d.get("FriendlyName") or f"Disco Físico #{number}").strip()
            serial = (d.get("SerialNumber") or f"WIN-DISK-{number}").strip()
            bus_type = str(d.get("BusType") or "").lower()
            size_bytes = int(d.get("Size") or 0)
            is_boot = bool(d.get("IsBoot") or d.get("IsSystem"))

            is_external = bus_type in ["usb", "1394", "sd", "mmc"]
            is_system = is_boot

            if not include_system_disks and is_system:
                continue

            if "nvme" in bus_type or "nvme" in model.lower():
                drive_type = "NVMe"
            elif is_external:
                drive_type = "HDD (USB)" if "hdd" in model.lower() else "USB Drive"
            elif "ssd" in model.lower():
                drive_type = "SSD"
            else:
                drive_type = "HDD"

            health = str(d.get("HealthStatus") or "Healthy").upper()
            if health in ["HEALTHY", "OK"]:
                smart_status = "PASSED"
            elif health in ["WARNING", "DEGRADED"]:
                smart_status = "WARN"
            else:
                smart_status = "FAILED" if health != "" else "N/D"

            disks.append({
                "name": f"PhysicalDrive{number}",
                "path": f"\\\\.\\PhysicalDrive{number}",
                "model": model,
                "vendor": "Windows Storage",
                "serial": serial,
                "size_bytes": size_bytes,
                "size_human": cls._format_bytes(size_bytes),
                "tran": bus_type or ("usb" if is_external else "sata"),
                "rota": "hdd" in drive_type.lower(),
                "rm": is_external,
                "hotplug": is_external,
                "is_external": is_external,
                "is_system": is_system,
                "drive_type": drive_type,
                "ptype": str(d.get("PartitionStyle") or "GPT").upper(),
                "smart_status": smart_status,
                "bad_sectors": 0,
                "power_on_hours": 0,
                "temperature_c": 0.0,
                "selftest_status": "",
                "partitions": part_map.get(number, []),
            })

        # Discos externos USB no topo
        disks.sort(key=lambda x: (not x["is_external"], x["is_system"], x["name"]))
        return disks

    @classmethod
    def run_detailed_smart_check(cls, device_path: str) -> Dict:
        """
        Executa diagnóstico SMART no Windows.
        Se smartctl.exe estiver presente, obtém os dados detalhados.
        Caso contrário, consulta o contador de confiabilidade do Windows (Get-StorageReliabilityCounter).
        """
        parsed = {
            "smart_status": "UNKNOWN",
            "bad_sectors": 0,
            "power_on_hours": 0,
            "temperature_c": 0.0,
            "model": None,
            "serial": None,
            "raw_report": "",
        }

        # Extrai número do disco físico se o caminho for \\.\PhysicalDriveN
        disk_number = 0
        if "PhysicalDrive" in device_path:
            try:
                disk_number = int(device_path.split("PhysicalDrive")[-1])
            except ValueError:
                pass

        smartctl = cls._find_smartctl_exe()
        if smartctl:
            target = f"/dev/pd{disk_number}"
            res_json = subprocess.run([smartctl, "-a", "-j", target], capture_output=True, text=True)
            res_txt = subprocess.run([smartctl, "-H", "-A", "-i", target], capture_output=True, text=True)
            raw_text = res_txt.stdout if res_txt.stdout.strip() else res_json.stdout
            parsed["raw_report"] = raw_text

            try:
                data = json.loads(res_json.stdout)
                if "model_name" in data:
                    parsed["model"] = data["model_name"]
                if "serial_number" in data:
                    parsed["serial"] = data["serial_number"]
                if "smart_status" in data and "passed" in data["smart_status"]:
                    parsed["smart_status"] = "PASSED" if data["smart_status"]["passed"] else "FAILED"
                if "temperature" in data and "current" in data["temperature"]:
                    parsed["temperature_c"] = float(data["temperature"]["current"])
                if "power_on_time" in data and "hours" in data["power_on_time"]:
                    parsed["power_on_hours"] = int(data["power_on_time"]["hours"])

                bad = 0
                for attr in data.get("ata_smart_attributes", {}).get("table", []):
                    aid = attr.get("id")
                    raw_val = attr.get("raw", {}).get("value", 0)
                    if aid in (5, 197, 198) and isinstance(raw_val, int):
                        bad += raw_val
                parsed["bad_sectors"] = bad
                if bad > 0 and parsed["smart_status"] == "PASSED":
                    parsed["smart_status"] = f"WARN ({bad} Bad Sectors)"
                return parsed
            except Exception:
                pass

        # Fallback nativo via PowerShell (sem exigir instalação de smartmontools)
        ps_cmd = f"Get-PhysicalDisk | Where-Object {{ $_.DeviceId -eq '{disk_number}' }} | Select-Object FriendlyName, SerialNumber, HealthStatus, OperationalStatus, CannotPoolReason | ConvertTo-Json"
        ps_out = cls._run_ps(ps_cmd)
        
        counter_cmd = f"Get-StorageReliabilityCounter -DiskNumber {disk_number} | Select-Object Temperature, ReadErrorsTotal, WriteErrorsTotal, Wear | ConvertTo-Json"
        counter_out = cls._run_ps(counter_cmd)

        model = f"PhysicalDrive #{disk_number}"
        serial = f"WIN-{disk_number}"
        health_status = "PASSED"
        temp = 0.0
        bad_sectors = 0

        try:
            if ps_out:
                ddata = json.loads(ps_out)
                model = ddata.get("FriendlyName") or model
                serial = ddata.get("SerialNumber") or serial
                h = str(ddata.get("HealthStatus") or "").upper()
                if h in ["WARNING", "DEGRADED"]:
                    health_status = "WARN"
                elif h in ["UNHEALTHY", "FAILED"]:
                    health_status = "FAILED"
        except Exception:
            pass

        try:
            if counter_out:
                cdata = json.loads(counter_out)
                temp = float(cdata.get("Temperature") or 0.0)
                bad_sectors = int(cdata.get("ReadErrorsTotal") or 0) + int(cdata.get("WriteErrorsTotal") or 0)
        except Exception:
            pass

        report_lines = [
            "=" * 78,
            "DIAGNÓSTICO TÉCNICO DE CONFIABILIDADE (Windows Storage Subsystem)",
            "=" * 78,
            f"Dispositivo:         \\\\.\\PhysicalDrive{disk_number}",
            f"Modelo:              {model}",
            f"Serial:              {serial}",
            f"Status de Saúde:     {health_status}",
            f"Erros de I/O / Bad:  {bad_sectors}",
            f"Temperatura:         {temp} °C" if temp > 0 else "Temperatura:         N/D",
            "=" * 78,
            "[DICA] Para relatório completo SMART com todos os atributos de fabricante no Windows,",
            "       instale o pacote smartmontools: winget install smartmontools",
            "=" * 78,
        ]

        parsed["smart_status"] = health_status
        parsed["model"] = model
        parsed["serial"] = serial
        parsed["temperature_c"] = temp
        parsed["bad_sectors"] = bad_sectors
        parsed["raw_report"] = "\n".join(report_lines)
        return parsed

    @classmethod
    def run_quick_surface_test(cls, device_path: str, progress_cb: Optional[Callable[[str], None]] = None) -> Dict:
        """
        Executa teste rápido de leitura de blocos I/O no Windows.
        Lê 128 MB diretamente do disco físico ou volume sem travar.
        """
        if progress_cb:
            progress_cb(f"Iniciando teste de leitura de blocos I/O em {device_path}...")

        disk_number = 0
        if "PhysicalDrive" in device_path:
            try:
                disk_number = int(device_path.split("PhysicalDrive")[-1])
            except ValueError:
                pass

        # Executa teste de leitura de blocos via PowerShell
        ps_test = f"""
        $stream = [System.IO.File]::Open("{device_path}", [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $buffer = New-Object byte[] (1024 * 1024)
        $totalRead = 0
        for ($i = 0; $i -lt 128; $i++) {{
            $read = $stream.Read($buffer, 0, $buffer.Length)
            if ($read -le 0) {{ break }}
            $totalRead += $read
        }}
        $stream.Close()
        Write-Output "OK:$totalRead"
        """
        out = cls._run_ps(ps_test, timeout=20)
        if "OK:" in out:
            return {
                "success": True,
                "message": "Teste de leitura direta (128 MB) concluído com sucesso no Windows! O disco responde sem erros de I/O.",
            }
        else:
            return {
                "success": False,
                "message": f"Aviso de leitura em {device_path}:\nPara acesso direto a blocos brutos em PhysicalDrive no Windows, execute o aplicativo como Administrador.",
            }

    @classmethod
    def format_disk(
        cls,
        device_path: str,
        fs_type: str,
        label: str,
        partition_table: str = "gpt",
        is_system: bool = False,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """
        Formata um disco no Windows via script diskpart ou PowerShell Clear-Disk / Format-Volume.
        Garante bloqueio contra formatação acidental de discos de sistema.
        """
        if is_system:
            return {
                "success": False,
                "message": "Operação abortada: Este disco foi detectado como Disco de Sistema (Windows Boot).",
            }

        disk_number = None
        if "PhysicalDrive" in device_path:
            try:
                disk_number = int(device_path.split("PhysicalDrive")[-1])
            except ValueError:
                pass

        if disk_number is None:
            return {"success": False, "message": f"Identificador de disco inválido: {device_path}"}

        fs_map = {
            "ext4": "ntfs",  # Windows nativo não suporta criar ext4 direto
            "ntfs": "ntfs",
            "fat32": "fat32",
            "vfat": "fat32",
            "exfat": "exfat",
        }
        win_fs = fs_map.get(fs_type.lower(), "ntfs")
        clean_label = "".join(c for c in label if c.isalnum() or c in "_-")[:11] or "HD_CONTROL"

        if progress_cb:
            progress_cb(f"Preparando script diskpart para limpar e formatar Disco #{disk_number} em {win_fs.upper()}...")

        script_content = f"""select disk {disk_number}
clean
convert {partition_table.lower()}
create partition primary
format fs={win_fs} label="{clean_label}" quick
assign
exit
"""
        script_file = os.path.join(os.environ.get("TEMP", "C:\\Temp"), f"diskpart_hdcontrol_{disk_number}.txt")
        try:
            with open(script_file, "w", encoding="ascii") as f:
                f.write(script_content)

            res = subprocess.run(["diskpart", "/s", script_file], capture_output=True, text=True, timeout=60)
            if os.path.exists(script_file):
                os.remove(script_file)

            if res.returncode == 0 and "successfully" in res.stdout.lower() or "sucesso" in res.stdout.lower():
                return {
                    "success": True,
                    "message": f"Disco #{disk_number} formatado com sucesso em {win_fs.upper()} (Tabela {partition_table.upper()}, Rótulo '{clean_label}').",
                }
            else:
                return {
                    "success": False,
                    "message": f"Diskpart finalizou com aviso/erro:\n{res.stdout}\n{res.stderr}",
                }
        except Exception as e:
            return {"success": False, "message": f"Falha ao executar formatação via diskpart: {e}"}
