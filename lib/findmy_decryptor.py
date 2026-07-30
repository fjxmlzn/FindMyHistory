#!/usr/bin/env python3
"""
FindMy Cache Data Decryption Script
FindMy 缓存数据解密脚本
Based on reverse engineering analysis of FindMyCrypto.framework
基于对 FindMyCrypto.framework 的逆向分析

Supports decryption of two cache file groups:
支持两组缓存文件解密：
1. FMIP Group (Find My iPhone) - uses FMIPDataManager.bplist key
1. FMIP 组 (Find My iPhone) - 使用 FMIPDataManager.bplist 密钥
   - SafeLocations.data, Items.data, Devices.data, FamilyMembers.data, ItemGroups.data, Owner.data
   - SafeLocations.data, Items.data, Devices.data, FamilyMembers.data, ItemGroups.data, Owner.data
2. FMF Group (Find My Friends) - uses FMFDataManager.bplist key
2. FMF 组 (Find My Friends) - 使用 FMFDataManager.bplist 密钥
   - FriendCacheData.data
   - FriendCacheData.data

Encryption Process:
加密流程：
1. ChaCha20-Poly1305 AEAD symmetric encryption
1. ChaCha20-Poly1305 AEAD 对称加密
2. Uses pre-stored symmetric key for decryption
2. 使用预先存储的对称密钥进行解密
"""

import plistlib
import base64
import json
import datetime
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
import os


def _log(en, zh, *args, **kwargs):
    """Print a log line with both English and Chinese versions.

    Print a log line in both English and Chinese so output is readable for either audience.

    Args:
        en: English message (may contain %-style placeholders matching *args).
        zh: Chinese message (may contain %-style placeholders matching *args).
        *args: Positional values substituted into both messages.
        **kwargs: Forwarded to ``print`` (e.g. ``end``).
    """
    if args:
        en_msg = en % args if "%" in en else en.format(*args)
        zh_msg = zh % args if "%" in zh else zh.format(*args)
    else:
        en_msg, zh_msg = en, zh
    print(f"[EN] {en_msg} | [ZH] {zh_msg}", **kwargs)


