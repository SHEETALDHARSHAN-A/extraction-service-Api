package postprocessing

import (
	"context"
	"encoding/json"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// --- JSON codec for gRPC (non-protobuf types) ---

const jsonCodecName = "json"

type jsonCodec struct{}

func (jsonCodec) Marshal(v interface{}) ([]byte, error)      { return json.Marshal(v) }
func (jsonCodec) Unmarshal(data []byte, v interface{}) error { return json.Unmarshal(data, v) }
func (jsonCodec) Name() string                               { return jsonCodecName }

// JSONCallOption forces JSON encoding for this service contract.
func JSONCallOption() grpc.CallOption {
	// Use a local codec instance to avoid requiring generated protobuf bindings.
	return grpc.ForceCodec(jsonCodec{})
}

// --- Types ---

type PostProcessRequest struct {
	RawContent string
	JobId      string
	RedactPii  bool
}

type PostProcessResponse struct {
	StructuredContent string
	ConfidenceScore   float32
	Status            string
	Error             string
}

// --- Server Interface ---

type PostProcessingServiceServer interface {
	PostProcess(context.Context, *PostProcessRequest) (*PostProcessResponse, error)
	mustEmbedUnimplementedPostProcessingServiceServer()
}

type UnimplementedPostProcessingServiceServer struct{}

func (UnimplementedPostProcessingServiceServer) PostProcess(context.Context, *PostProcessRequest) (*PostProcessResponse, error) {
	return nil, status.Errorf(codes.Unimplemented, "method PostProcess not implemented")
}
func (UnimplementedPostProcessingServiceServer) mustEmbedUnimplementedPostProcessingServiceServer() {}

func RegisterPostProcessingServiceServer(s grpc.ServiceRegistrar, srv PostProcessingServiceServer) {
	s.RegisterService(&serviceDesc, srv)
}

func postProcessHandler(srv interface{}, ctx context.Context, dec func(interface{}) error, _ grpc.UnaryServerInterceptor) (interface{}, error) {
	req := new(PostProcessRequest)
	if err := dec(req); err != nil {
		return nil, err
	}
	return srv.(PostProcessingServiceServer).PostProcess(ctx, req)
}

var serviceDesc = grpc.ServiceDesc{
	ServiceName: "postprocessing.PostProcessingService",
	HandlerType: (*PostProcessingServiceServer)(nil),
	Methods: []grpc.MethodDesc{
		{
			MethodName: "PostProcess",
			Handler:    postProcessHandler,
		},
	},
	Streams: []grpc.StreamDesc{},
}

// --- Client Interface ---

type PostProcessingServiceClient interface {
	PostProcess(ctx context.Context, in *PostProcessRequest, opts ...grpc.CallOption) (*PostProcessResponse, error)
}

type postProcessingServiceClient struct {
	cc grpc.ClientConnInterface
}

func NewPostProcessingServiceClient(cc grpc.ClientConnInterface) PostProcessingServiceClient {
	return &postProcessingServiceClient{cc}
}

func (c *postProcessingServiceClient) PostProcess(ctx context.Context, in *PostProcessRequest, opts ...grpc.CallOption) (*PostProcessResponse, error) {
	out := new(PostProcessResponse)
	opts = append(opts, JSONCallOption())
	err := c.cc.Invoke(ctx, "/postprocessing.PostProcessingService/PostProcess", in, out, opts...)
	if err != nil {
		return nil, err
	}
	return out, nil
}
