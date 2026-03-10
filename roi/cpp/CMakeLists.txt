cmake_minimum_required(VERSION 3.10)
project(emr_roi_masks)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 编译选项
if(MSVC)
    add_compile_options(/O2 /W3)
else()
    add_compile_options(-O3 -Wall -Wextra -fPIC)
    # SIMD 优化（可选）
    if(UNIX AND NOT APPLE)
        add_compile_options(-march=native)
    endif()
endif()

# 共享库（.so/.dll/.dylib）
add_library(emr_roi_masks SHARED 
    roi_masks.cpp
)

# 设置输出目录为上层目录的 lib/
set_target_properties(emr_roi_masks PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
)

# 添加头文件包含路径
target_include_directories(emr_roi_masks PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)

# 可选：安装规则
install(TARGETS emr_roi_masks
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
)
install(FILES roi_masks.h DESTINATION include)
