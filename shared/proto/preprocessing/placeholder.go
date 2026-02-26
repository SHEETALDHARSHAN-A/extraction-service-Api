package preprocessing

import (
	"context"
	"encoding/json"

	"google.golang.org/grpc"
	grpcEncoding "google.golang.org/grpc/encoding"
)

// --- JSON codec for gRPC (non-protobuf types) ---

const jsonCodecName = "json"

type jsonCodec struct{}

func (jsonCodec) Marshal(v interface{}) ([]byte, error)      { return json.Marshal(v) }
func (jsonCodec) Unmarshal(data []byte, v interface{}) error { return json.Unmarshal(data, v) }
func (jsonCodec) Name() string                               { return jsonCodecName }

func init() {
	grpcEncoding.RegisterCodec(jsonCodec{})
}

// JSONCallOption returns a grpc.CallOption that forces JSON encoding.
// Use this when dialing the preprocessing service.
func JSONCallOption() grpc.CallOption {
	return grpc.ForceCodec(jsonCodec{})
}

// --- Types ---

type PreprocessRequest struct {
	FilePath string `json:"file_path"`
	JobId    string `json:"job_id"`
	Deskew   bool   `json:"deskew"`
	Denoise  bool   `json:"denoise"`
}

type PreprocessResponse struct {
	ImagePaths []string `json:"image_paths"`
	Status     string   `json:"status"`
	Error      string   `json:"error"`
}

// --- Server Interface ---

type PreprocessingServiceServer interface {
	Preprocess(context.Context, *PreprocessRequest) (*PreprocessResponse, error)
	mustEmbedUnimplementedPreprocessingServiceServer()
}

type UnimplementedPreprocessingServiceServer struct{}

func (UnimplementedPreprocessingServiceServer) Preprocess(context.Context, *PreprocessRequest) (*PreprocessResponse, error) {
	return nil, nil
}
func (UnimplementedPreprocessingServiceServer) mustEmbedUnimplementedPreprocessingServiceServer() {}

func preprocessHandler(srv interface{}, ctx context.Context, dec func(interface{}) error, _ grpc.UnaryServerInterceptor) (interface{}, error) {
	req := new(PreprocessRequest)
	if err := dec(req); err != nil {
		return nil, err
	}
	return srv.(PreprocessingServiceServer).Preprocess(ctx, req)
}

var serviceDesc = grpc.ServiceDesc{
	ServiceName: "preprocessing.PreprocessingService",
	HandlerType: (*PreprocessingServiceServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "Preprocess",
			Handler:    preprocessHandler,
		},
	},
	Streams: []grpc.StreamDesc{},
}

func RegisterPreprocessingServiceServer(s grpc.ServiceRegistrar, srv PreprocessingServiceServer) {
	s.RegisterService(&serviceDesc, srv)
}

// --- Client Interface ---

type PreprocessingServiceClient interface {
	Preprocess(ctx context.Context, in *PreprocessRequest, opts ...grpc.CallOption) (*PreprocessResponse, error)
}

type preprocessingServiceClient struct {
	cc grpc.ClientConnInterface
}

func NewPreprocessingServiceClient(cc grpc.ClientConnInterface) PreprocessingServiceClient {
	return &preprocessingServiceClient{cc}
}

func (c *preprocessingServiceClient) Preprocess(ctx context.Context, in *PreprocessRequest, opts ...grpc.CallOption) (*PreprocessResponse, error) {
	out := new(PreprocessResponse)
	// Force JSON codec since our types are plain Go structs, not protobuf.
	opts = append(opts, JSONCallOption())
	err := c.cc.Invoke(ctx, "/preprocessing.PreprocessingService/Preprocess", in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}
