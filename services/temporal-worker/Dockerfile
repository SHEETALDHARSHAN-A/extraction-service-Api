FROM golang:1.22-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git

WORKDIR /app/services/temporal-worker
COPY services/temporal-worker/go.mod ./
RUN go mod download

COPY services/temporal-worker .
COPY shared /app/shared

RUN go build -o worker ./worker/main.go

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/services/temporal-worker/worker .
CMD ["./worker"]
