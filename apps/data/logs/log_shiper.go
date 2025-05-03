package logs

import (
	"context"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"os"
	"strconv"
	"time"

	"cloud.google.com/go/storage"
	"google.golang.org/api/option"
)

// Configuration
const (
	logFilePath      = "/data/synthetic logs/cluster/cluster.log" // Update this to your log file path
	gcsBucket        = "your-gcs-bucket"           // Update this to your GCS bucket name
	gcsPrefix        = "logs/"                     // Prefix within the bucket
	checkInterval    = 10 * time.Second            // How often to check for new logs
	batchUploadSize  = 5 * 1024 * 1024             // 5 MB - Accumulate this much before uploading
	stateFile        = ".log_shipper_state"        // File to track what we've already uploaded
	credentialsFile  = ""                          // Path to service account key file (leave empty to use application default credentials)
)

type LogShipper struct {
	logPath       string
	bucketName    string
	prefix        string
	position      int64
	buffer        string
	bufferSize    int
	storageClient *storage.Client
	ctx           context.Context
}

func NewLogShipper(logPath, bucketName, prefix string) (*LogShipper, error) {
	ctx := context.Background()
	
	var storageClient *storage.Client
	var err error
	
	if credentialsFile != "" {
		storageClient, err = storage.NewClient(ctx, option.WithCredentialsFile(credentialsFile))
	} else {
		storageClient, err = storage.NewClient(ctx)
	}
	
	if err != nil {
		return nil, fmt.Errorf("failed to create storage client: %v", err)
	}
	
	shipper := &LogShipper{
		logPath:       logPath,
		bucketName:    bucketName,
		prefix:        prefix,
		position:      0,
		buffer:        "",
		bufferSize:    0,
		storageClient: storageClient,
		ctx:           ctx,
	}
	
	if err := shipper.loadState(); err != nil {
		log.Printf("Warning: couldn't load state: %v", err)
	}
	
	return shipper, nil
}

func (s *LogShipper) loadState() error {
	if _, err := os.Stat(stateFile); os.IsNotExist(err) {
		if _, err := os.Stat(s.logPath); err == nil {
			info, err := os.Stat(s.logPath)
			if err != nil {
				return err
			}
			s.position = info.Size()
			log.Printf("First run - starting from end of file (%d bytes)", s.position)
			return s.saveState()
		}
		log.Printf("Log file %s does not exist yet. Will wait for it.", s.logPath)
		return nil
	}
	
	data, err := ioutil.ReadFile(stateFile)
	if err != nil {
		return err
	}
	
	pos, err := strconv.ParseInt(string(data), 10, 64)
	if err != nil {
		return err
	}
	
	s.position = pos
	log.Printf("Resuming from position %d", s.position)
	return nil
}

func (s *LogShipper) saveState() error {
	return ioutil.WriteFile(stateFile, []byte(strconv.FormatInt(s.position, 10)), 0644)
}

func (s *LogShipper) checkForNewLogs() error {
	if _, err := os.Stat(s.logPath); os.IsNotExist(err) {
		log.Printf("Log file %s does not exist. Waiting...", s.logPath)
		return nil
	}
	
	file, err := os.Open(s.logPath)
	if err != nil {
		return err
	}
	defer file.Close()
	
	info, err := file.Stat()
	if err != nil {
		return err
	}
	
	currentSize := info.Size()
	
	if currentSize < s.position {
		log.Printf("Log file appears to have been truncated (old size: %d, new size: %d). Resetting position.", s.position, currentSize)
		s.position = 0
	}
	
	if currentSize > s.position {
		if _, err := file.Seek(s.position, 0); err != nil {
			return err
		}
		
		newContent := make([]byte, currentSize-s.position)
		n, err := file.Read(newContent)
		if err != nil && err != io.EOF {
			return err
		}
		
		if n > 0 {
			s.buffer += string(newContent[:n])
			s.bufferSize += n
			s.position += int64(n)
			log.Printf("Read %d bytes. Buffer size: %d bytes", n, s.bufferSize)
			
			if s.bufferSize >= batchUploadSize {
				return s.uploadBuffer()
			}
		}
	}
	
	return nil
}

func (s *LogShipper) uploadBuffer() error {
	if s.buffer == "" {
		return nil
	}
	
	timestamp := time.Now().Format("20060102-150405")
	blobName := fmt.Sprintf("%s%s.log", s.prefix, timestamp)
	
	tempFile, err := ioutil.TempFile("", "log-shipper-*")
	if err != nil {
		return err
	}
	tempFilePath := tempFile.Name()
	defer os.Remove(tempFilePath) 
	
	if _, err := tempFile.WriteString(s.buffer); err != nil {
		tempFile.Close()
		return err
	}
	tempFile.Close()
	
	bucket := s.storageClient.Bucket(s.bucketName)
	obj := bucket.Object(blobName)
	writer := obj.NewWriter(s.ctx)
	
	f, err := os.Open(tempFilePath)
	if err != nil {
		return err
	}
	defer f.Close()
	
	if _, err = io.Copy(writer, f); err != nil {
		return err
	}
	
	if err := writer.Close(); err != nil {
		return err
	}
	
	log.Printf("Uploaded %d bytes to gs://%s/%s", s.bufferSize, s.bucketName, blobName)
	
	s.buffer = ""
	s.bufferSize = 0
	
	// Save state
	return s.saveState()
}

func (s *LogShipper) Run() error {
	log.Printf("Starting log shipper. Monitoring %s and uploading to gs://%s/%s", s.logPath, s.bucketName, s.prefix)
	
	ticker := time.NewTicker(checkInterval)
	forcedUploadTicker := time.NewTicker(1 * time.Minute)
	
	defer ticker.Stop()
	defer forcedUploadTicker.Stop()
	
	for {
		select {
		case <-ticker.C:
			if err := s.checkForNewLogs(); err != nil {
				log.Printf("Error checking for new logs: %v", err)
			}
		case <-forcedUploadTicker.C:
			if s.buffer != "" {
				log.Println("Performing periodic upload of buffered logs")
				if err := s.uploadBuffer(); err != nil {
					log.Printf("Error uploading buffer: %v", err)
				}
			}
		}
	}
}

func (s *LogShipper) Close() {
	if s.buffer != "" {
		if err := s.uploadBuffer(); err != nil {
			log.Printf("Error uploading buffer during shutdown: %v", err)
		}
	}
	s.saveState()
	s.storageClient.Close()
}

func main() {
	shipper, err := NewLogShipper(logFilePath, gcsBucket, gcsPrefix)
	if err != nil {
		log.Fatalf("Failed to create log shipper: %v", err)
	}
	
	go func() {
		c := make(chan os.Signal, 1)
		<-c
		log.Println("Shutting down log shipper...")
		shipper.Close()
		os.Exit(0)
	}()
	
	if err := shipper.Run(); err != nil {
		log.Fatalf("Error running log shipper: %v", err)
	}
}