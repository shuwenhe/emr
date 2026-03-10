#include "roi_masks.h"
#include <cmath>
#include <cstring>
#include <algorithm>
#include <vector>
#include <numeric>
#include <cstdio>

inline void emit_cpp_log(const char* event) {
    std::fprintf(stdout, "※ %s ※\n", event);
    std::fflush(stdout);
}

#if defined(__GNUC__) || defined(__clang__)
__attribute__((constructor))
static void on_lib_loaded() {
    emit_cpp_log("C++ LIB LOADED: libemr_roi_masks.so");
}
#endif

// 辅助：clamp 值到范围
inline float clamp(float val, float lo, float hi) {
    return val < lo ? lo : (val > hi ? hi : val);
}

inline int iclamp(int val, int lo, int hi) {
    return val < lo ? lo : (val > hi ? hi : val);
}

/**
 * rect_mask: 生成矩形掩膜
 * 使用直接赋值，O(面积) 复杂度
 */
int rect_mask(int height, int width, float x1, float y1, float x2, float y2,
              unsigned char* mask_out) {
    emit_cpp_log("C++ CALL: rect_mask");
    if (!mask_out || height <= 0 || width <= 0) return -1;
    
    // 初始化掩膜为0
    std::memset(mask_out, 0, height * width);
    
    // 计算clamp边界
    int x_min = iclamp((int)std::min(x1, x2), 0, width - 1);
    int x_max = iclamp((int)std::max(x1, x2), 0, width - 1);
    int y_min = iclamp((int)std::min(y1, y2), 0, height - 1);
    int y_max = iclamp((int)std::max(y1, y2), 0, height - 1);
    
    // 填充矩形区域
    for (int y = y_min; y <= y_max; ++y) {
        unsigned char* row = mask_out + y * width;
        for (int x = x_min; x <= x_max; ++x) {
            row[x] = 1;
        }
    }
    
    return 0;
}

/**
 * polygon_mask: 生成多边形掩膜
 * 使用扫描线算法 (Scanline Fill)
 */
int polygon_mask(int height, int width, const float* vertices, int num_vertices,
                 unsigned char* mask_out) {
    emit_cpp_log("C++ CALL: polygon_mask");
    if (!mask_out || !vertices || num_vertices < 3 || height <= 0 || width <= 0) {
        return -1;
    }
    
    // 初始化掩膜为0
    std::memset(mask_out, 0, height * width);
    
    // 扫描线算法简化版（使用射线法则 Ray Casting）
    for (int py = 0; py < height; ++py) {
        unsigned char* row = mask_out + py * width;
        
        for (int px = 0; px < width; ++px) {
            float x = (float)px + 0.5f;
            float y = (float)py + 0.5f;
            
            // 射线法则：沿 +x 方向从点发射射线，数与多边形的交点数
            int intersections = 0;
            for (int i = 0; i < num_vertices; ++i) {
                float x1 = vertices[i * 2];
                float y1 = vertices[i * 2 + 1];
                float x2 = vertices[((i + 1) % num_vertices) * 2];
                float y2 = vertices[((i + 1) % num_vertices) * 2 + 1];
                
                // 检查边是否与射线相交
                if ((y1 <= y && y < y2) || (y2 <= y && y < y1)) {
                    // 计算交点 x 坐标
                    float x_inter = x1 + (y - y1) * (x2 - x1) / (y2 - y1);
                    if (x < x_inter) {
                        intersections++;
                    }
                }
            }
            
            // 奇数个交点表示在多边形内
            row[px] = (intersections % 2) ? 1 : 0;
        }
    }
    
    return 0;
}

/**
 * segment_mask: 生成线段缓冲掩膜
 * 计算每点离线段的距离，如果 <= thickness 则标记
 */
