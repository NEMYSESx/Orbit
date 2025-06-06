FROM golang:1.23-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git gcc musl-dev librdkafka-dev pkgconfig

COPY go.mod go.sum ./

RUN go mod download

COPY . .

RUN CGO_ENABLED=1 go build -tags musl -o main ./cmd/main

FROM alpine:3.19

RUN apk add --no-cache ca-certificates librdkafka

RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S appuser -G appgroup

WORKDIR /app

COPY config/config.json ./config/


COPY --from=builder /app/main .

RUN chown appuser:appgroup /app/main


USER appuser

EXPOSE 3001
CMD ["./main", "--config", "./config/config.json"]
