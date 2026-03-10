#ifndef ROI_MASKS_H
#define ROI_MASKS_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * rect_mask: 生成矩形掩膜
 * @param height: 掩膜高度
 * @param width: 掩膜宽度
 * @param x1, y1, x2, y2: 矩形坐标 (自动clamp到[0, width/height))
 * @param mask_out: 输出缓冲区，大小 >= height * width (uint8_t)
 * @return: 0 成功, -1 失败
 */
int rect_mask(int height, int width, float x1, float y1, float x2, float y2,
              unsigned char* mask_out);

/**
 * polygon_mask: 生成多边形掩膜（扫描线填充）
 * @param height: 掩膜高度
 * @param width: 掩膜宽度
 * @param vertices: 顶点坐标数组 [x0, y0, x1, y1, ..., xn, yn]
 * @param num_vertices: 顶点数量
 * @param mask_out: 输出缓冲区，大小 >= height * width (uint8_t)
 * @return: 0 成功, -1 失败
 */
int polygon_mask(int height, int width, const float* vertices, int num_vertices,
                 unsigned char* mask_out);

/**
 * segment_mask: 生成线段缓冲掩膜
 * @param height: 掩膜高度
 * @param width: 掩膜宽度
 * @param x1, y1, x2, y2: 线段端点
 * @param thickness: 线段宽度（半径）
 * @param mask_out: 输出缓冲区，大小 >= height * width (uint8_t)
 * @return: 0 成功, -1 失败
 */
int segment_mask(int height, int width, float x1, float y1, float x2, float y2,
                 float thickness, unsigned char* mask_out);

/**
 * calc_stats_fast: 快速计算数组统计
 * 计算 min, max, mean, median, std, p05, p95
 * 
 * @param values: float32 数组
 * @param count: 元素数量
 * @param out_min, out_max, out_mean, out_median, out_std, out_p05, out_p95: 输出指针
 * @return: 0 成功, -1 失败
 */
int calc_stats_fast(const float* values, int count, 
                    float* out_min, float* out_max, float* out_mean,
                    float* out_median, float* out_std, 
                    float* out_p05, float* out_p95);

#ifdef __cplusplus
}
#endif

#endif // ROI_MASKS_H
