import serial
import service
import sys
import requests
import time
import subprocess

def run_udevadm():
   for i in range(4):
       try:
           output = subprocess.check_output(["udevadm", "info", f"--name=/dev/ttyUSB"+str(i), "--attribute-walk"])
           output_str = output.decode("utf-8")

           if 'ftdi_sio' in output_str:
               print(" found 'ftdi_sio':\n")
               return str(i)
           else:
               print("does not contain 'ftdi_sio'")
       except subprocess.CalledProcessError as e:
           print(f"An error occurred for {device_name}: {e}")
   return

def f_read(file_name):
   device = service.getHostName()
   raspiDir = "/home/JS/"+device+"/"
   data = ""
   with open(raspiDir+file_name, 'r', encoding="ISO-8859-1") as file:
       data = file.read()
   return data

def log_write(data):
   f=open("/home/pi/Serial/myylog.txt","a")
   f.write(data+"\n")
   f.close()

def calculate_transfer_time(file_size_kb, baudrate=19200, databits=7, stopbits=2, parity=1):
   file_size_bytes = file_size_kb * 1024  # KB to bytes
   total_bits = databits + stopbits + parity
   bytes_per_second = baudrate / (total_bits)
   return file_size_bytes / bytes_per_second




def notify_file_progress(device, filename, predict_time, threshold, file_size):
    try:
        url = "http://dev-ycheon.tomes.co.kr/tomes/fileSendProgress"
        data = {
            "equip_name": device,
            "file_name": filename,
            "predict_time": int(predict_time),
            "file_progress": str(threshold),
            "file_size": int(file_size) 
        }
        # Request 로깅
        log_write(f"{date} - Progress API Request - URL: {url}")
        log_write(f"{date} - Progress API Request - Data: {data}")

        response = requests.post(url, json=data)
        
        # Response 로깅
        log_write(f"{date} - Progress API Response - Status: {response.status_code}")
        log_write(f"{date} - Progress API Response - Body: {response.text}")

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("device") == "ok":
                print(f"진행률 {threshold}% 알림 성공")
            return True
        else:
            print(f"API 호출 실패: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"진행률 API 호출 실패: {str(e)}")
        log_write(f"{date} - Progress API Error: {str(e)}")
        return False

def notify_file_finish(device, filename):
    try:
        url = "http://dev-ycheon.tomes.co.kr/tomes/fileSendFinish"
        data = {
            "equip_name": device,
            "file_name": filename
        }
        # Request 로깅
        log_write(f"{date} - Finish API Request - URL: {url}")
        log_write(f"{date} - Finish API Request - Data: {data}")

        response = requests.post(url, json=data)
        
        # Response 로깅
        log_write(f"{date} - Finish API Response - Status: {response.status_code}")
        log_write(f"{date} - Finish API Response - Body: {response.text}")
        
        return response.status_code == 200
    except Exception as e:
        log_write(f"{date} - Finish API Error: {str(e)}")
        return False



def sendFile(ftp_file):
    time.sleep(0.001)
    device = service.getHostName()
    usb_num = run_udevadm()
    try:
        ser = serial.Serial(port='/dev/ttyUSB'+usb_num,
                        baudrate=19200,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        bytesize=serial.EIGHTBITS
                        )
        file_data = f_read(ftp_file)
        lines = file_data.split('\n')
        total_bytes_to_send = sum(len((line.strip() + '\r\n').encode('ISO-8859-1')) for line in lines)
        file_size_kb = total_bytes_to_send / 1024  # 파일 크기를 KB 단위로 계산
        estimated_time = calculate_transfer_time(file_size_kb)
        show_progress = estimated_time > 10
        if show_progress:
            print(f"예상 전송 시간: {estimated_time:.1f}초")
            log_write(f"{date} - 예상 전송 시간: {estimated_time:.1f}초")
        total_bytes_sent = 0
        last_percentage = 0
        for line in lines:
            line = line.strip() + '\r\n'
            bytes_written = ser.write(line.encode('ISO-8859-1'))
            total_bytes_sent += bytes_written
            if show_progress:
                current_percentage = (total_bytes_sent / total_bytes_to_send) * 100
                for threshold in [20, 40, 60, 80]:
                    if last_percentage < threshold and current_percentage >= threshold:
                        print(f"전송 진행률: {threshold}%")
                        log_write(f"{date} - 파일 전송 진행률: {threshold}%")
                        notify_file_progress(device, ftp_file, estimated_time, threshold, file_size_kb)
                last_percentage = current_percentage
            time.sleep(0.0001)

        # 파일 전송 완료 API 호출 (show_progress 상관없이)
        notify_file_finish(device, ftp_file)
        ser.close()

    except KeyboardInterrupt:
        ser.close()
        sys.exit()
    except Exception as e:
        print(str(e))
        print("Exception!!!!!!")
        log_write(date+"////"+str(e))
        if str(e) == "[Errno 5] Input/output error" or "[Errno 2] No such file or directory: '/dev/ttyUSB0'" in str(e):
            log_write(date+"/"+str(e))
            subprocess.call('sudo reboot now', shell=True)
        time.sleep(30)


date = service.getDateTime()
sendFile(sys.argv[1])