int segment_mask(int height, int width, float x1, float y1, float x2, float y2,
                 float thickness, unsigned char* mask_out) {
    emit_cpp_log("C++ CALL: segment_mask");
    if (!mask_out || height <= 0 || width <= 0 || thickness < 0) return -1;
    
    std::memset(mask_out, 0, height * width);
    
    float dx = x2 - x1;
    float dy = y2 - y1;
    float len_sq = dx * dx + dy * dy;
    float thresh_sq = thickness * thickness;
    
    // 处理退化情况：两点重合
    if (len_sq < 1e-6f) {
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                float px = x - x1;
                float py = y - y1;
                if (px * px + py * py <= thresh_sq) {
                    mask_out[y * width + x] = 1;
                }
            }
        }
        return 0;
    }
    
    // 标准情况：计算点到线段的距离
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            float px = x - x1;
            float py = y - y1;
            
            // 计算投影参数 t
            float t = (px * dx + py * dy) / len_sq;
            t = clamp(t, 0.0f, 1.0f);
            
            // 投影点
            float proj_x = x1 + t * dx;
            float proj_y = y1 + t * dy;
            
            // 距离平方
            float dist_sq = (x - proj_x) * (x - proj_x) + (y - proj_y) * (y - proj_y);
            
            if (dist_sq <= thresh_sq) {
                mask_out[y * width + x] = 1;
            }
        }
    }
    
    return 0;
}

/**
 * 快速分位数计算（Quickselect）
 */
float quickselect(std::vector<float>& arr, int left, int right, int k) {
    if (left == right) return arr[left];
    
    // 简单的分割策略
    int pivot_idx = (left + right) / 2;
    float pivot = arr[pivot_idx];
    
    // 分割
    std::swap(arr[pivot_idx], arr[right]);
    int store_idx = left;
    for (int i = left; i < right; ++i) {
        if (arr[i] < pivot) {
            std::swap(arr[store_idx++], arr[i]);
        }
    }
    std::swap(arr[right], arr[store_idx]);
    
    if (k == store_idx) return arr[k];
    else if (k < store_idx) return quickselect(arr, left, store_idx - 1, k);
    else return quickselect(arr, store_idx + 1, right, k);
}

/**
 * calc_stats_fast: 快速统计计算
 * 单/双遍扫描，用quickselect计算分位数
 */
int calc_stats_fast(const float* values, int count,
                    float* out_min, float* out_max, float* out_mean,
                    float* out_median, float* out_std,
                    float* out_p05, float* out_p95) {
    emit_cpp_log("C++ CALL: calc_stats_fast");
    if (!values || count <= 0 || !out_min || !out_max || !out_mean) {
        return -1;
    }
    
    // 第一遍：min, max, mean, sum
    float min_val = values[0];
    float max_val = values[0];
    float sum = 0.0f;
    
    for (int i = 0; i < count; ++i) {
        float v = values[i];
        if (v < min_val) min_val = v;
        if (v > max_val) max_val = v;
        sum += v;
    }
    
    float mean = sum / count;
    *out_min = min_val;
    *out_max = max_val;
    *out_mean = mean;
    
    // 第二遍：std, 并复制数据用于分位数计算
    float variance = 0.0f;
    std::vector<float> sorted_copy(values, values + count);
    
    for (int i = 0; i < count; ++i) {
        float delta = values[i] - mean;
        variance += delta * delta;
    }
    
    float std_val = std::sqrt(variance / count);
    *out_std = std_val;
    
    // 计算分位数
    std::sort(sorted_copy.begin(), sorted_copy.end());
    
    int median_idx = count / 2;
    if (out_median) {
        *out_median = (count % 2 == 0) 
            ? (sorted_copy[median_idx - 1] + sorted_copy[median_idx]) / 2.0f
            : sorted_copy[median_idx];
    }
    
    if (out_p05) {
        int p05_idx = (int)(count * 0.05f);
        p05_idx = std::max(0, std::min(p05_idx, count - 1));
        *out_p05 = sorted_copy[p05_idx];
    }
    
    if (out_p95) {
        int p95_idx = (int)(count * 0.95f);
        p95_idx = std::max(0, std::min(p95_idx, count - 1));
        *out_p95 = sorted_copy[p95_idx];
    }
    
    return 0;
}
