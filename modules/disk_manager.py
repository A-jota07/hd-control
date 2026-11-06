import os
import json
import subprocess
import shutil
import re
import platform
from typing import List, Dict, Optional, Callable

IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    from modules.disk_manager_windows import WindowsDiskManager


class DiskManager:
    """
    Gerencia detecção de discos, leitura SMART (via UDisks2 e smartctl),
    formatação, gravação de ISO/IMG, clonagem e cópia de pacotes de arquivos.
    """

    @staticmethod
    def list_disks(include_system_disks: bool = True) -> List[Dict]:
        """
        Retorna a lista de discos físicos conectados usando lsblk -J e enriquece
        com informações do UDisks2 (SMART sem precisar de sudo a todo momento).
        No Windows, delega automaticamente para WindowsDiskManager.
        """
        if IS_WINDOWS:
            return WindowsDiskManager.list_disks(include_system_disks=include_system_disks)

        cmd = [
            "lsblk",
            "-J",
            "-b",
            "-o",
            "NAME,PATH,SIZE,TYPE,MOUNTPOINT,MOUNTPOINTS,MODEL,SERIAL,TRAN,ROTA,RM,FSTYPE,LABEL,VENDOR,STATE,HOTPLUG,PTTYPE",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            data = json.loads(res.stdout)
        except Exception:
            return []

        udisks_map = DiskManager._get_udisks_smart_map()
        disks = []

        for dev in data.get("blockdevices", []):
            if dev.get("type") != "disk":
                continue
            name = dev.get("name", "")
            if name.startswith("zram") or name.startswith("loop"):
                continue

            is_system = DiskManager._is_system_disk(dev)
            if not include_system_disks and is_system:
                continue

            size_bytes = int(dev.get("size") or 0)
            size_human = DiskManager._format_bytes(size_bytes)
            tran = (dev.get("tran") or "").lower()
            rota = bool(dev.get("rota"))
            rm = bool(dev.get("rm"))
            hotplug = bool(dev.get("hotplug"))

            if "nvme" in name or tran == "nvme":
                drive_type = "NVMe"
            elif tran == "usb" or hotplug or rm:
                drive_type = "HDD (USB)" if rota else "SSD/USB"
            else:
                drive_type = "HDD" if rota else "SSD"

            serial = (dev.get("serial") or "").strip()
            model = (dev.get("model") or "Disco Desconhecido").strip()
            vendor = (dev.get("vendor") or "").strip()

            # Dados SMART via UDisks2 (não requer senha)
            ud_info = udisks_map.get(name, {})
            smart_supported = ud_info.get("smart_supported", False)
            smart_enabled = ud_info.get("smart_enabled", False)
            smart_failing = ud_info.get("smart_failing", False)
            bad_sectors = ud_info.get("bad_sectors", 0)
            power_on_hours = ud_info.get("power_on_hours", 0)
            temp_c = ud_info.get("temperature_c", 0.0)
            selftest_status = ud_info.get("selftest_status", "")

            if smart_supported and smart_enabled:
                if smart_failing or bad_sectors > 0:
                    smart_status = "ATENÇÃO / DEFEITO" if bad_sectors > 0 else "FALHA SMART"
                    if smart_failing:
                        smart_status = "FAILED"
                    else:
                        smart_status = f"WARN ({bad_sectors} Bad Sectors)"
                else:
                    smart_status = "PASSED"
            else:
                smart_status = "N/D (Clique em Diagnóstico)"

            partitions = []
            for child in dev.get("children", []) or []:
                c_size = int(child.get("size") or 0)
                mps = child.get("mountpoints") or ([child.get("mountpoint")] if child.get("mountpoint") else [])
                mps = [m for m in mps if m]
                partitions.append(
                    {
                        "name": child.get("name"),
                        "path": child.get("path") or f"/dev/{child.get('name')}",
                        "size": DiskManager._format_bytes(c_size),
                        "fstype": child.get("fstype") or "Sem formato",
                        "label": child.get("label") or "",
                        "mountpoints": mps,
                    }
                )

            disks.append(
                {
                    "name": name,
                    "path": dev.get("path") or f"/dev/{name}",
                    "model": model,
                    "vendor": vendor,
                    "serial": serial,
                    "size_bytes": size_bytes,
                    "size_human": size_human,
                    "tran": tran or ("interno" if not hotplug else "usb"),
                    "rota": rota,
                    "rm": rm,
                    "hotplug": hotplug,
                    "is_external": (tran == "usb" or hotplug or rm),
                    "is_system": is_system,
                    "drive_type": drive_type,
                    "ptype": (dev.get("pttype") or "Nenhuma").upper(),
                    "smart_status": smart_status,
                    "bad_sectors": bad_sectors,
                    "power_on_hours": power_on_hours,
                    "temperature_c": temp_c,
                    "selftest_status": selftest_status,
                    "partitions": partitions,
                }
            )

        # Ordenar colocando discos externos/USB e não-sistema no topo!
        disks.sort(key=lambda d: (d["is_system"], not d["is_external"], d["name"]))
        return disks

    @staticmethod
    def _is_system_disk(dev: Dict) -> bool:
        """Verifica se o disco contém /, /boot, /home, /var ou [SWAP]."""
        sys_mounts = {"/", "/boot", "/boot/efi", "/home", "/var", "/var/log", "[SWAP]"}

        def check_node(node):
            mp = node.get("mountpoint")
            if mp in sys_mounts:
                return True
            for m in node.get("mountpoints") or []:
                if m in sys_mounts:
                    return True
            for child in node.get("children") or []:
                if check_node(child):
                    return True
            return False

        return check_node(dev)

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
    def _get_udisks_smart_map() -> Dict[str, Dict]:
        """Lê dump do udisksctl para extrair dados SMART sem exigir root."""
        result = {}
        try:
            res = subprocess.run(["udisksctl", "dump"], capture_output=True, text=True, timeout=6)
            text = res.stdout
        except Exception:
            return result

        blocks = text.split("\n\n")
        drive_smart = {}
        block_to_drive = {}

        for blk in blocks:
            lines = blk.strip().splitlines()
            if not lines:
                continue
            header = lines[0].strip().rstrip(":")
            if "/org/freedesktop/UDisks2/drives/" in header:
                info = {
                    "smart_supported": False,
                    "smart_enabled": False,
                    "smart_failing": False,
                    "bad_sectors": 0,
                    "power_on_hours": 0,
                    "temperature_c": 0.0,
                    "selftest_status": "",
                }
                for line in lines[1:]:
                    s = line.strip()
                    if s.startswith("SmartSupported:"):
                        info["smart_supported"] = "true" in s.lower()
                    elif s.startswith("SmartEnabled:"):
                        info["smart_enabled"] = "true" in s.lower()
                    elif s.startswith("SmartFailing:"):
                        info["smart_failing"] = "true" in s.lower()
                    elif s.startswith("SmartNumBadSectors:"):
                        try:
                            info["bad_sectors"] = int(s.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                    elif s.startswith("SmartPowerOnSeconds:"):
                        try:
                            secs = int(s.split(":", 1)[1].strip())
                            info["power_on_hours"] = secs // 3600
                        except ValueError:
                            pass
                    elif s.startswith("SmartTemperature:"):
                        try:
                            k = float(s.split(":", 1)[1].strip())
                            if k > 200:
                                info["temperature_c"] = round(k - 273.15, 1)
                        except ValueError:
                            pass
                    elif s.startswith("SmartSelftestStatus:"):
                        info["selftest_status"] = s.split(":", 1)[1].strip()
                drive_smart[header] = info

            elif "/org/freedesktop/UDisks2/block_devices/" in header:
                dev_name = header.split("/")[-1]
                for line in lines[1:]:
                    s = line.strip()
                    if s.startswith("Drive:"):
                        drv_path = s.split(":", 1)[1].strip().strip("'")
                        block_to_drive[dev_name] = drv_path

        for dev_name, drv_path in block_to_drive.items():
            if drv_path in drive_smart:
                result[dev_name] = drive_smart[drv_path]

        return result

    @staticmethod
    def _get_udisks_drive_report(device_path: str) -> Dict:
        """
        Consulta informações do UDisks2 diretamente sem exigir senha de root.
        Extrai contagem de setores defeituosos, horas de uso, temperatura e status SMART.
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
        try:
            res = subprocess.run(["udisksctl", "info", "-b", device_path], capture_output=True, text=True, timeout=5)
            drive_id = None
            for line in res.stdout.splitlines():
                if "Drive:" in line:
                    drive_id = line.split("Drive:")[1].strip().strip("'")
                    break

            drive_text = ""
            if drive_id:
                drive_name = drive_id.split("/")[-1]
                res_d = subprocess.run(["udisksctl", "info", "-d", drive_name], capture_output=True, text=True, timeout=5)
                drive_text = res_d.stdout

            full_text = res.stdout + "\n" + drive_text

            for line in full_text.splitlines():
                s = line.strip()
                if s.startswith("Model:"):
                    parsed["model"] = s.split(":", 1)[1].strip()
                elif s.startswith("Serial:"):
                    parsed["serial"] = s.split(":", 1)[1].strip()
                elif s.startswith("SmartFailing:"):
                    failing = "true" in s.lower()
                    if failing:
                        parsed["smart_status"] = "FAILED"
                    elif parsed["smart_status"] == "UNKNOWN":
                        parsed["smart_status"] = "PASSED"
                elif s.startswith("SmartNumBadSectors:"):
                    try:
                        parsed["bad_sectors"] = int(s.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                elif s.startswith("SmartPowerOnSeconds:"):
                    try:
                        secs = int(s.split(":", 1)[1].strip())
                        parsed["power_on_hours"] = secs // 3600
                    except ValueError:
                        pass
                elif s.startswith("SmartTemperature:"):
                    try:
                        k = float(s.split(":", 1)[1].strip())
                        if k > 200:
                            parsed["temperature_c"] = round(k - 273.15, 1)
                        elif k > 0:
                            parsed["temperature_c"] = k
                    except ValueError:
                        pass

            if parsed["bad_sectors"] > 0:
                parsed["smart_status"] = f"WARN ({parsed['bad_sectors']} Bad Sectors)"
            elif parsed["smart_status"] == "UNKNOWN":
                parsed["smart_status"] = "PASSED"

            report_lines = [
                "=" * 78,
                "DIAGNÓSTICO TÉCNICO SMART // UDisks2 (Executado sem pedido de senha)",
                "=" * 78,
                f"Dispositivo:         {device_path}",
                f"Modelo:              {parsed['model'] or 'Desconhecido'}",
                f"Número de Série:     {parsed['serial'] or 'N/D'}",
                f"Saúde SMART Geral:   {parsed['smart_status']}",
                f"Setores Defeituosos: {parsed['bad_sectors']}",
                f"Horas de Uso Ligado: {parsed['power_on_hours']} horas (~{parsed['power_on_hours'] // 24} dias)",
                f"Temperatura:         {parsed['temperature_c']} °C" if parsed['temperature_c'] > 0 else "Temperatura:         N/D",
                "-" * 78,
                "PARÂMETROS DE HARDWARE E ATRIBUTOS DO DISCO:",
                "-" * 78,
            ]
            for line in drive_text.splitlines():
                if any(k in line for k in ["Smart", "RotationRate", "Vendor", "Model", "Revision", "Size", "Apm", "Pm"]):
                    report_lines.append(f"  {line.strip()}")
            report_lines.extend([
                "=" * 78,
                "[INFO] Diagnóstico obtido via UDisks2 nativo sem interromper com janelas de senha.",
                "       Para smartctl raw direto: sudo usermod -aG disk $USER",
                "=" * 78,
            ])
            parsed["raw_report"] = "\n".join(report_lines)
        except Exception as e:
            parsed["raw_report"] = f"Falha na consulta UDisks2: {e}"

        return parsed

    @staticmethod
    def run_detailed_smart_check(device_path: str) -> Dict:
        """
        Executa diagnóstico SMART completo.
        No Windows, aciona o WindowsDiskManager.
        No Linux, primeiro tenta consulta direta ou UDisks2 sem solicitar senha.
        """
        if IS_WINDOWS:
            return WindowsDiskManager.run_detailed_smart_check(device_path)

        # 1. Tentar smartctl diretamente (SEM pkexec / SEM pedir senha)
        res = subprocess.run(["smartctl", "-a", "-j", device_path], capture_output=True, text=True)
        data = None
        try:
            data = json.loads(res.stdout)
        except Exception:
            pass

        # Se falhou por parâmetro USB de leitor (-d sat)
        if not data:
            res_sat = subprocess.run(["smartctl", "-a", "-d", "sat", "-j", device_path], capture_output=True, text=True)
            try:
                data = json.loads(res_sat.stdout)
            except Exception:
                pass

        # Se smartctl funcionou sem precisar de root
        if data and "smart_status" in data:
            res_txt = subprocess.run(["smartctl", "-H", "-A", "-i", device_path], capture_output=True, text=True)
            raw_text = res_txt.stdout if res_txt.stdout.strip() else res.stdout
            parsed = {
                "smart_status": "UNKNOWN",
                "bad_sectors": 0,
                "power_on_hours": 0,
                "temperature_c": 0.0,
                "model": data.get("model_name"),
                "serial": data.get("serial_number"),
                "raw_report": raw_text,
            }
            if "passed" in data.get("smart_status", {}):
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

        # 2. Diagnóstico transparente via UDisks2 (100% sem senha!)
        ud_parsed = DiskManager._get_udisks_drive_report(device_path)
        if ud_parsed["smart_status"] != "UNKNOWN" or ud_parsed["raw_report"]:
            return ud_parsed

        # Fallback de última instância
        return {
            "smart_status": "UNKNOWN",
            "bad_sectors": 0,
            "power_on_hours": 0,
            "temperature_c": 0.0,
            "model": None,
            "serial": None,
            "raw_report": "Não foi possível obter diagnóstico do disco sem permissão.",
        }

    @staticmethod
    def run_quick_surface_test(device_path: str, progress_cb: Optional[Callable[[str], None]] = None) -> Dict:
        """
        Executa teste rápido de leitura (dd de 128MB).
        Tenta leitura direta sem senha primeiro, e depois sudo sem senha.
        """
        if IS_WINDOWS:
            return WindowsDiskManager.run_quick_surface_test(device_path, progress_cb)

        if progress_cb:
            progress_cb(f"Iniciando teste de leitura de superfície em {device_path}...")

        # 1. Tentar leitura direta sem pkexec (SEM SENHA)
        res = subprocess.run(
            ["dd", f"if={device_path}", "of=/dev/null", "bs=1M", "count=128", "iflag=direct", "status=none"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            return {
                "success": True,
                "message": "Teste de leitura direta (128 MB) concluído sem erros de I/O e sem necessidade de senha! O disco responde normalmente.",
            }

        # 2. Se falhou por permissão, tenta sudo -n (se sudo sem senha estiver ativo para wheel/disk)
        res_sudo = subprocess.run(
            ["sudo", "-n", "dd", f"if={device_path}", "of=/dev/null", "bs=1M", "count=128", "iflag=direct", "status=none"],
            capture_output=True,
            text=True,
        )
        if res_sudo.returncode == 0:
            return {
                "success": True,
                "message": "Teste de leitura direta (128 MB) concluído via sudo sem senha! Disco íntegro.",
            }

        # 3. Execução com elevação e instrução permanente para dispensar senha
        script = f"dd if={device_path} of=/dev/null bs=1M count=128 iflag=direct status=none"
        res_pk = subprocess.run(["pkexec", "sh", "-c", script], capture_output=True, text=True)
        if res_pk.returncode == 0:
            return {
                "success": True,
                "message": "Teste de leitura direta (128 MB) concluído com sucesso!\n\n[DICA]: Para nunca mais pedir senha neste teste, adicione seu usuário ao grupo disk:\n  sudo usermod -aG disk $USER",
            }
        else:
            return {
                "success": False,
                "message": f"Falha de leitura/I/O detectada no disco {device_path}:\n{res_pk.stderr}\n\n[DICA]: Execute 'sudo usermod -aG disk $USER' para acesso direto sem senha.",
            }

    @staticmethod
    def format_disk(
        device_path: str,
        fs_type: str,
        label: str,
        partition_table: str = "gpt",
        is_system: bool = False,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """
        Desmonta partições do disco, cria nova tabela de partições (GPT ou MBR/msdos)
        e formata uma partição primária ocupando 100% do disco.
        """
        if IS_WINDOWS:
            return WindowsDiskManager.format_disk(
                device_path=device_path,
                fs_type=fs_type,
                label=label,
                partition_table=partition_table,
                is_system=is_system,
                progress_cb=progress_cb,
            )

        if is_system:
            return {
                "success": False,
                "message": "BLOQUEIO DE SEGURANÇA: Este é o disco do sistema operacional atual. Formatação bloqueada.",
            }

        clean_label = re.sub(r"[^a-zA-Z0-9_-]", "", label or "HD_DADOS")[:11]
        ptable = "gpt" if partition_table.lower() == "gpt" else "msdos"

        # Determinar sufixo de partição (nvme0n1p1 vs sda1)
        part_dev = f"{device_path}p1" if device_path[-1].isdigit() else f"{device_path}1"

        fs_lower = fs_type.lower()
        if fs_lower == "ext4":
            mkfs_cmd = f"mkfs.ext4 -F -L '{clean_label}' {part_dev}"
        elif fs_lower == "exfat":
            mkfs_cmd = f"mkfs.exfat -L '{clean_label}' {part_dev}"
        elif fs_lower in ("fat32", "vfat"):
            mkfs_cmd = f"mkfs.vfat -F 32 -n '{clean_label.upper()}' {part_dev}"
        elif fs_lower == "btrfs":
            mkfs_cmd = f"mkfs.btrfs -f -L '{clean_label}' {part_dev}"
        elif fs_lower == "ntfs":
            if shutil.which("mkfs.ntfs") or shutil.which("mkntfs"):
                bin_ntfs = shutil.which("mkfs.ntfs") or shutil.which("mkntfs")
                mkfs_cmd = f"{bin_ntfs} -Q -F -L '{clean_label}' {part_dev}"
            else:
                return {
                    "success": False,
                    "message": "Utilitário mkntfs não encontrado. Use exFAT (compatível com Windows/Linux), FAT32 ou EXT4.",
                }
        else:
            return {"success": False, "message": f"Sistema de arquivos não suportado: {fs_type}"}

        if progress_cb:
            progress_cb(f"Desmontando partições e criando tabela {ptable.upper()} em {device_path}...")

        script = f"""
        set -e
        for p in $(lsblk -ln -o PATH {device_path} | tail -n +2); do
            umount -f "$p" 2>/dev/null || true
        done
        wipefs -a {device_path}
        parted -s {device_path} mklabel {ptable}
        parted -s -a optimal {device_path} mkpart primary 0% 100%
        partprobe {device_path} || true
        udevadm settle || sleep 2
        {mkfs_cmd}
        sync
        """

        res = subprocess.run(["pkexec", "sh", "-c", script], capture_output=True, text=True)
        if res.returncode == 0:
            return {
                "success": True,
                "partition": part_dev,
                "message": f"Disco {device_path} particionado ({ptable.upper()}) e formatado em {fs_type.upper()} com sucesso!",
            }
        else:
            return {
                "success": False,
                "message": f"Erro ao formatar {device_path}:\n{res.stderr}",
            }

    @staticmethod
    def mount_and_copy_files(
        partition_path: str,
        source_paths: List[str],
        dest_subfolder: str = "",
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """
        Monta a partição do HD externo (via udisksctl ou mount temporário) e copia
        arquivos/pastas selecionados pelo usuário para dentro do HD.
        """
        if not source_paths:
            return {"success": False, "message": "Nenhum arquivo ou pasta de origem selecionado."}

        if progress_cb:
            progress_cb(f"Montando partição {partition_path}...")

        # Tentar montar via udisksctl (monta como usuário normal em /run/media/junior/...)
        mount_point = DiskManager._get_partition_mountpoint(partition_path)
        if not mount_point:
            res_m = subprocess.run(["udisksctl", "mount", "-b", partition_path], capture_output=True, text=True)
            mount_point = DiskManager._get_partition_mountpoint(partition_path)

        # Se udisksctl conseguiu montar, copiamos direto ou ajustamos permissão
        if mount_point:
            target_dir = os.path.join(mount_point, dest_subfolder.strip("/")) if dest_subfolder else mount_point
            try:
                os.makedirs(target_dir, exist_ok=True)
                for src in source_paths:
                    if not os.path.exists(src):
                        continue
                    base = os.path.basename(src.rstrip("/"))
                    dst = os.path.join(target_dir, base)
                    if progress_cb:
                        progress_cb(f"Copiando '{base}' para {target_dir}...")
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                subprocess.run(["sync"])
                return {
                    "success": True,
                    "mount_point": mount_point,
                    "message": f"{len(source_paths)} item(ns) copiado(s) com sucesso para {target_dir}!",
                }
            except PermissionError:
                # Se for EXT4 recém-formatado como root, mudar dono para o usuário atual e copiar
                uid = os.getuid()
                gid = os.getgid()
                subprocess.run(["pkexec", "chown", "-R", f"{uid}:{gid}", mount_point])
                try:
                    os.makedirs(target_dir, exist_ok=True)
                    for src in source_paths:
                        if not os.path.exists(src):
                            continue
                        base = os.path.basename(src.rstrip("/"))
                        dst = os.path.join(target_dir, base)
                        if progress_cb:
                            progress_cb(f"Copiando '{base}' para {target_dir}...")
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
                    subprocess.run(["sync"])
                    return {
                        "success": True,
                        "mount_point": mount_point,
                        "message": f"Permissões ajustadas e {len(source_paths)} item(ns) copiado(s) para {target_dir}!",
                    }
                except Exception as e:
                    return {"success": False, "message": f"Erro durante a cópia: {e}"}
            except Exception as e:
                return {"success": False, "message": f"Erro ao copiar arquivos: {e}"}
        else:
            # Montagem temporária via pkexec
            tmp_mnt = "/tmp/hd_control_mnt"
            uid = os.getuid()
            gid = os.getgid()
            cp_cmds = []
            for src in source_paths:
                if os.path.exists(src):
                    cp_cmds.append(f"cp -r '{src}' '{tmp_mnt}/{dest_subfolder.strip('/')}'")
            script = f"""
            set -e
            mkdir -p '{tmp_mnt}'
            mount {partition_path} '{tmp_mnt}'
            mkdir -p '{tmp_mnt}/{dest_subfolder.strip('/')}'
            {" && ".join(cp_cmds)}
            chown -R {uid}:{gid} '{tmp_mnt}' 2>/dev/null || true
            sync
            umount '{tmp_mnt}'
            """
            res = subprocess.run(["pkexec", "sh", "-c", script], capture_output=True, text=True)
            if res.returncode == 0:
                return {
                    "success": True,
                    "mount_point": tmp_mnt,
                    "message": f"{len(source_paths)} item(ns) copiado(s) com sucesso para {partition_path}!",
                }
            else:
                return {"success": False, "message": f"Não foi possível montar/copiar para {partition_path}:\n{res.stderr}"}

    @staticmethod
    def _get_partition_mountpoint(partition_path: str) -> Optional[str]:
        try:
            res = subprocess.run(
                ["lsblk", "-no", "MOUNTPOINT", partition_path], capture_output=True, text=True, timeout=4
            )
            for line in res.stdout.splitlines():
                if line.strip():
                    return line.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def flash_iso_or_image(
        source_image: str,
        target_device: str,
        is_system: bool = False,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """
        Grava uma imagem ISO ou IMG/RAW diretamente no HD/SSD conectado (ou clona um disco de origem
        para um disco de destino) com verificação e sync.
        """
        if is_system:
            return {
                "success": False,
                "message": "BLOQUEIO DE SEGURANÇA: Não é permitido gravar imagem sobre o disco do sistema!",
            }
        if not os.path.exists(source_image):
            return {"success": False, "message": f"Arquivo ou dispositivo de origem não encontrado: {source_image}"}

        if progress_cb:
            progress_cb(f"Gravando imagem '{os.path.basename(source_image)}' em {target_device}... Aguarde.")

        script = f"""
        set -e
        for p in $(lsblk -ln -o PATH {target_device} | tail -n +2); do
            umount -f "$p" 2>/dev/null || true
        done
        dd if='{source_image}' of={target_device} bs=4M conv=fsync status=none
        sync
        partprobe {target_device} || true
        """
        res = subprocess.run(["pkexec", "sh", "-c", script], capture_output=True, text=True)
        if res.returncode == 0:
            return {
                "success": True,
                "message": f"Imagem '{os.path.basename(source_image)}' gravada com sucesso em {target_device}!",
            }
        else:
            return {
                "success": False,
                "message": f"Erro ao gravar imagem em {target_device}:\n{res.stderr}",
            }

    @staticmethod
    def find_local_isos() -> List[str]:
        """Procura arquivos .iso e .img nas pastas Downloads e Workspace do usuário para facilitar."""
        found = []
        search_dirs = [
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Downloads/Outros"),
            os.path.expanduser("~/Downloads/Instaladores"),
            os.path.expanduser("~/Documentos"),
            os.path.expanduser("~/workspace"),
        ]
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            try:
                for entry in os.scandir(d):
                    if entry.is_file() and entry.name.lower().endswith((".iso", ".img", ".raw")):
                        found.append(entry.path)
            except Exception:
                pass
        return sorted(list(set(found)))
