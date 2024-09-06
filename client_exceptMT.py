import subprocess
import re
import time
import datetime
import concurrent.futures
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
import asyncio
import websockets
import json
import os
import base64
import socket
from collections import Counter

# 전역 변수로 cpu_serial을 저장합니다.
cpu_serial = None

def initialize_cpu_serial():
    global cpu_serial
    serial_list = []
    for _ in range(5):
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('Serial'):
                        serial_list.append(line.split(':')[1].strip())
                        break
        except FileNotFoundError:
            serial_list.append("0000000000000000")
    cpu_serial = Counter(serial_list).most_common(1)[0][0]

def get_ip_address(ifname):
    command = "/sbin/ifconfig {}".format(ifname)
    output = os.popen(command).read()
    match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', output)
    if match:
        return match.group(1)
    return ""

def get_url_from_autostart():
    autostart_paths = [
        os.path.expanduser("~/.config/lxsession/LXDE-pi/autostart"),
        os.path.expanduser("~/.config/lxsession/LXDE-pi/autostart.org")
    ]

    for autostart_path in autostart_paths:
        if os.path.isfile(autostart_path):
            try:
                with open(autostart_path, 'r') as file:
                    for line in file:
                        if 'http://' in line or 'https://' in line:
                            match = re.search(r'(https?://[^\s]+)', line)
                            if match:
                                full_url = match.group(1)
                                return full_url.strip()
            except FileNotFoundError:
                continue
    print("Autostart file not found")
    return ''

def get_MTConnect_status():
    command = "crontab -l | grep 'monitor_adapter.py' | grep -v '^#'"
    if os.popen(command).read().strip():
        return "O"
    return "X"
def get_device_info():
    hostname = socket.gethostname()
    intern_ip = get_ip_address('wlan0')
    MTConnect_status = get_MTConnect_status()
    url = get_url_from_autostart()

    current = "X"
    current_command = "crontab -l | grep '/Current/monitor.py' | grep -v '^#'"
    if os.popen(current_command).read().strip():
        current = "O"
    print("MTConnect_stattus", MTConnect_status)
    return {
        "name": hostname,
        "intern_ip": intern_ip,
        "MTConnect_OX": MTConnect_status,
        "url": url,
        "current": current,
        "cpu_serial": cpu_serial
    }


async def send_initial_status(websocket):
    device_info = get_device_info()
    initial_message = json.dumps({"status": "established", **device_info})
    await websocket.send(initial_message)
    print(f"Sent initial status: {initial_message}")

async def handle_messages(websocket):
    async for message in websocket:
        data = json.loads(message)
        if data.get('status') == 'url_change':
            seq = data.get('device_id')
            new_url = data.get('url')
            browser_id = data.get('browser_id')
            update_autostart_url(new_url, seq)
            response = json.dumps({"status": "url_response", "device_id": seq, "browser_id": browser_id})
            await websocket.send(response)
        elif data.get('status') == 'ssh_connect':
            seq = data.get('device_id')
            browser_id = data.get('browser_id')
            result = await connect_ssh()

            # 결과가 0일 때만 응답 전송
            if result == 0:
                response = json.dumps({
                    "status": "ssh_response",
                    "device_id": seq,
                    "browser_id": browser_id,
                })
                await websocket.send(response)
        elif data.get('status') == 'execute_command':
            command = data.get('command')
            seq = data.get('device_id')
            browser_id = data.get('browser_id')
            returncode, stdout, stderr = execute_command(command)
            result = stdout if returncode == 0 else stderr
            status = 'success' if returncode == 0 else 'error'
            response = {
                "status": "command_success",
                "device_id": seq,
                "browser_id": browser_id,
                "result": result,
                "command_status": status
            }
            await websocket.send(json.dumps(response))
        elif data.get('status') == 'send_vnc':
            seq = data.get('device_id')
            browser_id = data.get('browser_id')
            screenshot_path = capture_screenshot()
            if screenshot_path:
                with open(screenshot_path, "rb") as image_file:
                    img_data = base64.b64encode(image_file.read()).decode('utf-8')
                response = {
                    "status": "vnc_response",
                    "device_id": seq,
                    "browser_id": browser_id,
                    "img": img_data
                }
                await websocket.send(json.dumps(response))


async def send_color_status_periodically(websocket):
    while True:
        device_info = get_device_info()
        status_message = json.dumps({"status": "color", "cpu_serial" : cpu_serial})
        await websocket.send(status_message)
        print(f"Sent status: color: {status_message}")
        await asyncio.sleep(60)  # 1분마다 전송



