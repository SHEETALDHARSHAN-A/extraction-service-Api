package main

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"image/png"
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/user/idep/shared/proto/preprocessing"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

// Supported archive extensions
var archiveExtensions = map[string]bool{
	".zip": true, ".rar": true, ".7z": true,
	".tar": true, ".gz": true, ".bz2": true, ".xz": true,
	".tgz": true, ".tbz2": true, ".txz": true,
}

type server struct {
	preprocessing.UnimplementedPreprocessingServiceServer
}

func (s *server) Preprocess(ctx context.Context, req *preprocessing.PreprocessRequest) (*preprocessing.PreprocessResponse, error) {
	log.Printf("📄 Preprocessing: %s (Job: %s)", req.FilePath, req.JobId)

	ext := strings.ToLower(filepath.Ext(req.FilePath))
	outputDir := filepath.Join(os.TempDir(), "idep", req.JobId)
	os.MkdirAll(outputDir, 0755)

	// ── Step 1: If archive, extract all documents first ──
	if isArchive(req.FilePath) {
		log.Printf("  📦 Archive detected (%s), extracting...", ext)
		docFiles, err := extractArchive(req.FilePath, outputDir)
		if err != nil {
			return &preprocessing.PreprocessResponse{Status: "error", Error: err.Error()}, nil
		}
		log.Printf("  📦 Extracted %d documents from archive", len(docFiles))

		// Process each extracted document and collect all images
		var allImages []string
		for _, docPath := range docFiles {
			images, err := convertDocToImages(docPath, outputDir)
			if err != nil {
				log.Printf("  ⚠️ Skipping %s: %v", filepath.Base(docPath), err)
				continue
			}
			allImages = append(allImages, images...)
		}

		if len(allImages) == 0 {
			return &preprocessing.PreprocessResponse{Status: "error", Error: "No processable documents found in archive"}, nil
		}

		// Enhance
		allImages = enhanceImages(allImages, outputDir, req.JobId)

		return &preprocessing.PreprocessResponse{ImagePaths: allImages, Status: "success"}, nil
	}

	// ── Step 2: Single file conversion ──
	imagePaths, err := convertDocToImages(req.FilePath, outputDir)
	if err != nil {
		return &preprocessing.PreprocessResponse{Status: "error", Error: err.Error()}, nil
	}

	// ── Step 3: Image Enhancement Pipeline ──
	imagePaths = enhanceImages(imagePaths, outputDir, req.JobId)

	log.Printf("✅ Preprocessed %d page(s) for job %s", len(imagePaths), req.JobId)
	return &preprocessing.PreprocessResponse{ImagePaths: imagePaths, Status: "success"}, nil
}

// ══════════════════════════════════════════
// Archive Extraction
// ══════════════════════════════════════════

func isArchive(filePath string) bool {
	ext := strings.ToLower(filepath.Ext(filePath))
	if archiveExtensions[ext] {
		return true
	}
	// Check for .tar.gz, .tar.bz2, .tar.xz
	lower := strings.ToLower(filePath)
	return strings.HasSuffix(lower, ".tar.gz") ||
		strings.HasSuffix(lower, ".tar.bz2") ||
		strings.HasSuffix(lower, ".tar.xz")
}

func extractArchive(archivePath, outputDir string) ([]string, error) {
	extractDir := filepath.Join(outputDir, "archive_contents")
	os.MkdirAll(extractDir, 0755)

	// Use the Python archive_extractor for full format support
	cmd := exec.Command("python3", "archive_extractor.py", archivePath, extractDir)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("archive extraction failed: %v, stderr: %s", err, stderr.String())
	}

	// Collect all document files from extraction
	var documents []string
	filepath.Walk(extractDir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return nil
		}
		ext := strings.ToLower(filepath.Ext(path))
		if isDocumentExt(ext) {
			documents = append(documents, path)
		}
		return nil
	})

	return documents, nil
}

func isDocumentExt(ext string) bool {
	docExts := map[string]bool{
		".pdf": true, ".docx": true, ".xlsx": true, ".pptx": true,
		".csv": true, ".txt": true,
		".png": true, ".jpg": true, ".jpeg": true, ".tiff": true, ".bmp": true, ".webp": true,
	}
	return docExts[ext]
}

// ══════════════════════════════════════════
// Document to Image Conversion
// ══════════════════════════════════════════

