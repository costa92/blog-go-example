package protocolcase

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"time"

	pb "github.com/costa92/blog-go-example/http-timeout-cancellation/api"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type protocolKey struct{}
type handler func(context.Context, *pb.WorkRequest) (*pb.WorkReply, error)

type endpoint struct {
	call  func(context.Context, *pb.WorkRequest, time.Duration) (*pb.WorkReply, error)
	close func()
}

type grpcWorker struct {
	pb.UnimplementedWorkerServer
	handler handler
}

func (s *grpcWorker) Run(ctx context.Context, req *pb.WorkRequest) (*pb.WorkReply, error) {
	if req.GetMode() == "ping" {
		return &pb.WorkReply{Outcome: "ready"}, nil
	}
	return s.handler(context.WithValue(ctx, protocolKey{}, "gRPC/HTTP2"), req)
}

func openEndpoint(protocol string, h handler) (*endpoint, error) {
	if protocol == "grpc" {
		listener, err := net.Listen("tcp", "127.0.0.1:0")
		if err != nil {
			return nil, err
		}
		server := grpc.NewServer()
		pb.RegisterWorkerServer(server, &grpcWorker{handler: h})
		stopped := make(chan struct{})
		go func() { defer close(stopped); _ = server.Serve(listener) }()
		conn, err := grpc.NewClient("passthrough:///"+listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithNoProxy())
		if err != nil {
			server.Stop()
			listener.Close()
			<-stopped
			return nil, err
		}
		client := pb.NewWorkerClient(conn)
		return &endpoint{
			call: func(ctx context.Context, req *pb.WorkRequest, _ time.Duration) (*pb.WorkReply, error) {
				return client.Run(ctx, req)
			},
			close: func() { conn.Close(); server.Stop(); listener.Close(); <-stopped },
		}, nil
	}
	if protocol != "http1" && protocol != "http2" {
		return nil, fmt.Errorf("unknown protocol %q", protocol)
	}
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req pb.WorkRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		var reply *pb.WorkReply
		var err error
		if req.GetMode() == "ping" {
			reply = &pb.WorkReply{Outcome: "ready"}
		} else {
			reply, err = h(context.WithValue(r.Context(), protocolKey{}, r.Proto), &req)
		}
		if err != nil {
			http.Error(w, err.Error(), http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(reply)
	}))
	if protocol == "http2" {
		server.EnableHTTP2 = true
		server.StartTLS()
	} else {
		server.Start()
	}
	client := server.Client()
	transport, ok := client.Transport.(*http.Transport)
	if !ok {
		transport = http.DefaultTransport.(*http.Transport)
	}
	transport = transport.Clone()
	transport.Proxy = nil
	transport.ForceAttemptHTTP2 = protocol == "http2"
	client.Transport = transport
	return &endpoint{
		call: func(ctx context.Context, req *pb.WorkRequest, timeout time.Duration) (*pb.WorkReply, error) {
			body, err := json.Marshal(req)
			if err != nil {
				return nil, err
			}
			r, err := http.NewRequestWithContext(ctx, http.MethodPost, server.URL, bytes.NewReader(body))
			if err != nil {
				return nil, err
			}
			r.Header.Set("Content-Type", "application/json")
			c := *client
			c.Timeout = timeout
			resp, err := c.Do(r)
			if err != nil {
				return nil, err
			}
			defer resp.Body.Close()
			if resp.StatusCode != http.StatusOK {
				return nil, fmt.Errorf("HTTP status %d", resp.StatusCode)
			}
			var reply pb.WorkReply
			err = json.NewDecoder(resp.Body).Decode(&reply)
			return &reply, err
		},
		close: func() { transport.CloseIdleConnections(); server.Close() },
	}, nil
}

func warm(ctx context.Context, e *endpoint) error {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	_, err := e.call(ctx, &pb.WorkRequest{Mode: "ping"}, 0)
	return err
}