def update_autostart_url(new_url, seq):
    autostart_path = "/home/pi/.config/lxsession/LXDE-pi/autostart"
    autostart_org_path = "/home/pi/.config/lxsession/LXDE-pi/autostart.org"

    if os.path.isfile(autostart_org_path):
        subprocess.call('sudo mv {} {}'.format(autostart_org_path, autostart_path), shell=True)
        print("Renamed autostart.org to autostart")

    try:
        subprocess.call('sudo rm -rf /home/pi/.config/chromium/Singleton*', shell=True)
        print("Removed lock files")

        time.sleep(2)

        url_parts = new_url.split('/')
        if url_parts[-1]:
            hostname_to_set = url_parts[-1]
        else:
            hostname_to_set = url_parts[-2]
        print("1111111111111111111")
        # 읽기 권한으로 파일을 열기
        with open(autostart_path, 'r') as file:
            lines = file.readlines()
        print("22222222222")
        # 임시 파일에 쓰기
        with open('/tmp/autostart', 'w') as temp_file:
            for line in lines:
                if 'http://' in line or 'https://' in line:
                    line = re.sub(r'(https?://[^\s]+)', new_url, line)
                temp_file.write(line)
        print("33333333333333")
        # 임시 파일을 실제 파일로 이동
        subprocess.call('sudo mv /tmp/autostart {}'.format(autostart_path), shell=True)
        print("Autostart URL updated to: {}".format(new_url))

        # 호스트네임 설정
        with open('/tmp/hostname', 'w') as file:
            file.write(hostname_to_set + '\n')
        subprocess.call('sudo mv /tmp/hostname /etc/hostname', shell=True)
        print("System hostname updated to: {}".format(hostname_to_set))

        # /etc/hosts 파일 업데이트
        with open('/etc/hosts', 'r') as file:
            lines = file.readlines()
        with open('/tmp/hosts', 'w') as file:
            for line in lines:
                if '127.0.1.1' in line:
                    file.write('127.0.1.1       {}\n'.format(hostname_to_set))
                else:
                    file.write(line)
        subprocess.call('sudo mv /tmp/hosts /etc/hosts', shell=True)
        print("555555555555")
        print("/etc/hostname and /etc/hosts updated to: {}".format(hostname_to_set))

        subprocess.call('sudo hostnamectl set-hostname {}'.format(hostname_to_set), shell=True)

        # 시스템 재부팅 주석 처리
        subprocess.call('sudo reboot', shell=True)
        #print("System rebooting... (not actually rebooted)")

    except FileNotFoundError:
        print("Autostart file not found")
    except Exception as e:
        print("Error updating autostart URL: {}".format(e))







# 비동기적으로 SSH 연결을 시도하는 함수
async def connect_ssh():
    os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin"
    command = 'sshpass -p "jmes!20191107" ssh -N -f -p 4222 -o StrictHostKeyChecking=no -R 3022:localhost:3022 pi@106.240.243.250'

    # SSH 터널을 백그라운드에서 실행하기 위해 -f 옵션 추가
    process = subprocess.Popen(command, shell=True)
    
    # SSH 연결 시도 후 즉시 리턴
    if process.returncode is None or process.returncode == 0:
        print("SSH tunnel established")
        return 0
    else:
        print("Failed to establish SSH tunnel")
        return process.returncode







# 새로운 execute_command 함수 추가
def execute_command(command):
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return process.returncode, stdout.decode(), stderr.decode()

def capture_screenshot():
    command = "export DISPLAY=:0 && scrot /tmp/screenshot.png"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.communicate()
    screenshot_path = "/tmp/screenshot.png"
    return screenshot_path if os.path.exists(screenshot_path) else None


async def main():
    initialize_cpu_serial()  # CPU 시리얼을 초기화합니다.
    uri = "ws://106.240.243.250:8888/ws/mtconnect_socket/"

    while True:
        try:
            async with websockets.connect(uri) as websocket:
                await send_initial_status(websocket)
                asyncio.create_task(handle_messages(websocket))
                asyncio.create_task(send_color_status_periodically(websocket))

                # WebSocket 연결을 유지함
                await websocket.wait_closed()

        except (websockets.ConnectionClosed, ConnectionRefusedError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
            print(f"Connection failed: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)  # 재연결 시도 전 대기 시간
        except Exception as e:
            print(f"Unexpected error: {e}. Reconnecting in 10 seconds...")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
