package clients

import (
	"context"
	"net"
	"testing"

	"google.golang.org/grpc"
)

func TestParseGRPCTarget(t *testing.T) {
	target, ok := parseGRPCTarget("grpc://glm-ocr-service:50062")
	if !ok {
		t.Fatalf("expected grpc endpoint to be detected")
	}
	if target != "glm-ocr-service:50062" {
		t.Fatalf("unexpected target: %s", target)
	}

	_, ok = parseGRPCTarget("http://glm-ocr-service:8002")
	if ok {
		t.Fatalf("http endpoint should not be detected as grpc")
	}
}

func TestInvokeJSONGRPC(t *testing.T) {
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	defer lis.Close()

	server := grpc.NewServer()
	rpcHandlers := map[string]grpc.MethodDesc{
		"Echo": {
			MethodName: "Echo",
			Handler: func(_ interface{}, ctx context.Context, dec func(interface{}) error, _ grpc.UnaryServerInterceptor) (interface{}, error) {
				var req map[string]interface{}
				if err := dec(&req); err != nil {
					return nil, err
				}
				return map[string]interface{}{"ok": true, "name": req["name"]}, nil
			},
		},
	}

	methodList := make([]grpc.MethodDesc, 0, len(rpcHandlers))
	for _, handler := range rpcHandlers {
		methodList = append(methodList, handler)
	}

	server.RegisterService(&grpc.ServiceDesc{
		ServiceName: "test.TransportService",
		HandlerType: (*interface{})(nil),
		Methods:     methodList,
		Streams:     []grpc.StreamDesc{},
	}, new(interface{}))

	go func() {
		_ = server.Serve(lis)
	}()
	defer server.Stop()

	var out map[string]interface{}
	err = invokeJSONGRPC(
		context.Background(),
		lis.Addr().String(),
		"/test.TransportService/Echo",
		map[string]interface{}{"name": "demo"},
		&out,
	)
	if err != nil {
		t.Fatalf("invokeJSONGRPC failed: %v", err)
	}

	if out["ok"] != true {
		t.Fatalf("expected ok=true, got %+v", out)
	}
	if out["name"] != "demo" {
		t.Fatalf("expected echoed name, got %+v", out)
	}
}
