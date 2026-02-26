FROM golang:1.25.6-alpine AS builder

WORKDIR /app

# Install dependencies
RUN apk add --no-cache git

COPY go.work ./
COPY shared /app/shared
COPY services/api-gateway/go.mod services/api-gateway/go.sum* ./services/api-gateway/
COPY services/temporal-worker/go.mod services/temporal-worker/go.sum* ./services/temporal-worker/
COPY services/preprocessing-service/go.mod services/preprocessing-service/go.sum* ./services/preprocessing-service/

# Actually, it's easier to build from the service directory for simplicity in local dev
WORKDIR /app/services/api-gateway
RUN go mod download

COPY services/api-gateway .

RUN go build -o main .

FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/services/api-gateway/main .
EXPOSE 8000
CMD ["./main"]
