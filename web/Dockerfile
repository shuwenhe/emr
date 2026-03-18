# 多阶段构建优化镜像大小
FROM node:20-alpine AS base

# 依赖安装阶段
FROM base AS deps
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

# 构建阶段
FROM base AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# 设置环境变量
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SELF_REGISTER_BASE_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_SELF_REGISTER_BASE_URL=${NEXT_PUBLIC_SELF_REGISTER_BASE_URL}
ENV NEXT_TELEMETRY_DISABLED=1

# 构建应用
RUN npm run build

# 生产运行阶段
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# 创建非root用户
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# 复制构建产物
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