func convertDocToImages(filePath, outputDir string) ([]string, error) {
	ext := strings.ToLower(filepath.Ext(filePath))

	switch ext {
	case ".pdf":
		return convertPDFToImages(filePath, outputDir)
	case ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp":
		destPath := filepath.Join(outputDir, filepath.Base(filePath))
		return []string{destPath}, copyFile(filePath, destPath)
	case ".docx", ".xlsx", ".pptx":
		return convertOfficeToImages(filePath, outputDir)
	case ".txt", ".csv":
		return []string{filePath}, nil
	default:
		return nil, fmt.Errorf("unsupported file type: %s", ext)
	}
}

func convertPDFToImages(pdfPath, outputDir string) ([]string, error) {
	prefix := filepath.Join(outputDir, fmt.Sprintf("pdf_%s", filepath.Base(pdfPath)))
	cmd := exec.Command("pdftoppm", "-png", "-r", "300", pdfPath, prefix)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("pdftoppm failed: %v, stderr: %s", err, stderr.String())
	}

	matches, _ := filepath.Glob(prefix + "-*.png")
	if len(matches) == 0 {
		matches, _ = filepath.Glob(prefix + "*.png")
	}
	log.Printf("  Rendered %d pages from PDF", len(matches))
	return matches, nil
}

func convertOfficeToImages(filePath, outputDir string) ([]string, error) {
	cmd := exec.Command("libreoffice", "--headless", "--convert-to", "pdf", "--outdir", outputDir, filePath)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("libreoffice failed: %v, stderr: %s", err, stderr.String())
	}

	baseName := strings.TrimSuffix(filepath.Base(filePath), filepath.Ext(filePath))
	pdfPath := filepath.Join(outputDir, baseName+".pdf")
	if _, err := os.Stat(pdfPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("expected PDF not found: %s", pdfPath)
	}
	return convertPDFToImages(pdfPath, outputDir)
}

// ══════════════════════════════════════════
// Image Enhancement Pipeline (Python/OpenCV)
// ══════════════════════════════════════════

func enhanceImages(imagePaths []string, outputDir, jobID string) []string {
	enhancedDir := filepath.Join(outputDir, "enhanced")
	os.MkdirAll(enhancedDir, 0755)

	// Copy images to a staging dir for batch processing
	stageDir := filepath.Join(outputDir, "stage")
	os.MkdirAll(stageDir, 0755)

	for _, imgPath := range imagePaths {
		ext := strings.ToLower(filepath.Ext(imgPath))
		if ext == ".txt" || ext == ".csv" {
			continue // Skip text files
		}
		copyFile(imgPath, filepath.Join(stageDir, filepath.Base(imgPath)))
	}

	// Run Python enhancer (GLM-optimized mode)
	cmd := exec.Command("python3", "image_enhancer.py", stageDir, enhancedDir, "glm")
	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		log.Printf("⚠️ Image enhancement failed, using raw images: %v", err)
		return imagePaths
	}

	// Collect enhanced images
	var enhanced []string
	filepath.Walk(enhancedDir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return nil
		}
		enhanced = append(enhanced, path)
		return nil
	})

	if len(enhanced) == 0 {
		return imagePaths
	}

	log.Printf("  ✨ Enhanced %d images for job %s", len(enhanced), jobID)
	return enhanced
}

// ══════════════════════════════════════════
// OCR Fallback
// ══════════════════════════════════════════

func RunTesseractOCR(imagePath string) (string, error) {
	cmd := exec.Command("tesseract", imagePath, "stdout", "-l", "eng", "--oem", "3", "--psm", "3")
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("tesseract failed: %v", err)
	}
	return strings.TrimSpace(stdout.String()), nil
}

// ══════════════════════════════════════════
// Utilities
// ══════════════════════════════════════════

func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0644)
}

func createPlaceholderImage(path string) error {
	img := image.NewRGBA(image.Rect(0, 0, 1, 1))
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return png.Encode(f, img)
}

// ══════════════════════════════════════════
// Main
// ══════════════════════════════════════════

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "50051"
	}

	portNum, _ := strconv.Atoi(port)
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", portNum))
	if err != nil {
		log.Fatalf("Failed to listen on port %d: %v", portNum, err)
	}

	s := grpc.NewServer()
	preprocessing.RegisterPreprocessingServiceServer(s, &server{})
	reflection.Register(s)

	log.Printf("🔧 Preprocessing Service on :%d (Archive + Enhance + OCR)", portNum)
	if err := s.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
