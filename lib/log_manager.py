import csv
import json
import os
from datetime import datetime
from collections import defaultdict
from influxdb_client import InfluxDBClient

import plistlib


def bytes_to_string(data):
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    elif isinstance(data, dict):
        return {
            bytes_to_string(key): bytes_to_string(value) for key, value in data.items()
        }
    elif isinstance(data, list):
        return [bytes_to_string(item) for item in data]
    else:
        return data


class LogManager(object):
    def __init__(
        self,
        findmy_files,
        store_keys,
        timestamp_key,
        log_folder,
        name_keys,
        name_separator,
        json_layer_separator,
        null_str,
        date_format,
        no_date_folder,
        log_location,
        influx_host,
        influx_token,
        influx_org,
        influx_bucket,
        decryptor=None,
    ):
        self._findmy_files = findmy_files
        self._store_keys = store_keys
        self._timestamp_key = timestamp_key
        self._name_keys = name_keys
        self._name_separator = name_separator
        self._json_layer_separator = json_layer_separator
        self._null_str = null_str
        self._date_format = date_format
        self._decryptor = decryptor
        self._decrypt_cache = {}

        # Log location config
        # 日志位置配置
        self._log_location = log_location
        if self._log_location == "local":
            self._log_folder = log_folder
            self._no_date_folder = no_date_folder
        elif self._log_location == "influx":
            self._influx_org = influx_org
            self._influx_bucket = influx_bucket
            influx_client = InfluxDBClient(
                url=influx_host, token=influx_token, org=self._influx_org
            )
            self._influx_write_api = influx_client.write_api()
        else:
            raise ValueError(
                f"Unsupported log location: `{self._log_location}`, supported log locations: `local`, `influx`"
            )

        self._latest_log = {}
        self._log_cnt = defaultdict(int)

        self._keys = sorted(list(set(self._name_keys).union(set(self._store_keys))))

    def _key_type_for_file(self, file_path):
        """
        Infer the decryptor key type from the file path.
        根据文件路径推断解密器密钥类型。
        """
        # FMIP group paths / FMIP 组路径
        if "fmipcore" in file_path:
            return "FMIP"
        # FMF group paths / FMF 组路径
        if "fmfcore" in file_path:
            return "FMF"
        return None

    def _load_and_decrypt(self, file):
        """
        Load a FindMy cache file, decrypting it if a decryptor is configured.
        加载 FindMy 缓存文件，如果配置了解密器则进行解密。

        Results are memoized per (file, mtime) to avoid re-decrypting on
        every refresh tick when the file has not changed.
        结果按 (file, mtime) 进行记忆化，避免文件未变更时每次刷新都重新解密。
        """
        if self._decryptor is None:
            with open(file, "rb") as f:
                return plistlib.load(f, fmt=plistlib.FMT_BINARY)

        try:
            mtime = os.path.getmtime(file)
        except OSError:
            mtime = None
        cache_key = (file, mtime)
        if cache_key in self._decrypt_cache:
            return self._decrypt_cache[cache_key]

        with open(file, "rb") as f:
            outer_plist = plistlib.load(f, fmt=plistlib.FMT_BINARY)

        key_type = self._key_type_for_file(file)
        if key_type and "encryptedData" in outer_plist:
            plaintext = self._decryptor.decrypt_chacha20_poly1305(
                outer_plist["encryptedData"], key_type
            )
            if plaintext is None:
                raise RuntimeError(
                    f"[EN] Failed to decrypt {file} with {key_type} key. "
                    "Check that the correct key file was provided. | "
                    f"[ZH] 使用 {key_type} 密钥解密 {file} 失败。"
                    "请检查是否提供了正确的密钥文件。"
                )
            data = plistlib.loads(plaintext, fmt=plistlib.FMT_BINARY)
        else:
            data = outer_plist

        self._decrypt_cache[cache_key] = data
        return data

    def _process_item(self, item):
        item_dict = {}
        for key in self._keys:
            path = key.split(self._json_layer_separator)
            value = item
            for sub_key in path:
                if isinstance(value, dict) and sub_key in value:
                    value = value[sub_key]
                else:
                    value = self._null_str
                    break
            item_dict[key] = value
        return item_dict

    def _get_items_dict(self):
        items_dict = {}
        file_errors = {}
        for file in self._findmy_files:
            try:
                plist_data = self._load_and_decrypt(file)
            except FileNotFoundError:
                file_errors[file] = (
                    "[EN] File not found. | [ZH] 文件不存在。"
                )
                continue
            except PermissionError as e:
                file_errors[file] = (
                    f"[EN] Permission denied ({e}). Grant Full Disk Access "
                    "to Terminal in System Settings > Privacy & Security. | "
                    f"[ZH] 没有访问权限（{e}）。请在“系统设置 > 隐私与安全性”"
                    "中为终端授予“完全磁盘访问权限”。"
                )
                continue
            except RuntimeError:
                # Raised by _load_and_decrypt on decryption failure.
                # Already bilingual; re-raise so the caller surfaces the
                # exact cause instead of the generic "No devices found" error.
                raise
            except plistlib.InvalidFileException as e:
                file_errors[file] = (
                    f"[EN] Invalid plist file ({e}). | "
                    f"[ZH] 无效的 plist 文件（{e}）。"
                )
                continue
            try:
                converted_data = bytes_to_string(plist_data)
                json_data = json.dumps(converted_data)
            except (TypeError, ValueError) as e:
                file_errors[file] = (
                    f"[EN] Failed to serialize plist to JSON ({e}). | "
                    f"[ZH] 将 plist 序列化为 JSON 失败（{e}）。"
                )
                continue
            for item in json_data:
                item = self._process_item(item)
                name = [
                    item[key] if key in item else self._null_str
                    for key in self._name_keys
                ]
                name = self._name_separator.join(name)
                if name in items_dict:
                    raise ValueError(f"{name} already exists!")
                items_dict[name] = item
        if not items_dict:
            if file_errors:
                details = " | ".join(
                    f"{os.path.basename(f)}: {msg}" for f, msg in file_errors.items()
                )
                raise RuntimeError(
                    f"[EN] No devices found. Per-file errors -> {details} | "
                    f"[ZH] 未找到任何设备。各文件错误 -> {details}"
                )
            raise RuntimeError(
                f"[EN] No devices found. Please check if Full Disk "
                "Access has been granted to Terminal. | "
                "[ZH] 未找到任何设备。请检查是否已为终端授予“完全磁盘访问权限”。"
            )
        return items_dict

    def _save_log(self, name, data):
        """
        Routes _save_log() calls to their proper function based on log location
        """
        if self._log_location == "local":
            return self._save_log_local(name, data)
        elif self._log_location == "influx":
            return self._save_log_influx(name, data)

    def _save_log_local(self, name, data):
        log_folder = self._log_folder
        if not self._no_date_folder:
            log_folder = os.path.join(
                log_folder, datetime.now().strftime(self._date_format)
            )
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)
        path = os.path.join(log_folder, name + ".csv")

        if not os.path.exists(path):
            with open(path, "w") as f:
                writer = csv.writer(f)
                writer.writerow(self._keys)

        with open(path, "a") as f:
            writer = csv.writer(f)
            writer.writerow([data[k] for k in self._keys])

    def _save_log_influx(self, name, data):
        """
        Sends log data to an InfluxDB2 database bucket
        """
        with open("test.txt", "w") as f:
            f.write(f"Saving Log Line for {name}: {data}")

        self._influx_write_api.write(
            bucket=self._influx_bucket,
            org=self._influx_org,
            record={
                "measurement": name,
                "fields": {
                    key: float(data[key]) if isinstance(data[key], int) else data[key]
                    for key in self._keys
                    if key in data
                },
                "time": data["location|timeStamp"],
            },
            write_precision="ms",
        )

    def refresh_log(self):
        items_dict = self._get_items_dict()
        for name in items_dict:
            # On non-local log locations, don't push null data
            # 在非本地日志位置时，不要推送空值数据
            if self._log_location != "local" and (
                items_dict[name]["location|timeStamp"] == "NULL"
                or items_dict[name]["location|longitude"] == "NULL"
            ):
                continue

            if (
                name not in self._latest_log
                or self._latest_log[name] != items_dict[name]
            ):
                self._save_log(name, items_dict[name])
                self._latest_log[name] = items_dict[name]
                self._log_cnt[name] += 1

    def get_latest_log(self):
        return self._latest_log, self._log_cnt
