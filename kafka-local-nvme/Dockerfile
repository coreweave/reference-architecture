FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go test ./...
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/kafka-local-pv-repair ./cmd/kafka-local-pv-repair

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/kafka-local-pv-repair /kafka-local-pv-repair
ENTRYPOINT ["/kafka-local-pv-repair"]
