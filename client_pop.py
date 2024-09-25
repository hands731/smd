import subprocess
import re
import time
import asyncio
import websockets
import json
import os
import base64
import socket
import ssl
# 전역 변수로 cpu_serial을 저장합니다.
cpu_serial = None

def get_disk_serial():
    disk_serial = "0000000000000000"
    try:
        result = subprocess.run(['lsblk', '-o', 'SERIAL', '-dn'], stdout=subprocess.PIPE)
        disk_serial = result.stdout.decode().strip().split()[0]
    except (FileNotFoundError, IndexError, subprocess.CalledProcessError):
        pass
    return disk_serial

def get_interface_name():
    command = "/sbin/ifconfig"
    output = os.popen(command).read()
    match = re.search(r'(wlp\w*)', output)
    if match:
        return match.group(1)
    return None

def get_ip_address():
    ifname = get_interface_name()
    if ifname:
        command = f"/sbin/ifconfig {ifname}"
        output = os.popen(command).read()
        match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
    return ""

def get_url_from_autostart():
    autostart_path = "/home/pi/kiosk.sh"
    try:
        with open(autostart_path, 'r') as file:
            for line in file:
                # 정규표현식을 사용하여 http:// 또는 https://로 시작하는 URL을 추출
                match = re.search(r'(http[s]?://[^\s]+)', line)
                if match:
                    return match.group(1).strip()  # 전체 URL 반환
    except FileNotFoundError:
        print("Autostart file not found")
    return ''

def get_device_info():
    hostname = socket.gethostname()
    intern_ip = get_ip_address()  # 동적으로 네트워크 인터페이스 이름을 가져와 사용
    url = get_url_from_autostart()

    return {
        "name": hostname,
        "intern_ip": intern_ip,
        "MTConnect_OX": "X",
        "url": url,
        "current": "X",
        "cpu_serial": cpu_serial
    }

async def send_initial_status(websocket):
    device_info = get_device_info()
    initial_message = json.dumps({"status": "established", **device_info})  # JSON 직렬화
    await websocket.send(initial_message)
    print(f"Sent initial status: {initial_message}")

async def handle_messages(websocket):
    async for message in websocket:
        data = json.loads(message)
        if data.get('status') == 'url_change':
            print(data)
            seq = data.get('device_id')
            new_url = data.get('url')
            browser_id = data.get('browser_id')
            update_autostart_url(new_url)
            response = {
                "status": "url_response",
                "device_id": seq,
                "browser_id": browser_id
            }
            await websocket.send(json.dumps(response))  # JSON 직렬화하여 전송
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
            await websocket.send(json.dumps(response))  # JSON 직렬화하여 전송
        elif data.get('status') == 'send_vnc':
            seq = data.get('device_id')
            browser_id = data.get('browser_id')
            screenshot_path = capture_screenshot()
            if screenshot_path:
                print(screenshot_path)
                with open(screenshot_path, "rb") as image_file:
                    img_data = base64.b64encode(image_file.read()).decode('utf-8')
                response = {
                    "status": "vnc_response",
                    "device_id": seq,
                    "browser_id": browser_id,
                    "img": img_data
                }
                await websocket.send(json.dumps(response))  # JSON 직렬화하여 전송

async def send_data_to_server(uri):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    while True:
        try:
            async with websockets.connect(uri, ssl=ssl_context) as websocket:
                await send_initial_status(websocket)

                # 메시지 처리 및 주기적인 상태 전송을 비동기적으로 실행
                message_task = asyncio.create_task(handle_messages(websocket))
                color_status_task = asyncio.create_task(send_color_status_periodically(websocket))

                await asyncio.gather(message_task, color_status_task)
        except Exception as e:
            print(f"WebSocket error or connection closed: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)





async def send_color_status_periodically(websocket):
    try:
        while True:
            device_info = get_device_info()
            status_message = json.dumps({"status": "color", "cpu_serial": cpu_serial})  # JSON 직렬화
            await websocket.send(status_message)
            print(f"Sent status: color: {status_message}")
            await asyncio.sleep(60)  # 1분마다 전송
    except websockets.exceptions.ConnectionClosedOK:
        print("WebSocket 연결이 정상적으로 종료되었습니다.")
    except Exception as e:
        print(f"send_color_status_periodically에서 예외 발생: {e}")



def update_autostart_url(new_url):
    autostart_path = "/home/pi/kiosk.sh"

    try:
        # 1. kiosk.sh 파일이 존재하는지 확인
        if not os.path.isfile(autostart_path):
            print("kiosk.sh 파일이 존재하지 않습니다.")
            return

        # 2. URL 업데이트
        with open(autostart_path, 'r') as file:
            lines = file.readlines()

        with open(autostart_path, 'w') as file:
            for line in lines:
                if 'http://' in line or 'https://' in line:
                    line = re.sub(r'(https?://[^\s]+)', new_url, line)
                file.write(line)

        print(f"kiosk.sh 파일의 URL이 {new_url}로 업데이트 되었습니다.")

        # 3. 시스템 재부팅
        print("시스템을 재부팅합니다...")
        subprocess.call("echo 'jmes!20191107' | sudo -S reboot", shell=True)

    except Exception as e:
        print(f"URL 업데이트 중 오류 발생: {e}")




# 비동기적으로 SSH 연결을 시도하는 함수
async def connect_ssh():
    os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin"
    command = 'sshpass -p "jmes!20191107" ssh -N -f -p 4222 -o StrictHostKeyChecking=no -R 3022:localhost:22 pi@106.240.243.250'

    # SSH 터널을 백그라운드에서 실행하기 위해 -f 옵션 추가
    process = subprocess.Popen(command, shell=True)
    
    # SSH 연결 시도 후 즉시 리턴
    if process.returncode is None or process.returncode == 0:
        print("SSH tunnel established")
        return 0
    else:
        print("Failed to establish SSH tunnel")
        return process.returncode

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
    global cpu_serial
    cpu_serial = get_disk_serial()  # CPU 시리얼을 초기화합니다.
    uri = "wss://106.240.243.250:8888/ws/mtconnect_socket/"
    await send_data_to_server(uri)

if __name__ == "__main__":
    asyncio.run(main())
