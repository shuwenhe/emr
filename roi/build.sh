#!/bin/bash
# 编译 EMR ROI Masks C++ 库

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CPP_DIR="${SCRIPT_DIR}/cpp"
BUILD_DIR="${CPP_DIR}/build"
INSTALL_DIR="${CPP_DIR}/lib"

echo "========================================="
echo "EMR ROI Masks C++ Build Script"
echo "========================================="
echo "Script directory: $SCRIPT_DIR"
echo "C++ directory: $CPP_DIR"
echo "Build directory: $BUILD_DIR"
echo "Install directory: $INSTALL_DIR"
echo ""

# 检查C++源文件是否存在
if [ ! -f "${CPP_DIR}/CMakeLists.txt" ]; then
    echo "Error: CMakeLists.txt not found in $CPP_DIR"
    exit 1
fi

# 创建编译目录
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# 运行 CMake
echo "[1/3] Running CMake..."
cmake -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
      "$CPP_DIR"

# 编译
echo "[2/3] Building..."
if command -v cmake &> /dev/null; then
    cmake --build . --config Release -j$(nproc)
else
    make -j$(nproc)
fi

# 安装
echo "[3/3] Installing..."
cmake --install . --prefix "$INSTALL_DIR" --config Release

echo ""
echo "========================================="
echo "✓ Build completed successfully!"
echo "Library installed to: $INSTALL_DIR"
echo "========================================="
echo ""
echo "To use the C++ accelerated library:"
echo "  1. Compiled library is at: $INSTALL_DIR"
echo "  2. Python binding at: ${SCRIPT_DIR}/python/roi_masks_binding.py"
echo "  3. The library will auto-load if available, or fallback to Python"
echo ""
