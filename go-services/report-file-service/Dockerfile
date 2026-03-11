FROM golang:1.22-alpine AS build
WORKDIR /src

COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/report-file-service ./cmd/server

FROM alpine:3.20
WORKDIR /app

RUN addgroup -S app && adduser -S app -G app
COPY --from=build /out/report-file-service /usr/local/bin/report-file-service

ENV RFS_ADDR=:8088
ENV RFS_REPORTS_DIR=/app/reports
ENV RFS_CACHE_TTL_SECONDS=300

EXPOSE 8088
USER app
ENTRYPOINT ["/usr/local/bin/report-file-service"]
