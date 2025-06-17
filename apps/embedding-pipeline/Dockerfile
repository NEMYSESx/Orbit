FROM golang:1.23-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git gcc musl-dev librdkafka-dev pkgconfig

COPY go.mod go.sum ./

RUN go mod download


COPY . .

RUN CGO_ENABLED=1 go build -tags musl -o main ./cmd/main

FROM alpine:3.19

RUN apk add --no-cache librdkafka


WORKDIR /app

COPY --from=builder /app/main .

COPY config/config.json ./config/


EXPOSE 3002

CMD ["./main", "--config", "./config/config.json"]