class FindMyDecryptor:
    """
    FindMy Cache Data Decryptor Class
    FindMy 缓存数据解密器类
    Handles decryption of FindMy cache files using ChaCha20-Poly1305 encryption
    使用 ChaCha20-Poly1305 加密处理 FindMy 缓存文件解密
    """

    def __init__(self):
        """
        Initialize the decryptor with empty keys
        初始化解密器，设置空密钥
        """
        self.fmip_key = None  # FMIP group key / FMIP 组密钥
        self.fmf_key = None  # FMF group key / FMF 组密钥

    def load_keys_from_file(self, file_path, key_type):
        """
        Load key data from file
        从文件加载密钥数据

        Args:
            file_path (str): Path to the key file
            key_type (str): Type of key ('FMIP' or 'FMF')

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Try to load key from file / 尝试从文件加载密钥
            _log(
                "🔍 Trying to load %s key from file: %s",
                "🔍 尝试从文件加载 %s 密钥: %s",
                key_type, file_path,
            )

            # Try to read plist file / 尝试读取 plist 文件
            with open(file_path, "rb") as f:
                plist_data = plistlib.load(f)

            # Successfully loaded key data from file / 成功从文件加载密钥数据
            _log(
                "✅ Successfully loaded %s key data from file",
                "✅ 成功从文件加载 %s 密钥数据",
                key_type,
            )
            return self.load_keys_from_plist(plist_data, key_type)

        except FileNotFoundError:
            # File not found error / 文件不存在错误
            _log("❌ File does not exist: %s", "❌ 文件不存在: %s", file_path)
            return False
        except Exception as e:
            # File reading error / 文件读取错误
            _log("❌ File read error: %s", "❌ 文件读取错误: %s", e)
            return False

    def load_keys_from_input(self, key_type, filename):
        """
        Load key data from user input
        从用户输入加载密钥数据

        Args:
            key_type (str): Type of key ('FMIP' or 'FMF')
            filename (str): Name of the key file for reference

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Prompt user for file contents / 提示用户输入文件内容
            _log(
                "\n📝 Please enter the contents of the %s file:",
                "\n📝 请输入 %s 文件的内容:",
                filename, end="\n",
            )
            # Hint: you can use 'xxd -p filename | tr -d "\n"' to get hex content
            # 提示：可以使用 'xxd -p filename | tr -d "\n"' 获取十六进制内容
            _log(
                "Hint: you can use 'xxd -p %s | tr -d \"\\n\"' to get hex content",
                "提示：可以使用 'xxd -p %s | tr -d \"\\n\"' 获取十六进制内容",
                filename,
            )

            hex_input = input(
                "[EN] Please enter hex content: | [ZH] 请输入十六进制内容: "
            ).strip()

            # Remove spaces and newlines / 移除空格和换行符
            hex_input = hex_input.replace(" ", "").replace("\n", "")

            # Convert to binary data / 转换为二进制数据
            binary_data = bytes.fromhex(hex_input)

            # Parse as plist / 解析为 plist
            plist_data = plistlib.loads(binary_data)

            # Successfully parsed user input data / 成功解析用户输入的数据
            _log(
                "✅ Successfully parsed %s data from user input",
                "✅ 成功解析用户输入的 %s 数据",
                key_type,
            )
            return self.load_keys_from_plist(plist_data, key_type)

        except ValueError as e:
            # Hexadecimal data format error / 十六进制数据格式错误
            _log(
                "❌ Hexadecimal data format error: %s",
                "❌ 十六进制数据格式错误: %s",
                e,
            )
            return False
        except Exception as e:
            # Data parsing error / 数据解析错误
            _log("❌ Data parsing error: %s", "❌ 数据解析错误: %s", e)
            return False

    def load_keys_from_plist(self, plist_data, key_type):
        """
        Load keys from plist data
        从 plist 数据加载密钥

        Args:
            plist_data (dict): Parsed plist data
            key_type (str): Type of key ('FMIP' or 'FMF')

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get symmetric key, supports two formats:
            # 获取对称密钥，支持两种格式：
            # Format 1: Direct base64 string / 格式1: 直接 base64 字符串
            # Format 2: Nested dictionary structure {'key': {'data': base64_string}}
            # 格式2: 嵌套字典结构 {'key': {'data': base64_string}}

            symmetric_key_data = plist_data.get("symmetricKey")

            if not symmetric_key_data:
                # Missing symmetricKey in plist / plist 中缺少 symmetricKey
                _log(
                    "❌ Missing symmetricKey in plist",
                    "❌ plist 中缺少 symmetricKey",
                )
                return False

            # Check if it's a nested structure / 检查是否为嵌套结构
            if isinstance(symmetric_key_data, dict):
                # Nested format: symmetricKey -> key -> data
                # 嵌套格式: symmetricKey -> key -> data
                key_dict = symmetric_key_data.get("key", {})
                if isinstance(key_dict, dict):
                    symmetric_key_b64 = key_dict.get("data")
                    if isinstance(symmetric_key_b64, bytes):
                        # If it's bytes type, use directly / 如果是 bytes 类型，直接使用
                        symmetric_key_bytes = symmetric_key_b64
                    else:
                        # If it's string, decode base64 / 如果是字符串，解码 base64
                        symmetric_key_bytes = base64.b64decode(symmetric_key_b64)
                else:
                    # Invalid symmetricKey structure / 无效的 symmetricKey 结构
                    _log(
                        "❌ Invalid symmetricKey structure",
                        "❌ 无效的 symmetricKey 结构",
                    )
                    return False
            else:
                # Direct format: directly base64 string / 直接格式: 直接是 base64 字符串
                symmetric_key_bytes = base64.b64decode(symmetric_key_data)

            # Print symmetric key length / 打印对称密钥长度
            _log(
                "🔑 %s symmetric key length: %d bytes",
                "🔑 %s 对称密钥长度: %d 字节",
                key_type, len(symmetric_key_bytes),
            )

            if len(symmetric_key_bytes) != 32:
                # Incorrect symmetric key length, should be 32 bytes
                # 对称密钥长度不正确，应为 32 字节
                _log(
                    "❌ %s symmetric key length is incorrect, should be 32 bytes",
                    "❌ %s 对称密钥长度不正确，应为 32 字节",
                    key_type,
                )
                return False

            # Save to different attributes based on key type / 根据密钥类型保存到不同的属性
            if key_type == "FMIP":
                self.fmip_key = symmetric_key_bytes
            elif key_type == "FMF":
                self.fmf_key = symmetric_key_bytes
            else:
                # Unknown key type / 未知的密钥类型
                _log(
                    "❌ Unknown key type: %s",
                    "❌ 未知的密钥类型: %s",
                    key_type,
                )
                return False

            # Symmetric key loaded successfully / 对称密钥加载成功
            _log(
                "✅ %s symmetric key loaded successfully",
                "✅ %s 对称密钥加载成功",
                key_type,
            )
            return True

        except Exception as e:
            # Key loading error / 密钥加载错误
            _log("❌ Key loading error: %s", "❌ 密钥加载错误: %s", e)
            return False

    def decrypt_chacha20_poly1305(self, encrypted_data, key_type):
        """
        Decrypt data using ChaCha20-Poly1305
        使用 ChaCha20-Poly1305 解密数据

        Args:
            encrypted_data (bytes): Encrypted data to decrypt
            key_type (str): Type of key to use ('FMIP' or 'FMF')

        Returns:
            bytes: Decrypted plaintext data, or None if failed
        """
        try:
            # Parse encryptedData structure / 解析 encryptedData 结构
            # First 12 bytes: nonce / 前12字节: nonce
            # Middle part: ciphertext / 中间部分: 密文
            # Last 16 bytes: authentication tag / 后16字节: 认证标签

            if len(encrypted_data) < 28:  # At least need nonce + auth_tag
                # Insufficient encrypted data length / 加密数据长度不足
                _log(
                    "❌ Encrypted data length is insufficient",
                    "❌ 加密数据长度不足",
                )
                return None

            nonce = encrypted_data[:12]
            ciphertext_with_tag = encrypted_data[12:]

            # Nonce and ciphertext+tag length / Nonce 与 密文+标签长度
            _log("🔍 Nonce: %s", "🔍 Nonce: %s", nonce.hex())
            _log(
                "🔍 Ciphertext + tag length: %d bytes",
                "🔍 密文+标签长度: %d 字节",
                len(ciphertext_with_tag),
            )

            # Select corresponding key based on key type / 根据密钥类型选择对应的密钥
            if key_type == "FMIP":
                symmetric_key = self.fmip_key
            elif key_type == "FMF":
                symmetric_key = self.fmf_key
            else:
                # Unknown key type / 未知的密钥类型
                _log(
                    "❌ Unknown key type: %s",
                    "❌ 未知的密钥类型: %s",
                    key_type,
                )
                return None

            # Decrypt using symmetric key / 使用对称密钥解密
            if symmetric_key is None:
                # Symmetric key not initialized / 对称密钥未初始化
                _log(
                    "❌ %s symmetric key is not initialized",
                    "❌ %s 对称密钥未初始化",
                    key_type,
                )
                return None

            # Create ChaCha20Poly1305 decryptor / 创建 ChaCha20Poly1305 解密器
            cipher = ChaCha20Poly1305(symmetric_key)

            # Decrypt data / 解密数据
            plaintext = cipher.decrypt(nonce, ciphertext_with_tag, None)
            # Decryption successful, plaintext length / 解密成功，明文长度
            _log(
                "✅ Decryption successful, plaintext length: %d bytes",
                "✅ 解密成功，明文长度: %d 字节",
                len(plaintext),
            )

            return plaintext

        except Exception as e:
            # ChaCha20-Poly1305 decryption error / ChaCha20-Poly1305 解密错误
            _log(
                "❌ ChaCha20-Poly1305 decryption error: %s",
                "❌ ChaCha20-Poly1305 解密错误: %s",
                e,
            )
            return None

    def format_plist_data(self, data, indent=0):
        """
        Format plist data for readability
        格式化 plist 数据以便可读

        Args:
            data: Data to format
            indent (int): Indentation level

        Returns:
            str: Formatted string representation
        """
        spaces = "  " * indent

        if isinstance(data, dict):
            result = "{\n"
            for key, value in data.items():
                result += (
                    f"{spaces}  {key}: {self.format_plist_data(value, indent + 1)}\n"
                )
            result += f"{spaces}}}"
            return result
        elif isinstance(data, list):
            result = "[\n"
            for item in data:
                result += f"{spaces}  {self.format_plist_data(item, indent + 1)}\n"
            result += f"{spaces}]"
            return result
        elif isinstance(data, bytes):
            return f"<{len(data)} bytes: {data[:20].hex()}{'...' if len(data) > 20 else ''}>"
        elif isinstance(data, datetime.datetime):
            return f"<datetime: {data.isoformat()}>"
        else:
            return str(data)

    def decrypt_cache_file(self, file_path, key_type):
        """
        Decrypt cache file
        解密缓存文件

        Args:
            file_path (str): Path to the cache file to decrypt
            key_type (str): Type of key to use ('FMIP' or 'FMF')

        Returns:
            bytes: Decrypted data, or None if failed
        """
        try:
            # Start decrypting file / 开始解密文件
            _log(
                "🔍 Starting to decrypt file: %s (using %s key)",
                "🔍 开始解密文件: %s (使用 %s 密钥)",
                file_path, key_type,
            )

            # Read plist file / 读取 plist 文件
            with open(file_path, "rb") as f:
                plist_data = plistlib.load(f)

            # Print plist data structure / 打印 plist 数据结构
            _log("📋 plist data structure:", "📋 plist 数据结构:")
            for key, value in plist_data.items():
                if isinstance(value, bytes):
                    _log("  %s: %d bytes", "  %s: %d 字节", key, len(value))
                else:
                    _log("  %s: %s", "  %s: %s", key, value)

            # Extract encrypted data / 提取加密数据
            encrypted_data = plist_data.get("encryptedData")

            if not encrypted_data:
                # Missing encryptedData / 缺少 encryptedData
                _log("❌ Missing encryptedData", "❌ 缺少 encryptedData")
                return None

            # Print encryptedData length / 打印 encryptedData 长度
            _log(
                "🔍 encryptedData length: %d bytes",
                "🔍 encryptedData 长度: %d 字节",
                len(encrypted_data),
            )

            # Decrypt data / 解密数据
            plaintext = self.decrypt_chacha20_poly1305(encrypted_data, key_type)

            if plaintext:
                # Decryption successful! / 解密成功!
                _log("✅ Decryption successful!", "✅ 解密成功!")
                # First 100 bytes of plaintext / 明文前100字节
                _log(
                    "📝 First 100 bytes of plaintext: %s",
                    "📝 明文前100字节: %s",
                    plaintext[:100],
                )

                # Try to parse decrypted data / 尝试解析解密后的数据
                try:
                    # First check if it's plist format / 首先检查是否为 plist 格式
                    if plaintext.startswith(b"bplist"):
                        # Decrypted data is plist format, parsing...
                        # 解密后的数据是 plist 格式，正在解析...
                        _log(
                            "📊 Decrypted data is in plist format, parsing...",
                            "📊 解密后的数据是 plist 格式，正在解析...",
                        )
                        inner_plist = plistlib.loads(plaintext)
                        # Content of decrypted plist / 解密后的 plist 内容
                        _log(
                            "📋 Decrypted plist content:",
                            "📋 解密后的 plist 内容:",
                        )
                        print(self.format_plist_data(inner_plist))

                        # Save decrypted data to file / 保存解密后的数据到文件
                        output_file = f"{file_path}.decrypted.plist"
                        with open(output_file, "wb") as f:
                            plistlib.dump(inner_plist, f)
                        # Decrypted data saved to / 解密后的数据已保存到
                        _log(
                            "💾 Decrypted data saved to: %s",
                            "💾 解密后的数据已保存到: %s",
                            output_file,
                        )

                    elif plaintext.startswith(b"{"):
                        # JSON format / JSON 格式
                        json_data = json.loads(plaintext.decode("utf-8"))
                        # Parsed as JSON format / 解析为 JSON 格式
                        _log(
                            "📊 Parsed as JSON format:",
                            "📊 解析为 JSON 格式:",
                        )
                        print(json.dumps(json_data, indent=2, ensure_ascii=False))

                    else:
                        # Other formats, try to display as text
                        # 其他格式，尝试作为文本显示
                        # Plaintext content (first 1000 bytes) / 明文内容 (前1000字节)
                        _log(
                            "📝 Plaintext content (first 1000 bytes):",
                            "📝 明文内容 (前1000字节):",
                        )
                        try:
                            print(plaintext[:1000].decode("utf-8"))
                        except UnicodeDecodeError:
                            # Binary data / 二进制数据
                            _log(
                                "Binary data: %s",
                                "二进制数据: %s",
                                plaintext[:1000],
                            )

                        # Save raw decrypted data / 保存原始解密数据
                        output_file = f"{file_path}.decrypted.bin"
                        with open(output_file, "wb") as f:
                            f.write(plaintext)
                        # Raw decrypted data saved to / 原始解密数据已保存到
                        _log(
                            "💾 Raw decrypted data saved to: %s",
                            "💾 原始解密数据已保存到: %s",
                            output_file,
                        )

                except Exception as e:
                    # Error occurred while parsing decrypted data / 解析解密数据时出错
                    _log(
                        "⚠️  Error while parsing decrypted data: %s",
                        "⚠️  解析解密数据时出错: %s",
                        e,
                    )
                    # Plaintext content (first 1000 bytes) / 明文内容 (前1000字节)
                    _log(
                        "📝 Plaintext content (first 1000 bytes):",
                        "📝 明文内容 (前1000字节):",
                    )
                    print(plaintext[:1000])

                return plaintext

            return None

        except Exception as e:
            # File decryption error / 解密文件错误
            _log(
                "❌ File decryption error: %s",
                "❌ 解密文件错误: %s",
                e,
            )
            return None


def main():
    """
    Main function
    主函数
    """
    decryptor = FindMyDecryptor()

    # FindMy Cache Data Decryption Tool / FindMy 缓存数据解密工具
    _log(
        "🔐 FindMy Cache Data Decryption Tool",
        "🔐 FindMy 缓存数据解密工具",
    )
    print("=" * 50)

    # Define key files and corresponding cache files / 定义密钥文件和对应的缓存文件
    key_configs = [
        {
            "key_type": "FMIP",
            "key_file": "FMIPDataManager.bplist",
            "cache_files": [
                "com.apple.findmy.fmipcore/SafeLocations.data",
                "com.apple.findmy.fmipcore/Items.data",
                "com.apple.findmy.fmipcore/Devices.data",
                "com.apple.findmy.fmipcore/FamilyMembers.data",
                "com.apple.findmy.fmipcore/ItemGroups.data",
                "com.apple.findmy.fmipcore/Owner.data",
            ],
        },
        {
            "key_type": "FMF",
            "key_file": "FMFDataManager.bplist",
            "cache_files": ["com.apple.findmy.fmfcore/FriendCacheData.data"],
        },
    ]

    # Process each key group / 处理每个密钥组
    for config in key_configs:
        key_type = config["key_type"]
        key_file = config["key_file"]
        cache_files = config["cache_files"]

        # Processing key group / 正在处理密钥组
        _log(
            "\n🔧 Processing %s group...",
            "\n🔧 处理 %s 组...",
            key_type, end="\n",
        )

        # Check if there are corresponding cache files to decrypt
        # 检查是否有对应的缓存文件需要解密
        existing_files = [f for f in cache_files if os.path.exists(f)]
        if not existing_files:
            # No cache files found for group, skipping... / 没有找到缓存文件，跳过...
            _log(
                "⚠️  No cache files found for %s group, skipping...",
                "⚠️  没有找到 %s 组的缓存文件，跳过...",
                key_type,
            )
            continue

        # Found cache files for group / 发现密钥组对应的缓存文件
        _log(
            "📁 Found %s group cache files: %s",
            "📁 发现 %s 组缓存文件: %s",
            key_type, existing_files,
        )

        # Try to load key from file / 尝试从文件加载密钥
        _log(
            "1️⃣ Trying to load %s key from file...",
            "1️⃣ 尝试从文件加载 %s 密钥...",
            key_type,
        )
        if not decryptor.load_keys_from_file(key_file, key_type):
            # Key file loading failed, please manually input key data
            # 密钥文件加载失败，请手动输入密钥数据
            _log(
                "⚠️  %s key file loading failed, please manually input key data",
                "⚠️  %s 密钥文件加载失败，请手动输入密钥数据",
                key_type,
            )

            # Load key from user input / 从用户输入加载密钥
            _log(
                "2️⃣ Loading %s key from user input:",
                "2️⃣ 从用户输入加载 %s 密钥:",
                key_type,
            )
            try:
                if not decryptor.load_keys_from_input(key_type, key_file):
                    # Key loading failed, skipping this group... / 密钥加载失败，跳过该组...
                    _log(
                        "❌ %s key loading failed, skipping this group...",
                        "❌ %s 密钥加载失败，跳过该组...",
                        key_type,
                    )
                    continue
            except KeyboardInterrupt:
                # User cancelled input, skipping group... / 用户取消输入，跳过该组...
                _log(
                    "\n❌ User cancelled input, skipping %s group...",
                    "\n❌ 用户取消输入，跳过 %s 组...",
                    key_type,
                )
                continue
            except Exception as e:
                # Input error, skipping group... / 输入错误，跳过该组...
                _log(
                    "❌ Input error: %s, skipping %s group...",
                    "❌ 输入错误: %s，跳过 %s 组...",
                    e, key_type,
                )
                continue

        # Decrypt cache files for this group / 解密该组的缓存文件
        _log(
            "3️⃣ Starting to decrypt %s group cache files...",
            "3️⃣ 开始解密 %s 组缓存文件...",
            key_type,
        )
        for file_path in existing_files:
            # Decrypt file / 解密文件
            _log(
                "\n📁 Decrypting file: %s",
                "\n📁 解密文件: %s",
                file_path, end="\n",
            )
            decryptor.decrypt_cache_file(file_path, key_type)

    # All files processed! / 所有文件处理完成!
    _log("\n🎉 All files processed!", "\n🎉 所有文件处理完成！")


if __name__ == "__main__":
    main()
