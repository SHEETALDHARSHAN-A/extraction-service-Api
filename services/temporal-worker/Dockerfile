FROM golang:1.25.6-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git

WORKDIR /app/services/temporal-worker
COPY services/temporal-worker/go.mod services/temporal-worker/go.sum* ./
COPY shared /app/shared
RUN go mod download

COPY services/temporal-worker .

RUN go build -o /app/services/temporal-worker/worker-bin ./worker/main.go

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/services/temporal-worker/worker-bin ./worker
CMD ["./worker"]
