package clients

import (
	"context"
	"fmt"
	"strings"

	sharedpreprocessing "github.com/user/idep/shared/proto/preprocessing"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func parseGRPCTarget(endpoint string) (string, bool) {
	if strings.HasPrefix(endpoint, "grpc://") {
		return strings.TrimPrefix(endpoint, "grpc://"), true
	}
	return "", false
}

func invokeJSONGRPC(ctx context.Context, target, method string, in interface{}, out interface{}) error {
	conn, err := grpc.NewClient(target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return fmt.Errorf("failed to connect to grpc target %s: %w", target, err)
	}
	defer conn.Close()

	if err := conn.Invoke(ctx, method, in, out, sharedpreprocessing.JSONCallOption()); err != nil {
		return fmt.Errorf("grpc invoke failed for %s: %w", method, err)
	}
	return nil
}
