#!/usr/bin/env python3
import socket
import time
import argparse

def send_udp_barrage(target_ip, target_port, count, delay):
    print(f"[*] Starting UDP barrage to {target_ip}:{target_port}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    messages_sent = 0
    try:
        for i in range(1, count + 1):
            msg = f"Gigamon Lab Test Message {i}/{count} - Timestamp: {time.time()}"
            sock.sendto(msg.encode(), (target_ip, target_port))
            messages_sent += 1
            
            if messages_sent % 100 == 0:
                print(f"[*] Sent {messages_sent} messages...")
            
            if delay > 0:
                time.sleep(delay)
                
    except KeyboardInterrupt:
        print("\n[*] Barrage stopped by user.")
    except Exception as e:
        print(f"\n[!] Error during transmission: {e}")
    finally:
        sock.close()
        print(f"[*] Finished. Total messages sent: {messages_sent}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a barrage of UDP test traffic for the Gigamon Lab.")
    parser.add_argument("target_ip", help="The destination IP address (e.g., prod2_private_ip)")
    parser.add_argument("--port", type=int, default=1514, help="The destination UDP port (default: 1514)")
    parser.add_argument("--count", type=int, default=1000, help="Number of messages to send (default: 1000)")
    parser.add_argument("--delay", type=float, default=0.001, help="Delay between messages in seconds (default: 0.001)")
    
    args = parser.parse_args()
    send_udp_barrage(args.target_ip, args.port, args.count, args.delay)