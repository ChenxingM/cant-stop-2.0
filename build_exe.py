# -*- coding: utf-8 -*-
"""
打包脚本 - 将游戏打包成可执行文件
使用方法: python build_exe.py
"""

import subprocess
import sys
import shutil
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

def install_pyinstaller():
    """安装 PyInstaller"""
    print("正在安装 PyInstaller...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

def update_version():
    """更新版本号 (格式: YYYYMMDD_XXX)"""
    version_file = PROJECT_ROOT / "version.py"
    today = datetime.now().strftime("%Y%m%d")

    # 读取当前版本
    current_version = "00000000_000"
    if version_file.exists():
        content = version_file.read_text(encoding='utf-8')
        match = re.search(r'VERSION\s*=\s*["\'](\d{8})_(\d{3})["\']', content)
        if match:
            current_version = f"{match.group(1)}_{match.group(2)}"

    # 计算新版本号
    current_date, current_build = current_version.split('_')
    if current_date == today:
        new_build = int(current_build) + 1
    else:
        new_build = 1
    new_version = f"{today}_{new_build:03d}"

    # 写入新版本
    content = f'''# -*- coding: utf-8 -*-
"""
版本信息
每次 build 时自动更新
"""

VERSION = "{new_version}"
AUTHOR = "Your Name"
PROJECT_NAME = "贪骰无厌 2.0 (Can't Stop)"
'''
    version_file.write_text(content, encoding='utf-8')
    print(f"版本号更新: {current_version} -> {new_version}")
    return new_version

def clean_pycache():
    """清理 __pycache__ 目录"""
    for cache_dir in PROJECT_ROOT.rglob("__pycache__"):
        shutil.rmtree(cache_dir)
        print(f"已删除: {cache_dir}")

def build():
    """执行打包"""
    dist_dir = PROJECT_ROOT / "dist"
    build_dir = PROJECT_ROOT / "build"

    # 更新版本号
    new_version = update_version()

    # 清理旧的打包
    for d in [dist_dir, build_dir]:
        if d.exists():
            print(f"清理: {d}")
            shutil.rmtree(d)

    clean_pycache()

    # 打包 GameMaster GUI
    print("\n" + "="*50)
    print("正在打包 GameMaster GUI...")
    print("="*50)
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--name=GameMaster",
        "--windowed",  # 无控制台窗口
        "--noconfirm",
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtWidgets",
        str(PROJECT_ROOT / "gm" / "start_gamemaster_packed.py")
    ], check=True, cwd=str(PROJECT_ROOT))

    # 打包 QQ Bot (主程序)
    print("\n" + "="*50)
    print("正在打包 QQ Bot 主程序...")
    print("="*50)
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--name=CantStop",
        "--console",  # 保留控制台
        "--noconfirm",
        "--hidden-import", "aiohttp",
        str(PROJECT_ROOT / "start_game_packed.py")
    ], check=True, cwd=str(PROJECT_ROOT))

    # 复制 GameMaster 到主程序目录
    gm_dist = dist_dir / "GameMaster"
    main_dist = dist_dir / "CantStop"

    if gm_dist.exists() and main_dist.exists():
        target = main_dist / "GameMaster"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(gm_dist, target)
        print(f"\n已将 GameMaster 复制到 {target}")

    # 复制配置文件和数据文件
    print("\n正在复制数据文件...")

    # config.json
    config_src = PROJECT_ROOT / "config.json"
    if config_src.exists():
        shutil.copy(config_src, main_dist / "config.json")
        print("  ✓ config.json")

    # data 目录 (只复制需要的文件)
    data_dst = main_dist / "data"
    data_dst.mkdir(exist_ok=True)

    # board_config.py
    board_cfg = PROJECT_ROOT / "data" / "board_config.py"
    if board_cfg.exists():
        shutil.copy(board_cfg, data_dst / "board_config.py")
        print("  ✓ data/board_config.py")

    # custom_commands.json
    custom_cmd = PROJECT_ROOT / "data" / "custom_commands.json"
    if custom_cmd.exists():
        shutil.copy(custom_cmd, data_dst / "custom_commands.json")
        print("  ✓ data/custom_commands.json")

    # images 目录
    images_src = PROJECT_ROOT / "data" / "images"
    if images_src.exists():
        shutil.copytree(images_src, data_dst / "images")
        print("  ✓ data/images/")

    # 删除单独的 GameMaster 目录
    if gm_dist.exists():
        shutil.rmtree(gm_dist)

    # 清理 build 目录和 spec 文件
    if build_dir.exists():
        shutil.rmtree(build_dir)
    for spec in PROJECT_ROOT.glob("*.spec"):
        spec.unlink()

    print("\n" + "="*50)
    print(f"打包完成! 版本: {new_version}")
    print("="*50)
    print(f"\n输出目录: {main_dist}")
    print("\n发布步骤:")
    print("1. 将 dist/CantStop 整个文件夹压缩成 zip")
    print("2. 发送给对方")
    print("3. 对方解压后，先编辑 config.json 配置 WebSocket 地址和群号")
    print("4. 运行 CantStop.exe 启动游戏")

if __name__ == "__main__":
    try:
        import PyInstaller
    except ImportError:
        install_pyinstaller()

    build()
