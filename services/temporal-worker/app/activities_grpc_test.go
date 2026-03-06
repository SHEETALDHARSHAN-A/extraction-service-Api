package app

import (
	"context"
	"net"
	"os"
	"path/filepath"
	"testing"

	"google.golang.org/grpc"
)

func TestCallGLMOCRGRPC(t *testing.T) {
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to listen: %v", err)
	}
	defer lis.Close()

	srv := grpc.NewServer()
	rpcHandlers := map[string]grpc.MethodDesc{
		"ExtractRegionsBatch": {
			MethodName: "ExtractRegionsBatch",
			Handler: func(_ interface{}, ctx context.Context, dec func(interface{}) error, _ grpc.UnaryServerInterceptor) (interface{}, error) {
				var req map[string]interface{}
				if err := dec(&req); err != nil {
					return nil, err
				}
				return map[string]interface{}{
					"results": []map[string]interface{}{
						{
							"region_id":  "region_0",
							"content":    "grpc extracted content",
							"confidence": 0.91,
						},
					},
				}, nil
			},
		},
	}

	methodList := make([]grpc.MethodDesc, 0, len(rpcHandlers))
	for _, handler := range rpcHandlers {
		methodList = append(methodList, handler)
	}

	srv.RegisterService(&grpc.ServiceDesc{
		ServiceName: "glmocr.GLMOCRService",
		HandlerType: (*interface{})(nil),
		Methods:     methodList,
		Streams:     []grpc.StreamDesc{},
	}, new(interface{}))

	go func() {
		_ = srv.Serve(lis)
	}()
	defer srv.Stop()

	tmpDir := t.TempDir()
	imgPath := filepath.Join(tmpDir, "sample.png")
	if err := os.WriteFile(imgPath, []byte{0x89, 0x50, 0x4E, 0x47}, 0o644); err != nil {
		t.Fatalf("failed to write temp image: %v", err)
	}

	a := &Activities{GLMOCRServiceURL: "grpc://" + lis.Addr().String()}
	content, confidence, err := a.callGLMOCRGRPC(context.Background(), imgPath, "Extract", "{}", "")
	if err != nil {
		t.Fatalf("callGLMOCRGRPC failed: %v", err)
	}

	if content != "grpc extracted content" {
		t.Fatalf("unexpected content: %s", content)
	}
	if confidence <= 0 {
		t.Fatalf("expected positive confidence, got %f", confidence)
	}
}
