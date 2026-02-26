package main

import (
	"log"

	"github.com/user/idep/temporal-worker/app"
	"github.com/user/idep/temporal-worker/config"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
)

func main() {
	cfg := config.Load()

	c, err := client.Dial(client.Options{
		HostPort:  cfg.TemporalHost,
		Namespace: cfg.TemporalNamespace,
	})
	if err != nil {
		log.Fatalln("❌ Unable to create Temporal client:", err)
	}
	defer c.Close()

	w := worker.New(c, cfg.TaskQueue, worker.Options{
		MaxConcurrentActivityExecutionSize:     20,
		MaxConcurrentWorkflowTaskExecutionSize: 10,
	})

	// Register workflow
	w.RegisterWorkflow(app.DocumentProcessingWorkflow)

	// Register activities with real service connections
	activities := &app.Activities{
		PreprocessingHost:  cfg.PreprocessingHost,
		PostprocessingHost: cfg.PostprocessingHost,
		TritonHost:         cfg.TritonHost,
		TritonGRPCPort:     cfg.TritonGRPCPort,
		TritonHTTPPort:     cfg.TritonHTTPPort,
		MinioEndpoint:      cfg.MinioEndpoint,
		MinioAccessKey:     cfg.MinioAccessKey,
		MinioSecretKey:     cfg.MinioSecretKey,
		MinioBucket:        cfg.MinioBucket,
	}
	w.RegisterActivity(activities)

	log.Printf("🚀 Temporal Worker starting on queue: %s", cfg.TaskQueue)
	err = w.Run(worker.InterruptCh())
	if err != nil {
		log.Fatalln("❌ Unable to start worker:", err)
	}
}
